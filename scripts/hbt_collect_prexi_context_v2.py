#!/usr/bin/env python3
"""HBT-1.2R-R2 research-only P1/manager collector hardening.

This wraps the R1 collector without changing HBT-1.1.2 predictions. It adds:
- previous-season Transfermarkt availability archive seeding for expected-XI history,
- safer EPL/FPL state classification (departed != injured),
- additional ESPN manager endpoint fallbacks,
- explicit source-readiness flags in the emitted shadow feed.

All new fields remain SHADOW ONLY until causal validation/promotion.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import hbt_collect_players_espn as p
import hbt_collect_prexi_context as base

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hbt_live_data"
ARCHIVE_CACHE_PATH = OUT / "_availability_archive_cache.json"
ARCHIVE_REPO = "https://api.github.com/repos/withqwerty/availability-data/contents"
ARCHIVE_LEAGUE = {
    "en.1": "GB1",
    "es.1": "ES1",
    "de.1": "L1",
    "it.1": "IT1",
    "fr.1": "FR1",
}


def read_cache() -> dict[str, Any]:
    try:
        d = json.loads(ARCHIVE_CACHE_PATH.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def write_cache(d: dict[str, Any]) -> None:
    p.write_json(ARCHIVE_CACHE_PATH, d)


_archive_cache = read_cache()
_dir_cache: dict[str, list[dict[str, Any]]] = {}


def _tokens(s: str) -> set[str]:
    k = p.team_key(str(s or "").replace("-", " "))
    aliases = {
        "internazionale milano": "internazionale",
        "inter milan": "internazionale",
        "paris saint germain": "paris saint germain",
        "bayern munchen": "bayern munich",
        "borussia monchengladbach": "borussia gladbach",
        "athletic bilbao": "athletic club",
        "real sociedad de futbol": "real sociedad",
        "atletico de madrid": "atletico madrid",
        "atletico madrid": "atletico madrid",
    }
    k = aliases.get(k, k)
    return {x for x in k.split() if x not in {"de", "del", "la", "the"}}


def _score_name(a: str, b: str) -> float:
    aa, bb = _tokens(a), _tokens(b)
    if not aa or not bb:
        return 0.0
    if aa == bb:
        return 1.0
    jac = len(aa & bb) / max(1, len(aa | bb))
    contain = 0.88 if (aa <= bb or bb <= aa) else 0.0
    return max(jac, contain)


def _archive_dir(league_code: str, season: int) -> list[dict[str, Any]]:
    key = f"{league_code}|{season}"
    if key in _dir_cache:
        return _dir_cache[key]
    url = f"{ARCHIVE_REPO}/raw/{league_code}/{season}?ref=main"
    try:
        rows = p.http_json(url, 20, 2)
        rows = rows if isinstance(rows, list) else []
    except Exception:
        rows = []
    _dir_cache[key] = rows
    return rows


def archive_team_json(event: dict[str, Any], team_name: str, season: int) -> dict[str, Any] | None:
    lc = ARCHIVE_LEAGUE.get(event.get("league") or "")
    if not lc:
        return None
    ckey = f"{lc}|{season}|{p.team_key(team_name)}"
    old = _archive_cache.get(ckey)
    if isinstance(old, dict) and old.get("competitions"):
        return old
    rows = _archive_dir(lc, season)
    scored: list[tuple[float, dict[str, Any]]] = []
    for r in rows:
        if not isinstance(r, dict) or r.get("type") != "file" or not str(r.get("name") or "").endswith(".json"):
            continue
        stem = re.sub(r"\.json$", "", str(r.get("name")), flags=re.I)
        scored.append((_score_name(team_name, stem), r))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored or scored[0][0] < 0.50:
        return None
    if len(scored) > 1 and scored[0][0] < 0.90 and scored[0][0] - scored[1][0] < 0.15:
        return None
    url = scored[0][1].get("download_url")
    if not url:
        return None
    try:
        raw = p.http_json(str(url), 25, 2)
        if not isinstance(raw, dict):
            return None
        if _score_name(team_name, str(raw.get("club") or raw.get("tmSlug") or "")) < 0.45:
            return None
        _archive_cache[ckey] = raw
        return raw
    except Exception:
        return None


def norm_archive_pos(raw: str) -> str:
    s = str(raw or "").upper().strip()
    if s in {"GK", "G"} or "GOAL" in s:
        return "GK"
    if s in {"CB", "LB", "RB", "LWB", "RWB", "DF", "DEF"} or "BACK" in s:
        return "DEF"
    if s in {"DM", "CM", "AM", "LM", "RM", "MF", "MID"} or "MID" in s:
        return "MID"
    if s in {"LW", "RW", "CF", "ST", "SS", "FW", "ATT"} or "WING" in s or "STRIK" in s or "FORWARD" in s:
        return "ATT"
    return s[:8]


def archive_history(event: dict[str, Any], side: str, year: int) -> tuple[list[list[dict[str, Any]]], list[int]]:
    team_name = event["home"] if side == "home" else event["away"]
    season = year - 1
    raw = archive_team_json(event, team_name, season)
    if not raw:
        return [], []
    lc = ARCHIVE_LEAGUE.get(event.get("league") or "")
    comp = next((c for c in raw.get("competitions") or [] if str(c.get("code") or "") == lc), None)
    if not isinstance(comp, dict):
        return [], []
    players = comp.get("players") or []
    rounds: set[int] = set()
    for q in players:
        for m in q.get("matches") or []:
            try:
                rounds.add(int(str(m.get("round") or "").split(".")[0]))
            except Exception:
                pass
    use_rounds = sorted(rounds)[-6:]
    out: list[list[dict[str, Any]]] = []
    used: list[int] = []
    for rnd in use_rounds:
        row: list[dict[str, Any]] = []
        for q in players:
            mm = None
            for m in q.get("matches") or []:
                try:
                    rr = int(str(m.get("round") or "").split(".")[0])
                except Exception:
                    continue
                if rr == rnd:
                    mm = m
                    break
            if not mm:
                continue
            status = str(mm.get("status") or "not_in_squad")
            if status not in {"starting", "sub_in", "bench", "not_in_squad"}:
                status = "not_in_squad"
            name = str(q.get("name") or "").strip()
            if not name:
                continue
            row.append({
                "id": "name:" + p.team_key(name),
                "name": name,
                "pos": norm_archive_pos(str(q.get("position") or "")),
                "status": status,
                "archiveRound": rnd,
            })
        if sum(x.get("status") == "starting" for x in row) >= 10:
            out.append(row)
            used.append(season)
    return out, used


_original_prior = base.prior_lineups_extended
_original_fpl = base.fpl_injury_rows


def prior_lineups_extended(event: dict[str, Any], side: str, pcache: dict[str, Any], year: int):
    espn_rows, espn_seasons = _original_prior(event, side, pcache, year)
    ar_rows, ar_seasons = archive_history(event, side, year)
    if len(espn_rows) >= 6:
        return espn_rows[-6:], espn_seasons[-6:]
    need = max(0, 6 - len(espn_rows))
    rows = ar_rows[-need:] + espn_rows
    seasons = ar_seasons[-need:] + espn_seasons
    return rows[-6:], seasons[-6:]


def fpl_injury_rows(team_name: str) -> list[dict[str, Any]]:
    rows = _original_fpl(team_name)
    out = []
    for r in rows:
        rr = dict(r)
        detail = str(rr.get("detail") or "")
        low = detail.lower()
        if re.search(r"has joined|joined .* on loan|joined .* permanently|transfer", low):
            rr["class"] = "departed"
            rr["hardUnavailable"] = True
            rr["availabilityReason"] = "not_at_club"
        out.append(rr)
    return out


def fetch_coach(event: dict[str, Any], team_id: str, year: int):
    urls = [
        f"https://site.api.espn.com/apis/site/v2/sports/soccer/{event['espnLeague']}/teams/{team_id}",
        f"https://site.api.espn.com/apis/site/v2/sports/soccer/{event['espnLeague']}/teams/{team_id}/roster",
        f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/{event['espnLeague']}/teams/{team_id}/coaches",
        f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/{event['espnLeague']}/seasons/{year}/teams/{team_id}/coaches",
    ]
    errors = []
    loaded_without_name = False
    for url in urls:
        try:
            raw = p.http_json(url, 15, 2)
            loaded_without_name = True
            name = base.coach_name(raw)
            if not name and isinstance(raw, dict):
                for item in raw.get("items") or []:
                    if isinstance(item, dict) and item.get("$ref"):
                        try:
                            prof = p.http_json(str(item["$ref"]).replace("http://", "https://"), 10, 1)
                            name = base.coach_name(prof)
                            if not name and isinstance(prof, dict):
                                for k in ("displayName", "fullName", "name", "shortName"):
                                    if prof.get(k):
                                        name = str(prof[k]).strip()
                                        break
                        except Exception as exc:
                            errors.append(str(exc))
                    if name:
                        break
            if name:
                return name, "loaded", url
        except Exception as exc:
            errors.append(str(exc))
    status = "loaded-no-coach" if loaded_without_name else ("unresolved: " + (errors[-1][:180] if errors else "no response"))
    return "", status, urls[0]


base.prior_lineups_extended = prior_lineups_extended
base.fpl_injury_rows = fpl_injury_rows
base.fetch_coach = fetch_coach


def postprocess() -> None:
    path = base.OUTPUT
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    for row in (data.get("fixtures") or {}).values():
        h = row.get("homeDetail") or {}
        a = row.get("awayDetail") or {}
        src_known = h.get("injurySourceStatus") in {"loaded-espn", "loaded-fpl"} and a.get("injurySourceStatus") in {"loaded-espn", "loaded-fpl"}
        hist_ready = h.get("snapshot") is not None and a.get("snapshot") is not None
        row["availabilitySourceKnown"] = bool(src_known)
        row["lineupHistoryReady"] = bool(hist_ready)
        row["weightedAvailabilityReady"] = bool(src_known and hist_ready)
        row["featureReadiness"] = "full-shadow" if (src_known and hist_ready) else ("continuity-only" if hist_ready else ("availability-only" if src_known else "partial"))
    pol = data.setdefault("policy", {})
    pol["earlySeasonHistory"] = "ESPN causal confirmed lineups, cold-start seeded from previous-season Transfermarkt availability archive; max six prior rows"
    pol["fplTransferHandling"] = "FPL unavailable players whose news indicates transfer/loan are classified departed/not_at_club, not injured"
    pol["availabilitySemantics"] = "source-known, lineup-history-ready, and weighted-availability-ready are separate states"
    pol["archiveSource"] = "withqwerty/availability-data previous season; Transfermarkt-derived; research only"
    p.write_json(path, data)
    try:
        m = json.loads(base.MANIFEST.read_text(encoding="utf-8"))
        m.setdefault("policy", {})["preXiShadow"] = "ESPN/FPL availability + ESPN lineups + previous-season Transfermarkt archive cold-start + prospective coach tracking; research only"
        p.write_json(base.MANIFEST, m)
    except Exception:
        pass


def main() -> int:
    rc = base.main()
    write_cache(_archive_cache)
    postprocess()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
