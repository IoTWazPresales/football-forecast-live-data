#!/usr/bin/env python3
"""HBT-1.3R market/tactical intelligence collector.

Adds pre-kickoff/live data for market families that were previously missing:
- player shots / shots on target / anytime-goal scoring hazards,
- team corners and cards rolling context,
- actual/expected tactical formation strings when the source exposes them,
- venue-to-venue and club-base travel distance.

This file is a data/feature collector only. It never consumes bookmaker odds and
never mutates frozen HBT-1.1.2 coefficients. Downstream promotion requires the
separate causal validation gates in the dashboard/model lab.
"""
from __future__ import annotations

import json
import math
import re
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any

import hbt_collect_players_espn as p

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hbt_live_data"
PREXI = OUT / "pre_xi_context.json"
MANIFEST = OUT / "manifest.json"
OUTPUT = OUT / "market_intelligence.json"
CACHE_PATH = OUT / "_market_intelligence_cache.json"
SCHEMA = "HBT-LIVE-DATA-1"
VERSION = "HBT-1.3R-MARKET-INTEL"

UNDERSTAT = {
    "en.1": "EPL",
    "es.1": "La_liga",
    "de.1": "Bundesliga",
    "it.1": "Serie_A",
    "fr.1": "Ligue_1",
}


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    p.write_json(path, data)


def fnum(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(str(v).strip().replace("%", ""))
    except Exception:
        return None


def nkey(s: str) -> str:
    return p.team_key(str(s or ""))


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def poisson_tail(lam: float, minimum: int) -> float:
    lam = max(0.0, float(lam))
    if minimum <= 0:
        return 1.0
    term = math.exp(-lam)
    cdf = term
    for k in range(1, minimum):
        term *= lam / k
        cdf += term
    return clamp(1.0 - cdf, 0.0, 1.0)


def haversine_km(a: tuple[float, float] | None, b: tuple[float, float] | None) -> float | None:
    if not a or not b:
        return None
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    q = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(q)))


def stat_key(s: str) -> str:
    s = nkey(s).replace(" ", "_")
    aliases = {
        "shots_on_goal": "shots_on_target",
        "shots_on_target": "shots_on_target",
        "shots": "shots",
        "total_shots": "shots",
        "corner_kicks": "corners",
        "corners": "corners",
        "fouls_committed": "fouls",
        "fouls": "fouls",
        "yellow_cards": "yellow_cards",
        "red_cards": "red_cards",
        "possession": "possession",
        "possession_pct": "possession",
    }
    return aliases.get(s, s)


def parse_stat_list(rows: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    if not isinstance(rows, list):
        return out
    for q in rows:
        if not isinstance(q, dict):
            continue
        name = q.get("name") or q.get("label") or q.get("displayName") or q.get("abbreviation") or q.get("shortDisplayName")
        value = q.get("value")
        if value is None:
            value = q.get("displayValue")
        if name is None:
            continue
        v = fnum(value)
        if v is not None:
            out[stat_key(str(name))] = v
    return out


def parse_team_stats(raw: dict[str, Any]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    box = raw.get("boxscore") if isinstance(raw, dict) else None
    for t in ((box or {}).get("teams") or []):
        if not isinstance(t, dict):
            continue
        team = t.get("team") or {}
        tid = str(team.get("id") or t.get("id") or "")
        if not tid:
            continue
        stats = parse_stat_list(t.get("statistics") or t.get("stats") or [])
        if stats:
            out[tid] = stats
    return out


def _athlete_name(row: dict[str, Any]) -> str:
    a = row.get("athlete") if isinstance(row.get("athlete"), dict) else row.get("player") if isinstance(row.get("player"), dict) else row
    return str(a.get("displayName") or a.get("fullName") or a.get("shortName") or a.get("name") or "").strip()


def _athlete_id(row: dict[str, Any]) -> str:
    a = row.get("athlete") if isinstance(row.get("athlete"), dict) else row.get("player") if isinstance(row.get("player"), dict) else row
    return str(a.get("id") or row.get("id") or "")


def parse_player_stats(raw: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for r in raw.get("rosters") or []:
        if not isinstance(r, dict):
            continue
        team = r.get("team") or {}
        tid = str(team.get("id") or "")
        if not tid:
            continue
        side: dict[str, dict[str, Any]] = {}
        for q in r.get("roster") or r.get("athletes") or []:
            if not isinstance(q, dict):
                continue
            pid = _athlete_id(q) or ("name:" + nkey(_athlete_name(q)))
            name = _athlete_name(q)
            if not name:
                continue
            stats: dict[str, float] = {}
            src = q.get("stats") or q.get("statistics") or []
            if isinstance(src, list) and src and isinstance(src[0], dict):
                stats = parse_stat_list(src)
            for k, alias in {
                "minutesPlayed": "minutes",
                "minutes": "minutes",
                "shots": "shots",
                "shotsOnTarget": "shots_on_target",
                "shotsOnGoal": "shots_on_target",
                "goals": "goals",
                "yellowCards": "yellow_cards",
                "redCards": "red_cards",
            }.items():
                if q.get(k) is not None:
                    v = fnum(q.get(k))
                    if v is not None:
                        stats[alias] = v
            pos = p.normalize_pos(q) if hasattr(p, "normalize_pos") else ""
            side[pid] = {"id": pid, "name": name, "pos": pos, "stats": stats}
        if side:
            out[tid] = side
    return out


def recursive_formations(obj: Any, team_id: str) -> list[str]:
    found: list[str] = []
    def walk(x: Any, context_team: str | None = None) -> None:
        if isinstance(x, dict):
            t = context_team
            team = x.get("team")
            if isinstance(team, dict) and team.get("id") is not None:
                t = str(team.get("id"))
            if x.get("teamId") is not None:
                t = str(x.get("teamId"))
            for k, v in x.items():
                if str(k).lower() in {"formation", "formationname", "formation_name"} and isinstance(v, (str, int)):
                    s = str(v).strip()
                    if (t is None or t == team_id) and re.fullmatch(r"\d(?:-\d){2,4}", s):
                        found.append(s)
                elif isinstance(v, (dict, list)):
                    walk(v, t)
        elif isinstance(x, list):
            for v in x:
                walk(v, context_team)
    walk(obj)
    return found


def parse_venue(raw: dict[str, Any]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    gi = raw.get("gameInfo") or {}
    if isinstance(gi.get("venue"), dict):
        candidates.append(gi["venue"])
    header = raw.get("header") or {}
    for c in header.get("competitions") or []:
        if isinstance((c or {}).get("venue"), dict):
            candidates.append(c["venue"])
    for v in candidates:
        addr = v.get("address") or {}
        city = str(addr.get("city") or v.get("city") or "").strip()
        country = str(addr.get("country") or addr.get("countryCode") or v.get("country") or "").strip()
        name = str(v.get("fullName") or v.get("name") or "").strip()
        if city or name:
            return {"name": name or None, "city": city or None, "country": country or None}
    return None


def parse_official(raw: dict[str, Any]) -> str | None:
    gi = raw.get("gameInfo") or {}
    for q in gi.get("officials") or raw.get("officials") or []:
        if not isinstance(q, dict):
            continue
        role = str(q.get("position") or q.get("type") or q.get("role") or "").lower()
        official = q.get("official") if isinstance(q.get("official"), dict) else {}
        name = str(q.get("displayName") or q.get("fullName") or q.get("name") or official.get("displayName") or "").strip()
        if name and (not role or "ref" in role or "official" in role):
            return name
    return None


def summary_url(event: dict[str, Any]) -> str:
    return f"https://site.api.espn.com/apis/site/v2/sports/soccer/{event['espnLeague']}/summary?event={urllib.parse.quote(str(event['id']))}"


def normalize_summary(raw: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    hf = recursive_formations(raw, str(event.get("homeId")))
    af = recursive_formations(raw, str(event.get("awayId")))
    return {
        "eventId": str(event.get("id") or ""),
        "date": event.get("date"),
        "homeId": event.get("homeId"),
        "awayId": event.get("awayId"),
        "teamStats": parse_team_stats(raw),
        "players": parse_player_stats(raw),
        "formations": {str(event.get("homeId")): (hf[0] if hf else None), str(event.get("awayId")): (af[0] if af else None)},
        "venue": parse_venue(raw),
        "referee": parse_official(raw),
    }


def get_summary_norm(event: dict[str, Any], cache: dict[str, Any], force: bool = False) -> dict[str, Any] | None:
    k = str(event.get("id") or "")
    now = time.time()
    old = (cache.get("summaries") or {}).get(k)
    if old and not force and now - float(old.get("cachedAt") or 0) < 7 * 86400:
        return old.get("data")
    try:
        raw = p.http_json(summary_url(event), 18, 2)
        norm = normalize_summary(raw if isinstance(raw, dict) else {}, event)
        cache.setdefault("summaries", {})[k] = {"cachedAt": now, "data": norm}
        return norm
    except Exception:
        return (old or {}).get("data")


def previous_events(event: dict[str, Any], side: str, year: int, pcache: dict[str, Any], n: int = 10) -> list[dict[str, Any]]:
    tid = event["homeId"] if side == "home" else event["awayId"]
    kickoff = p.parse_dt(event.get("date"))
    if not kickoff:
        return []
    rows: list[dict[str, Any]] = []
    for sy in (year, year - 1, year + 1):
        try:
            sched = p.get_team_schedule(event["espnLeague"], tid, sy, pcache)
        except Exception:
            sched = []
        for raw in sched:
            er = p.event_record(raw, event["league"], event["espnLeague"])
            if not er or er.get("id") == event.get("id") or not er.get("completed"):
                continue
            when = p.parse_dt(er.get("date"))
            if not when or when >= kickoff:
                continue
            rows.append(er)
    byid = {str(x.get("id")): x for x in rows if x.get("id")}
    return sorted(byid.values(), key=lambda x: x.get("date") or "")[-n:]


def ewmean(vals: list[float], decay: float = 0.86) -> float | None:
    if not vals:
        return None
    num = den = 0.0
    for i, v in enumerate(vals):
        age = len(vals) - 1 - i
        w = decay ** age
        num += w * v
        den += w
    return num / den if den else None


def team_recent_profile(team_id: str, prev: list[dict[str, Any]], cache: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for e in prev:
        sm = get_summary_norm(e, cache)
        if not sm:
            continue
        stats = sm.get("teamStats") or {}
        own = stats.get(str(team_id)) or {}
        opp_id = str(e.get("awayId")) if str(e.get("homeId")) == str(team_id) else str(e.get("homeId"))
        opp = stats.get(opp_id) or {}
        rows.append({"event": e, "summary": sm, "own": own, "opp": opp})
    metrics: dict[str, Any] = {"n": len(rows)}
    for k in ("shots", "shots_on_target", "corners", "fouls", "yellow_cards", "red_cards"):
        vf = [float(x["own"][k]) for x in rows if x["own"].get(k) is not None]
        va = [float(x["opp"][k]) for x in rows if x["opp"].get(k) is not None]
        metrics[k + "For"] = ewmean(vf)
        metrics[k + "Against"] = ewmean(va)
        metrics[k + "N"] = min(len(vf), len(va)) if vf and va else max(len(vf), len(va))
    forms = [str((x["summary"].get("formations") or {}).get(str(team_id)) or "") for x in rows]
    forms = [x for x in forms if x]
    if forms:
        score: dict[str, float] = defaultdict(float)
        for i, f in enumerate(forms):
            score[f] += 0.86 ** (len(forms) - 1 - i)
        metrics["recentFormation"] = max(score, key=score.get)
        metrics["formationHistory"] = forms[-6:]
        metrics["formationStability"] = score[metrics["recentFormation"]] / max(1e-9, sum(score.values()))
    else:
        metrics["recentFormation"] = None
        metrics["formationHistory"] = []
        metrics["formationStability"] = None
    return metrics, rows


def geocode(city: str | None, country: str | None, cache: dict[str, Any]) -> tuple[float, float] | None:
    if not city:
        return None
    key = nkey(f"{city} {country or ''}")
    old = (cache.get("geocode") or {}).get(key)
    if isinstance(old, list) and len(old) == 2:
        return float(old[0]), float(old[1])
    q = urllib.parse.quote(city)
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=5&language=en&format=json"
    try:
        raw = p.http_json(url, 15, 2)
        cand = raw.get("results") or [] if isinstance(raw, dict) else []
        ranked = sorted(cand, key=lambda x: -float(x.get("population") or 0))
        if country:
            cc = nkey(country)
            ranked = sorted(ranked, key=lambda x: nkey(str(x.get("country") or x.get("country_code") or "")) != cc)
        if ranked:
            loc = [float(ranked[0]["latitude"]), float(ranked[0]["longitude"])]
            cache.setdefault("geocode", {})[key] = loc
            return loc[0], loc[1]
    except Exception:
        pass
    return None


def team_home_venue(event: dict[str, Any], team_id: str, cache: dict[str, Any]) -> dict[str, Any] | None:
    key = f"{event['espnLeague']}|{team_id}"
    old = (cache.get("teamVenue") or {}).get(key)
    if isinstance(old, dict):
        return old
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{event['espnLeague']}/teams/{urllib.parse.quote(team_id)}"
    try:
        raw = p.http_json(url, 15, 2)
        team = raw.get("team") or raw
        venue = team.get("venue") or {}
        addr = venue.get("address") or {}
        out = {"name": venue.get("fullName") or venue.get("name"), "city": addr.get("city") or team.get("location"), "country": addr.get("country") or addr.get("countryCode")}
        cache.setdefault("teamVenue", {})[key] = out
        return out
    except Exception:
        return old if isinstance(old, dict) else None


def travel_profile(event: dict[str, Any], team_id: str, current_venue: dict[str, Any] | None, prev_rows: list[dict[str, Any]], cache: dict[str, Any]) -> dict[str, Any]:
    homev = team_home_venue(event, team_id, cache)
    cur = geocode((current_venue or {}).get("city"), (current_venue or {}).get("country"), cache)
    base = geocode((homev or {}).get("city"), (homev or {}).get("country"), cache)
    lastv = None
    if prev_rows:
        v = (prev_rows[-1].get("summary") or {}).get("venue")
        lastv = geocode((v or {}).get("city"), (v or {}).get("country"), cache)
    bkm = haversine_km(base, cur)
    lkm = haversine_km(lastv, cur)
    return {"currentVenue": current_venue, "homeVenue": homev, "homeBaseToFixtureKm": round(bkm, 1) if bkm is not None else None, "lastVenueToFixtureKm": round(lkm, 1) if lkm is not None else None, "sourceKnown": bool(cur and (base or lastv)), "semantics": "great-circle venue-city distance; not a flight-path estimate"}


def understat_players(league: str, year: int, cache: dict[str, Any]) -> list[dict[str, Any]]:
    code = UNDERSTAT.get(league)
    if not code:
        return []
    key = f"{code}|{year}"
    old = (cache.get("understat") or {}).get(key)
    now = time.time()
    if old and now - float(old.get("cachedAt") or 0) < 12 * 3600:
        return old.get("players") or []
    url = f"https://understat.com/getLeagueData/{code}/{year}"
    try:
        raw = p.http_json(url, 25, 2)
        rows = raw.get("players") or [] if isinstance(raw, dict) else []
        cache.setdefault("understat", {})[key] = {"cachedAt": now, "players": rows}
        return rows
    except Exception:
        return (old or {}).get("players") or []


def match_understat_player(name: str, team: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    nk, tk = nkey(name), nkey(team)
    cand: list[tuple[float, dict[str, Any]]] = []
    nt = set(nk.split())
    for r in rows:
        rn = nkey(str(r.get("player_name") or r.get("player") or ""))
        if not rn:
            continue
        rt = nkey(str(r.get("team_title") or r.get("team") or ""))
        a, b = set(rn.split()), nt
        score = 1.0 if rn == nk else len(a & b) / max(1, len(a | b))
        if rt and tk and rt != tk:
            score -= 0.15
        if score >= 0.55:
            cand.append((score, r))
    cand.sort(key=lambda x: x[0], reverse=True)
    return cand[0][1] if cand else None


def player_prop_rows(team: str, expected_xi: list[str], us_rows: list[dict[str, Any]], recent_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recent: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    recent_games: dict[str, int] = defaultdict(int)
    for x in recent_rows:
        sm = x.get("summary") or {}
        for side in (sm.get("players") or {}).values():
            for q in side.values():
                key = nkey(q.get("name") or "")
                if not key:
                    continue
                st = q.get("stats") or {}
                if st:
                    recent_games[key] += 1
                    for k in ("minutes", "shots", "shots_on_target", "goals", "yellow_cards", "red_cards"):
                        if st.get(k) is not None:
                            recent[key][k] += float(st[k])
    out: list[dict[str, Any]] = []
    for name in expected_xi:
        u = match_understat_player(name, team, us_rows)
        tm = fnum((u or {}).get("time")) or 0.0
        games = fnum((u or {}).get("games")) or 0.0
        avg_min = clamp(tm / games if games > 0 else 78.0, 55.0, 90.0)
        shots = fnum((u or {}).get("shots"))
        xg = fnum((u or {}).get("xG"))
        goals = fnum((u or {}).get("goals"))
        lam_shots = max(0.05, (shots / tm * avg_min) if shots is not None and tm > 90 else 0.65)
        lam_goal = max(0.005, (xg / tm * avg_min) if xg is not None and tm > 90 else ((goals / tm * avg_min) if goals is not None and tm > 90 else 0.08))
        rr = recent.get(nkey(name)) or {}
        rshots = rr.get("shots") or 0.0
        rsot = rr.get("shots_on_target")
        if rsot is not None and rshots >= 3:
            sot_share = clamp(rsot / rshots, 0.12, 0.72)
        else:
            pos = str((u or {}).get("position") or "").upper()
            sot_share = 0.39 if "FW" in pos or "F" == pos else 0.34 if "M" in pos else 0.24
        lam_sot = max(0.03, lam_shots * sot_share)
        yc = fnum((u or {}).get("yellow_cards")) or 0.0
        lam_card = max(0.01, yc / tm * avg_min if tm > 90 else 0.08)
        out.append({"name": name, "understatId": (u or {}).get("id"), "position": (u or {}).get("position"), "minutesEstimate": round(avg_min, 1), "lambdaShots": round(lam_shots, 4), "lambdaSOT": round(lam_sot, 4), "lambdaGoalRaw": round(lam_goal, 4), "lambdaCard": round(lam_card, 4), "pShot1Plus": poisson_tail(lam_shots, 1), "pShot2Plus": poisson_tail(lam_shots, 2), "pShot3Plus": poisson_tail(lam_shots, 3), "pSOT1Plus": poisson_tail(lam_sot, 1), "pSOT2Plus": poisson_tail(lam_sot, 2), "pAnytimeGoalRaw": 1.0 - math.exp(-lam_goal), "pCardRaw": 1.0 - math.exp(-lam_card), "recentEspnStatMatches": recent_games.get(nkey(name), 0), "source": "Understat season rate + ESPN recent SOT when available"})
    return out


def event_from_ctx(row: dict[str, Any]) -> dict[str, Any] | None:
    league = str(row.get("league") or "")
    espn = p.ESPN_LEAGUES.get(league)
    hd, ad = row.get("homeDetail") or {}, row.get("awayDetail") or {}
    if not espn or not hd.get("teamId") or not ad.get("teamId"):
        return None
    return {"id": str(row.get("eventId") or ""), "date": row.get("kickoff") or "", "league": league, "espnLeague": espn, "home": row.get("home") or hd.get("team") or "", "away": row.get("away") or ad.get("team") or "", "homeId": str(hd.get("teamId") or ""), "awayId": str(ad.get("teamId") or "")}


def fixture_market_intel(ctx: dict[str, Any], year: int, pcache: dict[str, Any], cache: dict[str, Any]) -> dict[str, Any] | None:
    e = event_from_ctx(ctx)
    if not e:
        return None
    current = get_summary_norm(e, cache, force=True)
    venue = (current or {}).get("venue")
    referee = (current or {}).get("referee")
    us = understat_players(e["league"], year, cache)
    sides: dict[str, Any] = {}
    for side in ("home", "away"):
        tid = e["homeId"] if side == "home" else e["awayId"]
        name = e["home"] if side == "home" else e["away"]
        prev = previous_events(e, side, year, pcache, 10)
        prof, rr = team_recent_profile(tid, prev, cache)
        confirmed_form = (current or {}).get("formations", {}).get(tid)
        snap = (ctx.get(side + "Detail") or {}).get("snapshot") or {}
        expected_xi = snap.get("expectedXI") or []
        players = player_prop_rows(name, expected_xi, us, rr)
        sides[side] = {"teamId": tid, "team": name, "recent": prof, "formation": {"confirmed": confirmed_form, "expected": confirmed_form or prof.get("recentFormation"), "recentMode": prof.get("recentFormation"), "stability": prof.get("formationStability"), "history": prof.get("formationHistory"), "source": "ESPN confirmed summary" if confirmed_form else "recency-weighted prior ESPN formations"}, "travel": travel_profile(e, tid, venue, rr, cache), "players": players}
    h, a = sides["home"]["recent"], sides["away"]["recent"]
    def combine(metric: str) -> tuple[float | None, float | None]:
        hf, aa = h.get(metric + "For"), a.get(metric + "Against")
        af, ha = a.get(metric + "For"), h.get(metric + "Against")
        hm = (float(hf) + float(aa)) / 2 if hf is not None and aa is not None else hf if hf is not None else aa
        am = (float(af) + float(ha)) / 2 if af is not None and ha is not None else af if af is not None else ha
        return hm, am
    hc, ac = combine("corners")
    hy, ay = combine("yellow_cards")
    hs, ash = combine("shots")
    hst, ast = combine("shots_on_target")
    return {"eventId": e["id"], "league": e["league"], "home": e["home"], "away": e["away"], "kickoff": e["date"], "fetchedAt": p.iso_now(), "venue": venue, "referee": referee, "homeDetail": sides["home"], "awayDetail": sides["away"], "eventMarkets": {"corners": {"homeLambda": hc, "awayLambda": ac, "totalLambda": (hc + ac if hc is not None and ac is not None else None)}, "yellowCards": {"homeLambda": hy, "awayLambda": ay, "totalLambda": (hy + ay if hy is not None and ay is not None else None)}, "shots": {"homeLambda": hs, "awayLambda": ash, "totalLambda": (hs + ash if hs is not None and ash is not None else None)}, "shotsOnTarget": {"homeLambda": hst, "awayLambda": ast, "totalLambda": (hst + ast if hst is not None and ast is not None else None)}}, "readiness": {"playerProps": bool(sides["home"]["players"] or sides["away"]["players"]), "corners": hc is not None and ac is not None, "cards": hy is not None and ay is not None, "formation": bool(sides["home"]["formation"]["expected"] and sides["away"]["formation"]["expected"]), "travel": bool(sides["home"]["travel"]["sourceKnown"] and sides["away"]["travel"]["sourceKnown"])}, "policy": {"bookmakerOddsUsed": False, "feedsFrozenModel": False, "candidateForHBT13": True}}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ctx = read_json(PREXI, {})
    cache = read_json(CACHE_PATH, {"summaries": {}, "geocode": {}, "teamVenue": {}, "understat": {}})
    pcache = p.read_cache()
    year = int(ctx.get("seasonStartYear") or p.season_start_year())
    fixtures: dict[str, Any] = {}
    errors: list[str] = []
    for key, row in (ctx.get("fixtures") or {}).items():
        try:
            z = fixture_market_intel(row, year, pcache, cache)
            if z:
                fixtures[key] = z
        except Exception as exc:
            errors.append(f"{key}: {exc}")
    payload = {"schemaVersion": SCHEMA, "researchVersion": VERSION, "generatedAt": p.iso_now(), "seasonStartYear": year, "policy": {"researchOnlyUntilValidated": True, "feedsFrozenPrediction": False, "oddsUsed": False, "playerModel": "Understat season shots/xG rates + ESPN recent SOT where exposed; expected-XI scoped", "cornerCardModel": "causal recent team for/against rates; historical calibration is a separate promotion gate", "formation": "actual ESPN formation when exposed; otherwise recency-weighted prior actual formations", "travel": "club-base and previous-venue to fixture venue-city great-circle distance"}, "fixtures": fixtures, "errors": errors[:50]}
    write_json(OUTPUT, payload)
    sm = cache.get("summaries") or {}
    if len(sm) > 4000:
        items = sorted(sm.items(), key=lambda kv: float((kv[1] or {}).get("cachedAt") or 0), reverse=True)[:4000]
        cache["summaries"] = dict(items)
    write_json(CACHE_PATH, cache)
    p.write_json(p.CACHE_PATH, pcache)
    m = read_json(MANIFEST, {"schemaVersion": SCHEMA, "files": {}, "freshness": {}, "policy": {}})
    m.setdefault("files", {})["marketIntelligence"] = OUTPUT.name
    m.setdefault("freshness", {})["marketIntelligenceMaxAgeMinutes"] = 60
    m.setdefault("policy", {})["marketIntelligence"] = "HBT-1.3R player props + corners/cards + formation + travel; candidate only until causal validation"
    m["marketResearchVersion"] = VERSION
    write_json(MANIFEST, m)
    rd = [x.get("readiness") or {} for x in fixtures.values()]
    print("HBT-1.3 market intel:", len(fixtures), "fixtures;", sum(bool(x.get("playerProps")) for x in rd), "player;", sum(bool(x.get("corners")) for x in rd), "corners;", sum(bool(x.get("cards")) for x in rd), "cards;", sum(bool(x.get("formation")) for x in rd), "formation;", sum(bool(x.get("travel")) for x in rd), "travel; errors", len(errors))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
