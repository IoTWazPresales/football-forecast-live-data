#!/usr/bin/env python3
"""Read-only, fail-closed HBT forecast/scanner snapshot readiness audit.

Inputs must be commit-pinned same-run copies; this script does not authenticate
Git history, independent fixture identity, result evidence or betting prices.
It never scores predictions or modifies source artifacts.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

FROZEN_VERSION = "HBT-1.1.2L-R1"
SUPPORT = ("FULL_MODEL", "FALLBACK", "INSUFFICIENT_DATA", "NOT_YET_READY", "SOURCE_FAILURE", "UNSUPPORTED_COMPETITION")


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith(("Z", "+00:00")):
        raise ValueError("Explicit UTC timestamp required")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid UTC timestamp") from exc
    if dt.utcoffset() is None or dt.utcoffset().total_seconds() != 0:
        raise ValueError("UTC offset must be zero")
    return dt.astimezone(timezone.utc)


def audit(forecast: dict, scanner: dict) -> dict:
    """Assess discovery-versus-prediction readiness; do not imply men's eligibility."""
    if forecast.get("sourceLabVersion") != FROZEN_VERSION:
        raise ValueError("Frozen model mismatch")
    if forecast.get("policy", {}).get("prospectiveExport") is not True:
        raise ValueError("Prospective forecast evidence absent")
    target = forecast.get("targetDate")
    if not isinstance(target, str) or target != scanner.get("targetDate"):
        raise ValueError("Forecast/scanner target dates differ")
    exported, scanned = _utc(forecast.get("sourceExportedAt")), _utc(scanner.get("generatedAt"))
    if not 0 <= (scanned - exported).total_seconds() <= 300:
        raise ValueError("Scanner and forecast are not temporally same-run")
    predictions, fixtures = forecast.get("predictions"), scanner.get("fixtures")
    if not isinstance(predictions, list) or not isinstance(fixtures, list):
        raise ValueError("Forecast predictions or scanner fixtures missing")
    seen = set()
    for row in predictions:
        f = row.get("fixture") or {}
        key = (f.get("date"), f.get("league"), f.get("home"), f.get("away"))
        if f.get("date") != target or not all(key) or key in seen:
            raise ValueError("Invalid, duplicate, or wrong-date forecast")
        seen.add(key)
        p = row.get("probs")
        if (not isinstance(p, list) or len(p) != 3 or
            any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 or v >= 1 for v in p) or
            abs(sum(p) - 1) > 1e-8):
            raise ValueError("Invalid 1X2 probability vector")
    counts = Counter(row.get("hbtSupportLevel") for row in fixtures)
    if any(status not in SUPPORT for status in counts):
        raise ValueError("Unknown scanner support status")
    coverage, gate = scanner.get("coverage") or {}, scanner.get("rankingGate") or {}
    if coverage.get("fixturesDiscovered") != len(fixtures) or coverage.get("classifiedRows") != len(fixtures):
        raise ValueError("Scanner fixture counts disagree")
    for status in SUPPORT:
        if coverage.get(status, 0) != counts[status]:
            raise ValueError(f"Scanner {status} count disagrees")
    eligible = sum(row.get("rankEligible") is True for row in fixtures)
    if gate.get("rankEligibleFixtures") != eligible:
        raise ValueError("Scanner eligible count disagrees")
    if coverage.get("forecastRowsAvailable") != len(predictions):
        raise ValueError("Scanner forecast count disagrees")
    matched = coverage.get("forecastRowsMatched")
    if not isinstance(matched, int) or not 0 <= matched <= len(predictions):
        raise ValueError("Invalid matched-forecast count")
    if eligible != counts["FULL_MODEL"] + counts["FALLBACK"]:
        raise ValueError("Rank eligibility and support categories disagree")
    # We cannot infer fixture-category eligibility or global men's coverage here.
    flags = []
    if not predictions:
        flags.append("ZERO_DATE_SCOPED_PREDICTIONS")
    if gate.get("discoveryComplete") is True and not predictions:
        flags.append("DISCOVERY_COMPLETE_BUT_PREDICTION_EMPTY")
    if not counts["FULL_MODEL"]:
        flags.append("NO_FULL_FUSION_PREDICTIONS")
    if matched != len(predictions):
        flags.append("UNMATCHED_FORECASTS")
    if not eligible:
        flags.append("NO_RANK_ELIGIBLE_PREDICTIONS")
    return {
        "targetDate": target,
        "discoveredFixtures": len(fixtures),
        "forecastCount": len(predictions),
        "forecastRowsMatched": matched,
        "rankEligible": eligible,
        "supportCounts": {status: counts[status] for status in SUPPORT},
        "discoveryCompleteReported": gate.get("discoveryComplete") is True,
        "forecastRowsPresentAndMatched": bool(predictions) and matched == len(predictions) and eligible > 0,
        "fullFusionRowsPresent": counts["FULL_MODEL"] > 0,
        "seniorMensPredictionReadinessEstablished": False,
        "flags": flags,
        "categoryAndKickoffVerified": False,
        "note": "Diagnostic only: no category authentication, immutable first-add verification, global men's coverage, or betting readiness implied."
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast", required=True, type=Path)
    parser.add_argument("--scanner", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(json.loads(args.forecast.read_text()), json.loads(args.scanner.read_text())), indent=2))


if __name__ == "__main__":
    main()
