#!/usr/bin/env python3
"""Read-only HBT German top/second-tier competition identity audit.

Accept same-run, commit-pinned scanner, frozen bridge status and forecast JSON.
Never infers German top-tier identity from the bare word 'Bundesliga'.
Never alters HBT parameters, predictions, settlement or source captures.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any


SUPPORTED = {"INSUFFICIENT_DATA", "FULL_MODEL", "FALLBACK"}


def norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", raw.encode("ascii", "ignore").decode().lower()).split())


def german_tier(row: dict[str, Any]) -> int | None:
    """Return 1/2 only for explicit, unambiguous German league provenance."""
    labels = [norm(row.get(k)) for k in ("competition", "competitionSlug") if row.get(k)]
    seen = set()
    for label in labels:
        if re.search(r"\b(?:german|germany)\s+(?:2|second)\s+bundesliga\b|\b2\s+bundesliga\b|\bbundesliga\s+2\b", label):
            seen.add(2)
        elif re.search(r"\b(?:german|germany)\s+(?:1\s+)?bundesliga\b|\b1\s+bundesliga\b", label):
            seen.add(1)
    return next(iter(seen)) if len(seen) == 1 else None


def pair(home: Any, away: Any) -> tuple[str, str]:
    return norm(home), norm(away)


def excluded_pair(raw: Any) -> tuple[str, str] | None:
    if not isinstance(raw, str):
        return None
    parts = re.split(r"\s+vs\.?\s+", raw, maxsplit=1, flags=re.I)
    return pair(*parts) if len(parts) == 2 else None


def audit(scanner: dict[str, Any], bridge: dict[str, Any], forecast: dict[str, Any]) -> dict[str, Any]:
    dates = [doc.get("targetDate") for doc in (scanner, bridge, forecast)]
    if any(not isinstance(d, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in dates) or len(set(dates)) != 1:
        raise ValueError("Three same-date, explicit targetDate documents required")
    rows = scanner.get("fixtures")
    excluded = (bridge.get("target") or {}).get("excluded")
    predictions = forecast.get("predictions")
    if not all(isinstance(x, list) for x in (rows, excluded, predictions)):
        raise ValueError("Expected scanner.fixtures, bridge.target.excluded and forecast.predictions arrays")
    if not all(isinstance(x, dict) for x in rows + excluded + predictions):
        raise ValueError("Malformed fixture, exclusion or prediction row")

    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    issues = []
    second = 0
    unsupported_as_supported = 0
    for row in rows:
        by_pair[pair(row.get("home"), row.get("away"))].append(row)
        if german_tier(row) != 2:
            continue
        second += 1
        status = row.get("hbtSupportLevel")
        if status in SUPPORTED or row.get("rankEligible") or row.get("hbtLeague") == "de.1":
            unsupported_as_supported += 1
            issues.append({"code": "GERMAN_SECOND_TIER_FALSE_TOP_TIER_SUPPORT",
                           "fixture": f"{row.get('home')} vs {row.get('away')}",
                           "status": status, "hbtLeague": row.get("hbtLeague"),
                           "rankEligible": bool(row.get("rankEligible"))})

    ambiguous = 0
    unmatched = 0
    exclusion_conflicts = 0
    for row in excluded:
        k = excluded_pair(row.get("fixture"))
        matches = by_pair.get(k, []) if k else []
        if len(matches) != 1:
            ambiguous += int(len(matches) > 1)
            unmatched += int(len(matches) == 0)
            continue
        if german_tier(matches[0]) == 2 and row.get("league") == "de.1":
            exclusion_conflicts += 1
            issues.append({"code": "BRIDGE_SECOND_TIER_MISLABELLED_DE1",
                           "fixture": row.get("fixture"), "bridgeLeague": row.get("league")})

    prediction_conflicts = 0
    for row in predictions:
        fx = row.get("fixture") or {}
        if not isinstance(fx, dict):
            raise ValueError("Malformed forecast.fixture")
        matches = by_pair.get(pair(fx.get("home"), fx.get("away")), [])
        if len(matches) != 1:
            continue
        if german_tier(matches[0]) == 2 and fx.get("league") == "de.1":
            prediction_conflicts += 1
            issues.append({"code": "SECOND_TIER_FORECAST_IN_TOP_TIER",
                           "fixture": f"{fx.get('home')} vs {fx.get('away')}", "forecastLeague": "de.1"})

    return {"targetDate": dates[0],
            "status": "TIER_PROVENANCE_CONFLICT" if issues else "NO_EXPLICIT_TIER_CONFLICT_FOUND",
            "counts": {"scannerFixtures": len(rows), "explicitGermanSecondTier": second,
                       "falseSupportedSecondTier": unsupported_as_supported,
                       "bridgeSecondTierAsDe1": exclusion_conflicts,
                       "forecastSecondTierAsDe1": prediction_conflicts,
                       "ambiguousExclusionMatches": ambiguous, "unmatchedExclusions": unmatched},
            "issues": sorted(issues, key=lambda x: (x["code"], x["fixture"])),
            "limitations": ["Country/tier explicit labels only; generic Bundesliga is not inferred.",
                            "Requires independently authenticated same-run Git source clocks.",
                            "Does not establish training contamination or produce forecasts."]}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("scanner", "bridge", "forecast"):
        p.add_argument(f"--{name}", required=True, type=Path)
    args = p.parse_args()
    docs = [json.loads(getattr(args, n).read_text(encoding="utf-8")) for n in ("scanner", "bridge", "forecast")]
    print(json.dumps(audit(*docs), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
