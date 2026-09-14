#!/usr/bin/env python3
"""Runtime hardening wrapper for HBT-1.2R-R3 context collection.

ESPN soccer season query labels are inconsistent across competitions: some use
season start year while others use season end year. Try adjacent labels and
combine/dedupe them. All R3 downstream workload calculations still enforce
completed fixture time < target kickoff, so this expands causal coverage without
introducing future information.
"""
from __future__ import annotations

import json
from typing import Any

import hbt_collect_players_espn as p
import hbt_collect_context_v3 as r3

_ORIGINAL_GET_TEAM_SCHEDULE = p.get_team_schedule


def robust_team_schedule(league: str, team_id: str, year: int, cache: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sy in (year, year + 1, year - 1):
        try:
            part = _ORIGINAL_GET_TEAM_SCHEDULE(league, team_id, sy, cache) or []
        except Exception:
            part = []
        for raw in part:
            if not isinstance(raw, dict):
                continue
            rid = str(raw.get("id") or raw.get("uid") or "")
            key = rid or json.dumps(raw, sort_keys=True, ensure_ascii=False)[:500]
            if key in seen:
                continue
            seen.add(key)
            rows.append(raw)
    return rows


p.get_team_schedule = robust_team_schedule

if __name__ == "__main__":
    raise SystemExit(r3.main())
