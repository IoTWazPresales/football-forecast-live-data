"""Read-only, fail-closed scoring of HBT point-in-time 1X2 forecasts.

This module does NOT fetch results, assert that a commit is first-add, score
unavailable goal markets, or reconstruct bookmaker prices. Those are external
verification responsibilities. It never modifies HBT source data.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

FROZEN_MODEL = "HBT-1.1.2L-R1"
HEX40 = re.compile(r"^[a-f0-9]{40}$")
BINS = ((0.0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 1.00000001))


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith(("Z", "+00:00")):
        raise ValueError("Explicit UTC timestamp required")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid UTC timestamp") from exc
    if dt.utcoffset().total_seconds() != 0:
        raise ValueError("UTC offset must be zero")
    return dt.astimezone(timezone.utc)


def _external_url(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("Missing independent source URL")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.hostname in (
        "github.com", "raw.githubusercontent.com", "api.github.com"
    ):
        raise ValueError("External HTTPS verification URL required")


def _identity(row: dict) -> tuple[str, str, str, str]:
    return tuple(str(row[k]).strip().casefold() for k in ("date", "league", "home", "away"))


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def score_settled(forecast: dict, evidence: dict, provenance: dict) -> dict:
    """Score verified senior-men's regulation-time results only.

    Provenance must be independently established against Git history; its
    firstAddVerified field is an attestation, not cryptographic verification.
    Evidence results must be independently reviewed, not model-generated.
    """
    if forecast.get("sourceLabVersion") != FROZEN_MODEL:
        raise ValueError("Frozen model version mismatch")
    if forecast.get("policy", {}).get("prospectiveExport") is not True:
        raise ValueError("Prospective export evidence missing")
    if provenance.get("firstAddVerified") is not True:
        raise ValueError("First-add provenance not independently attested")
    for key in ("commitSha", "blobSha"):
        if not isinstance(provenance.get(key), str) or not HEX40.fullmatch(provenance[key]):
            raise ValueError(f"Invalid {key}")
    export_at = _utc(forecast.get("sourceExportedAt"))
    commit_at = _utc(provenance.get("committedAtUtc"))
    if commit_at < export_at:
        raise ValueError("Commit predates claimed forecast export")
    target = forecast.get("targetDate")
    predictions = forecast.get("predictions")
    if not isinstance(predictions, list):
        raise ValueError("Predictions list missing")
    indexed = {}
    for row in predictions:
        fixture = row["fixture"]
        key = _identity(fixture)
        if key in indexed or fixture["date"] != target:
            raise ValueError("Duplicate or wrong-date forecast identity")
        probs = row["probs"]
        if (not isinstance(probs, list) or len(probs) != 3 or
            any(not isinstance(p, (float, int)) or isinstance(p, bool) or not math.isfinite(p) or p <= 0 or p >= 1 for p in probs) or
            abs(sum(probs) - 1) > 1e-8):
            raise ValueError("Invalid 1X2 probability vector")
        indexed[key] = [float(p) for p in probs]

    results = evidence.get("results")
    if not isinstance(results, list):
        raise ValueError("Verified results list missing")
    seen, evaluated = set(), []
    for result in results:
        key = _identity(result)
        if key not in indexed or key in seen:
            raise ValueError("Unknown or duplicate result identity")
        seen.add(key)
        if result.get("category") != "SENIOR_MEN" or result.get("status") != "FT_REGULATION":
            raise ValueError("Not verified senior-men regulation-time final")
        if not isinstance(result.get("competition"), str) or not result["competition"].strip():
            raise ValueError("Competition identity not independently supplied")
        _external_url(result.get("resultSource"))
        _external_url(result.get("kickoffSource"))
        kickoff = _utc(result.get("kickoffUtc"))
        if export_at >= kickoff or commit_at >= kickoff:
            raise ValueError("Forecast not proven before verified kickoff")
        goals = [result.get("homeGoals"), result.get("awayGoals")]
        if any(not isinstance(g, int) or isinstance(g, bool) or g < 0 for g in goals):
            raise ValueError("Invalid regulation-time goals")
        y = 0 if goals[0] > goals[1] else 1 if goals[0] == goals[1] else 2
        p = indexed[key]
        dc = ((p[0]+p[1], y != 2), (p[1]+p[2], y != 0), (p[0]+p[2], y != 1))
        evaluated.append({
            "identity": key, "correct": p.index(max(p)) == y, "confidence": max(p),
            "brier": sum((v - (1 if i == y else 0))**2 for i,v in enumerate(p)),
            "logLoss": -math.log(p[y]),
            "dc": [{"brier": (pr-int(hit))**2,
                    "logLoss": -math.log(pr if hit else 1-pr)} for pr,hit in dc]
        })
    n = len(evaluated)
    return {
        "targetDate": target, "forecastCount": len(predictions), "verifiedSettled": n,
        "forecastSettlementCoverage": n / len(predictions) if predictions else None,
        "accuracy": _mean([float(r["correct"]) for r in evaluated]),
        "multiclassBrierUnhalved": _mean([r["brier"] for r in evaluated]),
        "multiclassLogLoss": _mean([r["logLoss"] for r in evaluated]),
        "doubleChance": {label: {
            "brier": _mean([r["dc"][i]["brier"] for r in evaluated]),
            "logLoss": _mean([r["dc"][i]["logLoss"] for r in evaluated])
        } for i,label in enumerate(("1X", "X2", "12"))},
        "topPickReliability": [{
            "range": [lo, min(hi,1.0)], "n": len(group),
            "meanConfidence": _mean([r["confidence"] for r in group]),
            "observedAccuracy": _mean([float(r["correct"]) for r in group])
        } for lo,hi in BINS for group in [[r for r in evaluated if lo <= r["confidence"] < hi]]],
        "bttsAndGoalTotals": "UNAVAILABLE_NOT_SCORED_WITHOUT_GENUINE_FORECASTS",
        "r5HypotheticalROI": "UNAVAILABLE_NO_VERIFIED_CONTEMPORANEOUS_PRICES_AND_SELECTIONS",
        "note": "Forecast settlement coverage is NOT global fixture discovery coverage."
    }
