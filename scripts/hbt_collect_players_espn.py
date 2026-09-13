#!/usr/bin/env python3
"""HBT-1.1 ESPN confirmed-XI fallback collector.

GitHub-hosted runners are currently blocked by SofaScore (HTTP 403). This
collector uses ESPN's anonymous soccer JSON endpoints instead and writes the
same normalized player_features.json contract expected by the Forecast Desk.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hbt_live_data"
CACHE_PATH = OUT / "_espn_player_cache.json"
SCHEMA = "HBT-LIVE-DATA-1"
ESPN_LEAGUES = {
    "en.1": "eng.1",
    "es.1": "esp.1",
    "de.1": "ger.1",
    "it.1": "ita.1",
    "fr.1": "fra.1",
}
STATUS_WEIGHT = {"starting": 1.0, "sub_in": 0.58, "bench": 0.18, "not_in_squad": 0.03}
IMPORTANCE_WINDOW = 10
IMPORTANCE_HALF_LIFE = 5
IMPORTANCE_SHRINK = 3
MIN_PRIOR_MATCHDAYS = 3


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def http_json(url: str, timeout: int = 25, retries: int = 3) -> Any:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8-sig"))
        except Exception as exc:
            last = exc
            if attempt + 1 < retries:
                time.sleep(0.8 + attempt * 1.2)
    raise RuntimeError(f"fetch failed {url}: {last}")


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c))


def team_key(s: str) -> str:
    s = strip_accents(s).lower().replace("&", " and ")
    s = re.sub(r"\b(fc|cf|afc|ssc|ac|fk|sk|sv|club)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def read_cache() -> dict[str, Any]:
    try:
        d = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            raise ValueError
        d.setdefault("summaries", {})
        d.setdefault("schedules", {})
        return d
    except Exception:
        return {"summaries": {}, "schedules": {}}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def parse_dt(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def competitor_sides(event: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    comps = event.get("competitions") or []
    if not comps:
        return None, None
    cs = comps[0].get("competitors") or []
    h = next((x for x in cs if x.get("homeAway") == "home"), None)
    a = next((x for x in cs if x.get("homeAway") == "away"), None)
    return h, a


def event_record(event: dict[str, Any], league_code: str, espn_code: str) -> dict[str, Any] | None:
    h, a = competitor_sides(event)
    if not h or not a:
        return None
    ht, at = h.get("team") or {}, a.get("team") or {}
    status = ((event.get("status") or {}).get("type") or {})
    return {
        "id": str(event.get("id") or ""),
        "date": event.get("date") or "",
        "league": league_code,
        "espnLeague": espn_code,
        "state": str(status.get("state") or "").lower(),
        "completed": bool(status.get("completed") is True or str(status.get("state") or "").lower() == "post"),
        "homeId": str(ht.get("id") or ""), "awayId": str(at.get("id") or ""),
        "home": ht.get("displayName") or ht.get("name") or "",
        "away": at.get("displayName") or at.get("name") or "",
    }


def normalize_pos(row: dict[str, Any]) -> str:
    p = row.get("position") or (row.get("athlete") or {}).get("position") or {}
    if isinstance(p, str):
        raw = p
    else:
        raw = p.get("abbreviation") or p.get("name") or p.get("displayName") or ""
    s = strip_accents(str(raw)).upper().strip()
    if s in {"G", "GK", "GOALKEEPER"} or "GOAL" in s:
        return "GK"
    if s in {"D", "DF", "DEF"} or "DEF" in s or "BACK" in s:
        return "DEF"
    if s in {"M", "MF", "MID"} or "MID" in s:
        return "MID"
    if s in {"F", "FW", "ATT"} or "FORWARD" in s or "STRIK" in s or "WING" in s:
        return "ATT"
    return s[:8]


def normalize_roster(roster_obj: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in roster_obj.get("roster") or roster_obj.get("athletes") or []:
        ath = row.get("athlete") or row
        pid = ath.get("id") or row.get("id") or ath.get("displayName") or ath.get("fullName")
        if pid is None:
            continue
        starter = row.get("starter") is True
        subbed_in = row.get("subbedIn") is True or row.get("substitute") is True
        status = "starting" if starter else ("sub_in" if subbed_in else "bench")
        out.append({
            "id": str(pid),
            "name": ath.get("displayName") or ath.get("fullName") or ath.get("shortName") or "",
            "pos": normalize_pos(row),
            "status": status,
        })
    return out


def summary_lineup(raw: dict[str, Any], home_id: str, away_id: str) -> dict[str, Any] | None:
    rosters = raw.get("rosters") or []
    sides: dict[str, list[dict[str, Any]]] = {"home": [], "away": []}
    unresolved: list[list[dict[str, Any]]] = []
    for r in rosters:
        players = normalize_roster(r)
        team = r.get("team") or {}
        tid = str(team.get("id") or "")
        ha = str(r.get("homeAway") or "").lower()
        if tid and tid == home_id:
            sides["home"] = players
        elif tid and tid == away_id:
            sides["away"] = players
        elif ha in sides:
            sides[ha] = players
        else:
            unresolved.append(players)
    if not sides["home"] and unresolved:
        sides["home"] = unresolved.pop(0)
    if not sides["away"] and unresolved:
        sides["away"] = unresolved.pop(0)
    confirmed = sum(x.get("status") == "starting" for x in sides["home"]) >= 10 and sum(x.get("status") == "starting" for x in sides["away"]) >= 10
    if not sides["home"] and not sides["away"]:
        return None
    return {"confirmed": confirmed, **sides}


def get_summary(event: dict[str, Any], cache: dict[str, Any], force: bool = False) -> dict[str, Any] | None:
    eid = event["id"]
    old = cache.get("summaries", {}).get(eid)
    if old and old.get("confirmed") and not force:
        return old
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{event['espnLeague']}/summary?event={urllib.parse.quote(eid)}"
    try:
        raw = http_json(url, timeout=15, retries=2)
        norm = summary_lineup(raw, event["homeId"], event["awayId"])
        if norm and (norm.get("confirmed") or old is None):
            cache.setdefault("summaries", {})[eid] = norm
        return norm or old
    except Exception:
        return old


def get_team_schedule(league: str, team_id: str, year: int, cache: dict[str, Any]) -> list[dict[str, Any]]:
    key = f"{league}|{team_id}|{year}"
    old = cache.get("schedules", {}).get(key)
    now_ts = time.time()
    if old and now_ts - float(old.get("fetchedAtTs") or 0) < 6 * 3600:
        return old.get("events") or []
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/teams/{urllib.parse.quote(team_id)}/schedule?season={year}"
    try:
        raw = http_json(url, timeout=15, retries=2)
        events = raw.get("events") or []
        cache.setdefault("schedules", {})[key] = {"fetchedAtTs": now_ts, "events": events}
        return events
    except Exception:
        return (old or {}).get("events") or []


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


def prior_lineups_for_team(event: dict[str, Any], side: str, cache: dict[str, Any], year: int) -> list[list[dict[str, Any]]]:
    team_id = event["homeId"] if side == "home" else event["awayId"]
    kickoff = parse_dt(event.get("date")) or dt.datetime.now(dt.timezone.utc)
    sched = get_team_schedule(event["espnLeague"], team_id, year, cache)
    prev: list[dict[str, Any]] = []
    for e in sched:
        er = event_record(e, event["league"], event["espnLeague"])
        if not er or er["id"] == event["id"] or not er.get("completed"):
            continue
        edt = parse_dt(er.get("date"))
        if not edt or edt >= kickoff:
            continue
        prev.append(er)
    prev.sort(key=lambda x: x.get("date") or "")
    prev = prev[-6:]
    rows: list[list[dict[str, Any]]] = []
    for e in prev:
        lu = get_summary(e, cache, force=False)
        if not lu:
            continue
        eside = "home" if str(e.get("homeId")) == str(team_id) else "away"
        pl = lu.get(eside) or []
        if sum(x.get("status") == "starting" for x in pl) >= 10:
            rows.append(pl)
        time.sleep(0.04)
    return rows


def team_snapshot(event: dict[str, Any], side: str, current: dict[str, Any], cache: dict[str, Any], year: int) -> dict[str, Any] | None:
    hist = prior_lineups_for_team(event, side, cache, year)
    if len(hist) < MIN_PRIOR_MATCHDAYS:
        return None
    current_xi = [x for x in (current.get(side) or []) if x.get("status") == "starting"]
    if len(current_xi) < 10 or len(current_xi) > 12:
        return None
    universe: dict[str, dict[str, Any]] = {}
    for m in hist:
        for p in m:
            universe[str(p["id"])] = {"id": str(p["id"]), "name": p.get("name") or "", "pos": p.get("pos") or ""}
    for p in current.get(side) or []:
        universe[str(p["id"])] = {"id": str(p["id"]), "name": p.get("name") or "", "pos": p.get("pos") or ""}
    info = []
    for p in universe.values():
        sts = []
        for m in hist:
            found = next((x for x in m if str(x["id"]) == str(p["id"])), None)
            sts.append(found.get("status") if found else "not_in_squad")
        imp, n = player_importance(sts)
        info.append({**p, "importance": imp, "priorN": n})
    ideal = select_xi(info)
    if len(ideal) < 10:
        return None
    imap = {str(x["id"]): x for x in info}
    xi = [{**x, "importance": float((imap.get(str(x["id"])) or {}).get("importance") or 0)} for x in current_xi]
    prev_xi = [x for x in hist[-1] if x.get("status") == "starting"]
    cur_ids = {str(x["id"]) for x in xi}
    overlap = sum(1 for x in prev_xi if str(x["id"]) in cur_ids) / 11.0
    prev_gk = next((x for x in prev_xi if x.get("pos") == "GK"), None)
    cur_gk = next((x for x in xi if x.get("pos") == "GK"), None)
    same_gk = 1.0 if prev_gk and cur_gk and str(prev_gk["id"]) == str(cur_gk["id"]) else 0.0
    continuity = 0.85 * clip(overlap, 0, 1) + 0.15 * same_gk
    repl = replacement_quality(ideal, xi)
    return {"continuity": continuity, "replacementQuality": repl, "priorMatches": len(hist), "xi": [x.get("name") or "" for x in xi]}


def fetch_events_for_day(day: dt.date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    out: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    ds = day.strftime("%Y%m%d")
    for code, espn in ESPN_LEAGUES.items():
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{espn}/scoreboard?dates={ds}"
        try:
            raw = http_json(url, timeout=15, retries=2)
            events = raw.get("events") or []
            rows = [event_record(e, code, espn) for e in events]
            rows = [x for x in rows if x and x.get("id")]
            out.extend(rows)
            audit.append({"date": day.isoformat(), "league": code, "status": "loaded", "events": len(rows), "source": url})
        except Exception as exc:
            audit.append({"date": day.isoformat(), "league": code, "status": "failed", "events": 0, "source": url, "error": str(exc)})
    return out, audit


def prune_cache(cache: dict[str, Any]) -> None:
    sm = cache.get("summaries") or {}
    if len(sm) > 2500:
        keep = list(sm.keys())[-2500:]
        cache["summaries"] = {k: sm[k] for k in keep}
    sc = cache.get("schedules") or {}
    if len(sc) > 300:
        items = sorted(sc.items(), key=lambda kv: float((kv[1] or {}).get("fetchedAtTs") or 0), reverse=True)[:300]
        cache["schedules"] = dict(items)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    year = now.year if now.month >= 7 else now.year - 1
    cache = read_cache()
    features: dict[str, Any] = {}
    audit: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for delta in range(-1, 4):
        rows, a = fetch_events_for_day(now.date() + dt.timedelta(days=delta))
        events.extend(rows); audit.extend(a)

    seen: set[str] = set()
    for event in events:
        if event["id"] in seen:
            continue
        seen.add(event["id"])
        kick = parse_dt(event.get("date"))
        h = (kick - now).total_seconds()/3600 if kick else 999.0
        key = f"{(kick.date().isoformat() if kick else now.date().isoformat())}|{team_key(event['home'])}|{team_key(event['away'])}"
        base = {"ok": False, "eventId": event["id"], "league": event["league"], "home": event["home"], "away": event["away"], "fetchedAt": iso_now(), "source": "ESPN static collector"}
        if h > 3.0 or h < -2.0:
            features[key] = {**base, "reason": "outside confirmed-XI collection window"}
            continue
        lu = get_summary(event, cache, force=True)
        if not lu or not lu.get("confirmed"):
            features[key] = {**base, "reason": "confirmed XI not published by ESPN"}
            continue
        H = team_snapshot(event, "home", lu, cache, year)
        A = team_snapshot(event, "away", lu, cache, year)
        if not H or not A:
            features[key] = {**base, "reason": "insufficient recent ESPN lineup history"}
            continue
        features[key] = {**base, "ok": True, "continuityDiff": H["continuity"]-A["continuity"], "replacementQualityAdv": H["replacementQuality"]-A["replacementQuality"], "homeSnapshot": H, "awaySnapshot": A, "reason": ""}

    generated = iso_now()
    payload = {"schemaVersion": SCHEMA, "generatedAt": generated, "seasonStartYear": year, "features": features}
    write_json(OUT / "player_features.json", payload)
    prune_cache(cache)
    write_json(CACHE_PATH, cache)

    manifest_path = OUT / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        manifest = {"schemaVersion": SCHEMA, "files": {"performance": "performance.json", "players": "player_features.json"}, "freshness": {"performanceMaxAgeMinutes":1440,"confirmedXiMaxAgeMinutes":30}, "policy": {}}
    manifest["generatedAt"] = generated
    manifest["seasonStartYear"] = year
    manifest.setdefault("sourceAudit", {})["players"] = audit
    manifest.setdefault("policy", {})["playerSource"] = "ESPN anonymous site API fallback; SofaScore blocked on GitHub-hosted runners"
    write_json(manifest_path, manifest)

    loaded = sum(1 for x in audit if x.get("status") == "loaded")
    ok = sum(1 for x in features.values() if x.get("ok"))
    near = sum(1 for x in features.values() if "outside" not in str(x.get("reason") or ""))
    print(f"ESPN player feed {generated}: scoreboard slices {loaded}/{len(audit)} loaded; near-kickoff fixtures {near}; confirmed feature rows {ok}/{len(features)}")
    return 0 if loaded >= 20 else 2


if __name__ == "__main__":
    raise SystemExit(main())
