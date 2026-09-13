#!/usr/bin/env python3
"""HBT-1.1 static live-intelligence collector.

Runs outside the browser (GitHub Actions recommended), fetches the live sources,
normalizes them, and writes browser-safe JSON files under hbt_live_data/.

No bookmaker odds are fetched or written.
"""
from __future__ import annotations

import datetime as dt
import gzip
import html
import json
import math
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hbt_live_data"
OUT.mkdir(parents=True, exist_ok=True)
CACHE = OUT / "_collector_cache.json"

UA = "Mozilla/5.0 (compatible; HBT-Live-Data/1.1; +https://github.com/)"
SCHEMA = "HBT-LIVE-DATA-1"
LEAGUES = {
    "en.1": "EPL",
    "es.1": "La_liga",
    "de.1": "Bundesliga",
    "it.1": "Serie_A",
    "fr.1": "Ligue_1",
}

GENERIC = {
    "club", "clube", "football", "futbol", "fussball", "calcio", "societa",
    "sportiva", "de", "do", "del", "the", "as", "ss", "us", "rc", "sc",
    "sd", "cd", "ud", "bc", "bsc", "tsg", "fsv", "acf", "uc", "ea", "sco",
    "osc", "hsc", "ogc", "stade", "olympique", "girondins",
}
PERF_ALIAS = {
    "internazionale milano": "inter", "internazionale": "inter", "inter milan": "inter",
    "rasenballsport leipzig": "leipzig", "rb leipzig": "leipzig",
    "bayern munchen": "bayern", "bayern munich": "bayern",
    "borussia monchengladbach": "monchengladbach", "borussia m gladbach": "monchengladbach",
    "m gladbach": "monchengladbach", "lyonnais": "lyon", "rennais": "rennes",
    "strasbourg alsace": "strasbourg", "deportivo alaves": "alaves",
    "hellas verona": "verona", "chievo verona": "chievo", "hamburger": "hamburg",
    "koln": "cologne", "cologne": "cologne", "tottenham hotspur": "tottenham",
}
STATUS_WEIGHT = {"starting": 1.0, "sub_in": 0.58, "bench": 0.18, "not_in_squad": 0.03}
IMPORTANCE_WINDOW = 10
IMPORTANCE_HALF_LIFE = 5
IMPORTANCE_SHRINK = 3
MIN_PRIOR_MATCHDAYS = 3


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def season_start_year(now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.now(dt.timezone.utc)
    return now.year if now.month >= 7 else now.year - 1


def decode_body(raw: bytes, encoding: str | None) -> bytes:
    enc = (encoding or "").lower().strip()
    if enc == "gzip" or (len(raw) >= 2 and raw[:2] == b"\x1f\x8b"):
        return gzip.decompress(raw)
    if enc == "deflate":
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw


def http_json(url: str, timeout: int = 25, retries: int = 3) -> Any:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "application/json,text/plain,*/*",
                    "Accept-Encoding": "gzip, deflate",
                    "Referer": "https://understat.com/" if "understat.com" in url else "https://www.sofascore.com/",
                    "X-Requested-With": "XMLHttpRequest" if "understat.com" in url else "HBT-Collector",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = decode_body(r.read(), r.headers.get("Content-Encoding"))
                text = raw.decode("utf-8-sig")
                return json.loads(text)
        except Exception as exc:
            last = exc
            if attempt + 1 < retries:
                time.sleep(1.0 + attempt * 1.5)
    raise RuntimeError(f"fetch failed {url}: {last}")


def strip_accents(s: str) -> str:
    s = html.unescape(str(s or ""))
    s = s.replace("ø", "o").replace("Ø", "o").replace("æ", "ae").replace("Æ", "ae")
    s = s.replace("œ", "oe").replace("Œ", "oe").replace("ß", "ss").replace("ł", "l").replace("Ł", "l")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def base_team_key(s: str) -> str:
    s = strip_accents(s).lower().replace("&", " and ")
    s = re.sub(r"\b(fc|cf|afc|ssc|ac|fk|sk|sv)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def perf_team_key(s: str) -> str:
    toks = [t for t in base_team_key(s).split() if t and t not in GENERIC and not t.isdigit()]
    k = " ".join(toks)
    return PERF_ALIAS.get(k, k)


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def read_cache() -> dict[str, Any]:
    if not CACHE.exists():
        return {"lineups": {}, "teamEvents": {}}
    try:
        d = json.loads(CACHE.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            raise ValueError("bad cache")
        d.setdefault("lineups", {})
        d.setdefault("teamEvents", {})
        return d
    except Exception:
        return {"lineups": {}, "teamEvents": {}}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def normalize_understat_team(t: dict[str, Any]) -> dict[str, Any]:
    hist = []
    for x in t.get("history") or []:
        row = {
            "date": str(x.get("date") or "")[:10],
            "npxG": x.get("npxG"), "npxGA": x.get("npxGA"),
            "deep": x.get("deep"), "deep_allowed": x.get("deep_allowed"),
            "scored": x.get("scored"), "missed": x.get("missed"),
            "pts": x.get("pts"), "h_a": x.get("h_a"),
        }
        if row["date"]:
            hist.append(row)
    return {"title": t.get("title") or "", "history": hist}


def fetch_performance(year: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    packs: dict[str, Any] = {}
    audit: list[dict[str, Any]] = []
    for code, league in LEAGUES.items():
        url = f"https://understat.com/getLeagueData/{league}/{year}"
        try:
            raw = http_json(url)
            teams_raw = raw.get("teams") or {}
            vals = list(teams_raw.values()) if isinstance(teams_raw, dict) else list(teams_raw)
            teams = [normalize_understat_team(t) for t in vals if isinstance(t, dict)]
            teams = [t for t in teams if t["title"]]
            packs[code] = {
                "code": code, "league": league, "year": year,
                "source": url, "fetchedAt": iso_now(), "teams": teams,
            }
            audit.append({"code": code, "status": "loaded", "teams": len(teams), "source": url})
        except Exception as exc:
            audit.append({"code": code, "status": "failed", "teams": 0, "source": url, "error": str(exc)})
    return packs, audit


def event_summary(e: dict[str, Any], query_date: str | None = None) -> dict[str, Any]:
    return {
        "id": e.get("id"),
        "startTimestamp": e.get("startTimestamp"),
        "status": {"type": ((e.get("status") or {}).get("type"))},
        "homeTeam": {"id": (e.get("homeTeam") or {}).get("id"), "name": (e.get("homeTeam") or {}).get("name") or ""},
        "awayTeam": {"id": (e.get("awayTeam") or {}).get("id"), "name": (e.get("awayTeam") or {}).get("name") or ""},
        "queryDate": query_date,
    }


def tournament_name(e: dict[str, Any]) -> tuple[str, str]:
    t = e.get("tournament") or {}
    ut = t.get("uniqueTournament") or {}
    cat = t.get("category") or ut.get("category") or {}
    return str(ut.get("name") or t.get("name") or ""), str(cat.get("name") or "")


def classify_big5_event(e: dict[str, Any]) -> str | None:
    tn, cat = tournament_name(e)
    n = strip_accents(tn).lower()
    c = strip_accents(cat).lower()
    rules = [
        ("en.1", "england", ("premier league",)),
        ("es.1", "spain", ("laliga", "la liga", "primera division")),
        ("de.1", "germany", ("bundesliga",)),
        ("it.1", "italy", ("serie a",)),
        ("fr.1", "france", ("ligue 1",)),
    ]
    for code, country, names in rules:
        if country in c and any(x in n for x in names):
            return code
    return None


def normalize_lineup(raw: dict[str, Any]) -> dict[str, Any]:
    def side(name: str) -> list[dict[str, Any]]:
        out = []
        for x in (((raw.get(name) or {}).get("players")) or []):
            p = x.get("player") or {}
            pid = p.get("id") or x.get("id") or p.get("name")
            if pid is None:
                continue
            pos = x.get("position") or p.get("position") or ""
            sub = bool(x.get("substitute") is True or x.get("substitute") == 1)
            st = x.get("statistics") or {}
            mins = st.get("minutesPlayed", st.get("minutesPlayedTotal", 0)) or 0
            status = "sub_in" if sub and float(mins or 0) > 0 else ("bench" if sub else "starting")
            s = str(pos).upper()
            pos2 = {"G": "GK", "D": "DEF", "M": "MID", "F": "ATT"}.get(s, s)
            out.append({"id": str(pid), "name": p.get("name") or x.get("name") or "", "pos": pos2, "status": status})
        return out
    return {"confirmed": raw.get("confirmed") is True, "home": side("home"), "away": side("away")}


def get_lineup(event_id: int | str, cache: dict[str, Any], force: bool = False) -> dict[str, Any] | None:
    key = str(event_id)
    old = (cache.get("lineups") or {}).get(key)
    if old and old.get("confirmed") and not force:
        return old
    try:
        raw = http_json(f"https://api.sofascore.com/api/v1/event/{event_id}/lineups", timeout=10, retries=2)
        norm = normalize_lineup(raw)
        if norm.get("confirmed") or old is None:
            cache.setdefault("lineups", {})[key] = norm
        return norm
    except Exception:
        return old


def get_team_events(team_id: int | str, cache: dict[str, Any], now_ts: float) -> list[dict[str, Any]]:
    key = str(team_id)
    old = (cache.get("teamEvents") or {}).get(key)
    if old and now_ts - float(old.get("fetchedAtTs") or 0) < 3 * 3600:
        return old.get("events") or []
    ev: list[dict[str, Any]] = []
    for page in range(2):
        try:
            raw = http_json(f"https://api.sofascore.com/api/v1/team/{team_id}/events/last/{page}", timeout=10, retries=2)
            ev.extend(event_summary(x) for x in (raw.get("events") or []))
            if not raw.get("hasNextPage"):
                break
            time.sleep(0.08)
        except Exception:
            break
    cache.setdefault("teamEvents", {})[key] = {"fetchedAtTs": now_ts, "events": ev[:30]}
    return ev[:30]


def status_score(status: str) -> float:
    return STATUS_WEIGHT.get(status, 0.03)


def player_importance(statuses: list[str]) -> tuple[float, int]:
    prior = statuses[-IMPORTANCE_WINDOW:]
    if len(prior) < MIN_PRIOR_MATCHDAYS:
        return 0.0, len(prior)
    num = den = 0.0
    n = len(prior)
    for i, st in enumerate(prior):
        d = max(1, n - i)
        w = 0.5 ** (d / IMPORTANCE_HALF_LIFE)
        num += w * status_score(st)
        den += w
    raw = num / den if den else 0.0
    shrink = n / (n + IMPORTANCE_SHRINK)
    return raw * shrink, n


def select_xi(info: list[dict[str, Any]]) -> list[dict[str, Any]]:
    c = sorted(info, key=lambda x: float(x.get("importance") or 0), reverse=True)
    xi: list[dict[str, Any]] = []
    used: set[str] = set()
    gk = next((x for x in c if x.get("pos") == "GK"), None)
    if gk:
        xi.append(gk); used.add(str(gk["id"]))
    for x in c:
        if len(xi) >= 11:
            break
        if str(x["id"]) in used or x.get("pos") == "GK":
            continue
        xi.append(x); used.add(str(x["id"]))
    return xi


def replacement_quality(ideal: list[dict[str, Any]], xi: list[dict[str, Any]]) -> float:
    ideal_ids = {str(x["id"]) for x in ideal}
    xi_ids = {str(x["id"]) for x in xi}
    missing = [x for x in ideal if str(x["id"]) not in xi_ids]
    repls = [x for x in xi if str(x["id"]) not in ideal_ids]
    if not missing:
        return 1.0
    used: set[int] = set(); total = 0.0
    for m in missing:
        best = None; best_score = -1.0
        for i, r in enumerate(repls):
            if i in used:
                continue
            same = 1 if r.get("pos") == m.get("pos") else 0
            score = same * 10 + float(r.get("importance") or 0)
            if score > best_score:
                best_score = score; best = (i, r, same)
        if not best:
            continue
        i, r, same = best; used.add(i)
        positional = 1.0 if same else 0.55
        mi = float(m.get("importance") or 0)
        ratio = clip(float(r.get("importance") or 0) / mi, 0, 1.25) if mi > 0.03 else 1.0
        total += positional * ratio
    return clip(total / len(missing), 0, 1.25)


def team_player_snapshot(team_id: int | str, current_event_id: int | str, side: str,
                         current_lineup: dict[str, Any], fixture_ts: int,
                         cache: dict[str, Any], now_ts: float) -> dict[str, Any] | None:
    prev = []
    for e in get_team_events(team_id, cache, now_ts):
        if str(e.get("id")) == str(current_event_id):
            continue
        if fixture_ts and int(e.get("startTimestamp") or 0) >= fixture_ts:
            continue
        if str(((e.get("status") or {}).get("type") or "")).lower() != "finished":
            continue
        prev.append(e)
    prev.sort(key=lambda e: int(e.get("startTimestamp") or 0))
    prev = prev[-6:]
    if len(prev) < MIN_PRIOR_MATCHDAYS:
        return None
    match_sides: list[list[dict[str, Any]]] = []
    for e in prev:
        lu = get_lineup(e["id"], cache)
        if not lu:
            continue
        eside = "home" if str((e.get("homeTeam") or {}).get("id")) == str(team_id) else "away"
        pl = lu.get(eside) or []
        if sum(1 for x in pl if x.get("status") == "starting") >= 10:
            match_sides.append(pl)
        time.sleep(0.05)
    if len(match_sides) < MIN_PRIOR_MATCHDAYS:
        return None
    current = current_lineup.get(side) or []
    current_xi = [x for x in current if x.get("status") == "starting"]
    if len(current_xi) < 10 or len(current_xi) > 12:
        return None
    universe: dict[str, dict[str, Any]] = {}
    for m in match_sides:
        for p in m:
            universe[str(p["id"])] = {"id": str(p["id"]), "name": p.get("name") or "", "pos": p.get("pos") or ""}
    for p in current:
        universe[str(p["id"])] = {"id": str(p["id"]), "name": p.get("name") or "", "pos": p.get("pos") or ""}
    info = []
    for p in universe.values():
        statuses = []
        for m in match_sides:
            found = next((x for x in m if str(x["id"]) == str(p["id"])), None)
            statuses.append(found.get("status") if found else "not_in_squad")
        imp, n = player_importance(statuses)
        info.append({**p, "importance": imp, "priorN": n})
    ideal = select_xi(info)
    if len(ideal) < 10:
        return None
    imap = {str(x["id"]): x for x in info}
    xi = [{**x, "importance": float((imap.get(str(x["id"])) or {}).get("importance") or 0),
           "priorN": int((imap.get(str(x["id"])) or {}).get("priorN") or 0)} for x in current_xi]
    prev_xi = [x for x in match_sides[-1] if x.get("status") == "starting"]
    cur_ids = {str(x["id"]) for x in xi}
    overlap = sum(1 for x in prev_xi if str(x["id"]) in cur_ids) / 11.0
    prev_gk = next((x for x in prev_xi if x.get("pos") == "GK"), None)
    cur_gk = next((x for x in xi if x.get("pos") == "GK"), None)
    same_gk = 1.0 if prev_gk and cur_gk and str(prev_gk["id"]) == str(cur_gk["id"]) else 0.0
    continuity = 0.85 * clip(overlap, 0, 1) + 0.15 * same_gk
    repl = replacement_quality(ideal, xi)
    return {"continuity": continuity, "replacementQuality": repl,
            "priorMatches": len(match_sides), "xi": [x.get("name") or "" for x in xi]}


def fetch_player_features(cache: dict[str, Any], days_back: int = 1, days_forward: int = 3) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    now = dt.datetime.now(dt.timezone.utc)
    now_ts = now.timestamp()
    features: dict[str, Any] = {}
    audit: list[dict[str, Any]] = []
    seen_events: set[str] = set()
    for delta in range(-days_back, days_forward + 1):
        day = (now.date() + dt.timedelta(days=delta)).isoformat()
        url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{day}"
        try:
            raw = http_json(url, timeout=12, retries=2)
            events = raw.get("events") or []
            b5 = [(e, classify_big5_event(e)) for e in events]
            b5 = [(e, c) for e, c in b5 if c]
            audit.append({"date": day, "status": "loaded", "events": len(events), "bigFive": len(b5), "source": url})
        except Exception as exc:
            audit.append({"date": day, "status": "failed", "events": 0, "bigFive": 0, "source": url, "error": str(exc)})
            continue
        for e, code in b5:
            eid = e.get("id")
            if eid is None or str(eid) in seen_events:
                continue
            seen_events.add(str(eid))
            home = (e.get("homeTeam") or {}).get("name") or ""
            away = (e.get("awayTeam") or {}).get("name") or ""
            key = f"{day}|{perf_team_key(home)}|{perf_team_key(away)}"
            base = {"ok": False, "eventId": eid, "league": code, "home": home, "away": away,
                    "fetchedAt": iso_now(), "source": "SofaScore static collector"}
            ts = int(e.get("startTimestamp") or 0)
            hours_to_kickoff = (ts - now_ts) / 3600.0 if ts else 999.0
            if hours_to_kickoff > 3.0 or hours_to_kickoff < -2.0:
                features[key] = {**base, "reason": "outside confirmed-XI collection window"}
                continue
            lu = get_lineup(eid, cache, force=True)
            if not lu or not lu.get("confirmed"):
                features[key] = {**base, "reason": "confirmed XI not published"}
                continue
            hid = (e.get("homeTeam") or {}).get("id")
            aid = (e.get("awayTeam") or {}).get("id")
            if hid is None or aid is None:
                features[key] = {**base, "reason": "team id missing in lineup source"}
                continue
            H = team_player_snapshot(hid, eid, "home", lu, ts, cache, now_ts)
            A = team_player_snapshot(aid, eid, "away", lu, ts, cache, now_ts)
            if not H or not A:
                features[key] = {**base, "reason": "insufficient recent confirmed-lineup history"}
                continue
            features[key] = {
                **base, "ok": True,
                "continuityDiff": H["continuity"] - A["continuity"],
                "replacementQualityAdv": H["replacementQuality"] - A["replacementQuality"],
                "homeSnapshot": H, "awaySnapshot": A,
                "reason": "",
            }
            time.sleep(0.08)
    return features, audit


def prune_cache(cache: dict[str, Any]) -> None:
    lineups = cache.get("lineups") or {}
    if len(lineups) > 2500:
        keys = list(lineups.keys())[-2500:]
        cache["lineups"] = {k: lineups[k] for k in keys}
    te = cache.get("teamEvents") or {}
    if len(te) > 300:
        items = sorted(te.items(), key=lambda kv: float((kv[1] or {}).get("fetchedAtTs") or 0), reverse=True)[:300]
        cache["teamEvents"] = dict(items)


def main() -> int:
    year = season_start_year()
    generated = iso_now()
    cache = read_cache()
    perf, perf_audit = fetch_performance(year)
    player_features, player_audit = fetch_player_features(cache)
    prune_cache(cache)

    performance_payload = {
        "schemaVersion": SCHEMA, "generatedAt": generated,
        "seasonStartYear": year, "leagues": perf,
    }
    players_payload = {
        "schemaVersion": SCHEMA, "generatedAt": generated,
        "seasonStartYear": year, "features": player_features,
    }
    manifest = {
        "schemaVersion": SCHEMA,
        "generatedAt": generated,
        "seasonStartYear": year,
        "files": {"performance": "performance.json", "players": "player_features.json"},
        "freshness": {"performanceMaxAgeMinutes": 1440, "confirmedXiMaxAgeMinutes": 30},
        "sourceAudit": {"performance": perf_audit, "players": player_audit},
        "policy": {
            "odds": "excluded",
            "missingConfirmedXi": "use separately-trained PRE-XI Fusion; never substitute zero player intelligence",
            "browserDirectExternalFetches": False,
        },
    }
    write_json(OUT / "performance.json", performance_payload)
    write_json(OUT / "player_features.json", players_payload)
    write_json(OUT / "manifest.json", manifest)
    write_json(CACHE, cache)

    ok_perf = sum(1 for x in perf_audit if x.get("status") == "loaded")
    ok_players = sum(1 for x in player_features.values() if x.get("ok"))
    print(f"HBT live data {generated}: performance {ok_perf}/{len(LEAGUES)} leagues; "
          f"player features {ok_players}/{len(player_features)} confirmed-XI fixtures")
    if ok_perf < 5:
        print("WARNING: not all Big-Five performance feeds loaded", file=sys.stderr)
    return 0 if ok_perf >= 4 else 2


if __name__ == "__main__":
    raise SystemExit(main())
