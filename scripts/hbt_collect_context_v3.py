#!/usr/bin/env python3
"""HBT-1.2R-R3 research-only context intelligence collector.

Wraps HBT-1.2R-R2 and augments the existing pre_xi_context.json with
causal, pre-kickoff context that is useful for live decision support:
- workload / rest / short-turnaround burden from prior completed fixtures,
- rotation-risk proxy from expected-XI continuity,
- expected-XI role-shape profile (not a tactical formation claim),
- manager source/readiness already collected by R2,
- explicit promotion/readiness metadata per intelligence family.

IMPORTANT: this script does NOT change HBT-1.1.2 probabilities, tiers, picks,
Fusion coefficients, or bookmaker logic. New fields remain research/shadow only.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import hbt_collect_players_espn as p
import hbt_collect_prexi_context as base
import hbt_collect_prexi_context_v2 as r2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hbt_live_data"
OUTPUT = OUT / "pre_xi_context.json"
MANIFEST = OUT / "manifest.json"


def _event_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    league = str(row.get("league") or "")
    espn = p.ESPN_LEAGUES.get(league)
    h = row.get("homeDetail") or {}
    a = row.get("awayDetail") or {}
    if not espn or not h.get("teamId") or not a.get("teamId"):
        return None
    return {
        "id": str(row.get("eventId") or ""),
        "date": row.get("kickoff") or "",
        "league": league,
        "espnLeague": espn,
        "home": row.get("home") or h.get("team") or "",
        "away": row.get("away") or a.get("team") or "",
        "homeId": str(h.get("teamId") or ""),
        "awayId": str(a.get("teamId") or ""),
    }


def _completed_prior(event: dict[str, Any], side: str, year: int, cache: dict[str, Any]) -> list[dict[str, Any]]:
    tid = event["homeId"] if side == "home" else event["awayId"]
    kickoff = p.parse_dt(event.get("date"))
    if not kickoff:
        return []
    rows: list[dict[str, Any]] = []
    for sy in (year, year - 1):
        try:
            sched = p.get_team_schedule(event["espnLeague"], tid, sy, cache)
        except Exception:
            sched = []
        for raw in sched:
            er = p.event_record(raw, event["league"], event["espnLeague"])
            if not er or not er.get("completed") or er.get("id") == event.get("id"):
                continue
            when = p.parse_dt(er.get("date"))
            if not when or when >= kickoff:
                continue
            er["historySeason"] = sy
            er["dt"] = when
            rows.append(er)
    by_id = {str(x.get("id")): x for x in rows if x.get("id")}
    return sorted(by_id.values(), key=lambda x: x["dt"])[-30:]


def _workload(event: dict[str, Any], side: str, year: int, cache: dict[str, Any]) -> dict[str, Any]:
    kickoff = p.parse_dt(event.get("date"))
    prior = _completed_prior(event, side, year, cache)
    if not kickoff or not prior:
        return {
            "sourceKnown": False,
            "restDays": None,
            "matches7": None,
            "matches14": None,
            "matches21": None,
            "shortTurnarounds21": None,
            "awayMatches10": None,
            "lastMatchAt": None,
        }

    def age_days(x: dict[str, Any]) -> float:
        return max(0.0, (kickoff - x["dt"]).total_seconds() / 86400.0)

    last = prior[-1]
    last21 = [x for x in prior if age_days(x) <= 21.0]
    last10 = [x for x in prior if age_days(x) <= 10.0]
    short = 0
    s = sorted(last21, key=lambda x: x["dt"])
    for i in range(1, len(s)):
        gap = (s[i]["dt"] - s[i - 1]["dt"]).total_seconds() / 86400.0
        if gap <= 4.0:
            short += 1
    tid = event["homeId"] if side == "home" else event["awayId"]
    away10 = sum(1 for x in last10 if str(x.get("awayId") or "") == str(tid))
    return {
        "sourceKnown": True,
        "restDays": round(age_days(last), 2),
        "matches7": sum(1 for x in prior if age_days(x) <= 7.0),
        "matches14": sum(1 for x in prior if age_days(x) <= 14.0),
        "matches21": len(last21),
        "shortTurnarounds21": short,
        "awayMatches10": away10,
        "lastMatchAt": last.get("date"),
    }


def _role_shape(event: dict[str, Any], side: str, year: int, cache: dict[str, Any], snap: dict[str, Any] | None) -> dict[str, Any]:
    if not snap or not snap.get("expectedXI"):
        return {"sourceKnown": False, "profile": None, "counts": None, "label": "unavailable"}
    try:
        hist, _ = r2.prior_lineups_extended(event, side, cache, year)
    except Exception:
        hist = []
    pos_by_name: dict[str, str] = {}
    for match in hist:
        for q in match:
            name = str(q.get("name") or "").strip()
            if name:
                pos_by_name[p.team_key(name)] = str(q.get("pos") or "OUT").upper()
    counts = {"GK": 0, "DEF": 0, "MID": 0, "ATT": 0, "OUT": 0}
    for name in snap.get("expectedXI") or []:
        pos = pos_by_name.get(p.team_key(name), "OUT")
        if pos not in counts:
            pos = "OUT"
        counts[pos] += 1
    known = sum(counts[x] for x in ("GK", "DEF", "MID", "ATT"))
    profile = f"{counts['DEF']}D-{counts['MID']}M-{counts['ATT']}A" if known >= 9 else None
    return {
        "sourceKnown": bool(profile),
        "profile": profile,
        "counts": counts,
        "label": "expected-XI role shape only; not a tactical formation claim",
    }


def _augment_row(row: dict[str, Any], year: int, cache: dict[str, Any]) -> None:
    event = _event_from_row(row)
    if not event:
        row["extendedContext"] = {"sourceKnown": False, "reason": "fixture identity incomplete"}
        row["intelligenceReadiness"] = {
            "availability": bool(row.get("availabilitySourceKnown")),
            "lineupHistory": bool(row.get("lineupHistoryReady")),
            "workload": False,
            "manager": False,
            "roleShape": False,
        }
        return
    home = _workload(event, "home", year, cache)
    away = _workload(event, "away", year, cache)
    hs = (row.get("homeDetail") or {}).get("snapshot")
    aws = (row.get("awayDetail") or {}).get("snapshot")
    hshape = _role_shape(event, "home", year, cache, hs)
    ashape = _role_shape(event, "away", year, cache, aws)
    f = row.get("features") or {}
    manager = row.get("managerFeatures") or {}
    hcont = hs.get("expectedContinuity") if isinstance(hs, dict) else None
    acont = aws.get("expectedContinuity") if isinstance(aws, dict) else None
    ext = {
        "sourceKnown": bool(home.get("sourceKnown") or away.get("sourceKnown") or hshape.get("sourceKnown") or ashape.get("sourceKnown")),
        "workload": {
            "home": home,
            "away": away,
            "restAdvDays": (home["restDays"] - away["restDays"]) if home.get("restDays") is not None and away.get("restDays") is not None else None,
            "shortTurnAdv": (away["shortTurnarounds21"] - home["shortTurnarounds21"]) if home.get("shortTurnarounds21") is not None and away.get("shortTurnarounds21") is not None else None,
            "load7Adv": (away["matches7"] - home["matches7"]) if home.get("matches7") is not None and away.get("matches7") is not None else None,
            "awayTravelProxyAdv": (away["awayMatches10"] - home["awayMatches10"]) if home.get("awayMatches10") is not None and away.get("awayMatches10") is not None else None,
        },
        "rotation": {
            "homeExpectedContinuity": hcont,
            "awayExpectedContinuity": acont,
            "homeRotationRisk": (1.0 - float(hcont)) if hcont is not None else None,
            "awayRotationRisk": (1.0 - float(acont)) if acont is not None else None,
            "continuityDiff": f.get("expectedContinuityDiff"),
        },
        "roleShape": {"home": hshape, "away": ashape},
        "manager": {
            "homeCoach": manager.get("homeCoach"),
            "awayCoach": manager.get("awayCoach"),
            "homeChangedDetected": manager.get("homeManagerChangedDetected"),
            "awayChangedDetected": manager.get("awayManagerChangedDetected"),
            "homeTenureLowerBoundDays": manager.get("homeTenureLowerBoundDays"),
            "awayTenureLowerBoundDays": manager.get("awayTenureLowerBoundDays"),
        },
        "promotion": {
            "availability": "shadow/rejected P1 promotion in current causal test",
            "expectedXIContinuity": "shadow/rejected P1 promotion in current causal test",
            "shortTurnaround": "historically selected L3 signal; R3 live field is candidate-only until prospective validation",
            "load7": "historically rejected as predictive; diagnostic only",
            "awayTravelProxy": "historically rejected as predictive; diagnostic only",
            "managerChange": "unvalidated prospective shadow",
            "roleShape": "new descriptive shadow; not a tactical model",
            "odds": "never predictive input",
        },
    }
    row["extendedContext"] = ext
    row["intelligenceReadiness"] = {
        "availability": bool(row.get("availabilitySourceKnown")),
        "lineupHistory": bool(row.get("lineupHistoryReady")),
        "workload": bool(home.get("sourceKnown") and away.get("sourceKnown")),
        "manager": bool(manager.get("homeCoach") or manager.get("awayCoach")),
        "roleShape": bool(hshape.get("sourceKnown") and ashape.get("sourceKnown")),
    }


def postprocess() -> None:
    try:
        data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except Exception:
        return
    year = int(data.get("seasonStartYear") or dt.datetime.now(dt.timezone.utc).year)
    cache = p.read_cache()
    for row in (data.get("fixtures") or {}).values():
        _augment_row(row, year, cache)
    policy = data.setdefault("policy", {})
    policy["researchVersion"] = "HBT-1.2R-R3-CONTEXT"
    policy["extendedContext"] = "workload/rest/short-turnaround + rotation proxy + expected-XI role shape + manager tracking; shadow only"
    policy["feedsBackIntoPrediction"] = False
    policy["oddsUsed"] = False
    policy["tacticalSemantics"] = "role-shape is descriptive player-position composition; it is not formation/tactical intent"
    data["researchVersion"] = "HBT-1.2R-R3-CONTEXT"
    p.write_json(OUTPUT, data)
    try:
        m = json.loads(MANIFEST.read_text(encoding="utf-8"))
        m.setdefault("policy", {})["preXiShadow"] = "R3: availability + expected-XI continuity + manager + workload/rest/short-turnaround + rotation + role-shape; research only"
        m.setdefault("policy", {})["feedsBackIntoPrediction"] = False
        m["contextResearchVersion"] = "HBT-1.2R-R3-CONTEXT"
        p.write_json(MANIFEST, m)
    except Exception:
        pass
    p.write_json(p.CACHE_PATH, cache)


def main() -> int:
    rc = r2.main()
    postprocess()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
