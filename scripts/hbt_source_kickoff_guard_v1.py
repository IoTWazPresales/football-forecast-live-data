#!/usr/bin/env python3
"""Research-only source-clock guard for HBT OpenFootball Eredivisie fixtures.

Requires independently verified UTC kickoff; never changes a forecast, score,
fixture identity, source capture or training record. No network access.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

SOURCE_ZONE = {"OPENFOOTBALL:nl.1": "Europe/Amsterdam"}


def verified_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise ValueError("verified kickoff must be an ISO8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("verified kickoff must explicitly use UTC")
    return parsed.astimezone(timezone.utc)


def local_to_utc(date_str: str, clock: str, source: str) -> datetime:
    if source not in SOURCE_ZONE:
        raise ValueError("source timezone not audited; refuse to infer UTC")
    try:
        day = date.fromisoformat(date_str)
        tm = time.fromisoformat(clock)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("invalid local date or clock") from exc
    if tm.tzinfo is not None:
        raise ValueError("local clock must not contain a timezone")
    local = datetime.combine(day, tm)
    zone = ZoneInfo(SOURCE_ZONE[source])
    possibilities = []
    for fold in (0, 1):
        candidate = local.replace(tzinfo=zone, fold=fold)
        back = candidate.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
        if back == local:
            possibilities.append(candidate.astimezone(timezone.utc))
    unique = set(possibilities)
    if len(unique) != 1:
        raise ValueError("ambiguous or nonexistent local clock; independent UTC required")
    return unique.pop()


def check_row(row: dict) -> dict:
    if not row.get("independentKickoffVerified") or not str(row.get("independentKickoffSource", "")).startswith("https://"):
        raise ValueError("independent UTC kickoff verification and source URL required")
    derived = local_to_utc(row["date"], row["localTime"], row["source"])
    observed = verified_utc(row["verifiedKickoffUTC"])
    if derived != observed:
        raise ValueError(f"source local clock maps to {derived.isoformat()}, verified kickoff {observed.isoformat()}")
    return {"source": row["source"], "date": row["date"], "localTime": row["localTime"],
            "verifiedKickoffUTC": observed.isoformat().replace("+00:00", "Z"),
            "derivedKickoffUTC": derived.isoformat().replace("+00:00", "Z"),
            "status": "CLOCK_VERIFIED", "independentKickoffSource": row["independentKickoffSource"]}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    a = p.parse_args()
    data = json.loads(a.manifest.read_text(encoding="utf-8"))
    results = []
    for row in data["fixtures"]:
        try:
            results.append(check_row(row))
        except (ValueError, KeyError) as exc:
            results.append({"source": row.get("source"), "date": row.get("date"),
                            "status": "QUARANTINE", "reason": str(exc)})
    print(json.dumps({"schemaVersion": "HBT-SOURCE-CLOCK-AUDIT-1", "results": results}, indent=2))
    return 0 if all(x["status"] == "CLOCK_VERIFIED" for x in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
