#!/usr/bin/env python3
"""Rank HBT slate candidates only after the discovery gate passes.

Football calls are model-only. Bookmaker prices are an optional downstream
sidecar for display, fair-price/value analysis and later CLV audit. A price can
never create, remove, replace or reorder the HBT football forecast itself, and
it cannot veto a R1 prospective experiment.

Validated HBT-1.3 event-market families are surfaced separately from 1X2. They
must pass the existing causal-model validation flag AND a minimum live-history
coverage gate. No bookmaker price is used to choose their probability or line.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hbt_live_data"
SLATE = OUT / "slate_scanner.json"
INTEL = OUT / "hbt_1_4_match_intelligence.json"
EXPERIMENTS = OUT / "live_experiments.json"
PRICES = OUT / "market_prices.json"
OUTPUT = OUT / "ranked_candidates.json"
VERSION = "HBT-SLATE-RANKER-2.1"
TIER_ORDER = {"A": 0, "B": 1, "C": 2, "Avoid": 3, None: 4, "": 4}
EVENT_MIN_HISTORY = 3
EVENT_LINES = {
    "corners": [7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5],
    "yellowCards": [2.5, 3.5, 4.5, 5.5, 6.5],
    "shots": [19.5, 21.5, 23.5, 25.5, 27.5, 29.5],
    "shotsOnTarget": [6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5],
}
EVENT_LABELS = {
    "corners": "Total Corners",
    "yellowCards": "Total Yellow Cards",
    "shots": "Total Team Shots",
    "shotsOnTarget": "Total Shots on Target",
}


def read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write(path: Path, obj: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def nkey(value: Any) -> str:
    s = unicodedata.normalize("NFKD", str(value or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r"\b(fc|cf|afc|sc|club|ud|cd|rc|ac|as)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def find_price_fixture(home: Any, away: Any, prices: dict[str, Any]) -> dict[str, Any] | None:
    h, a = nkey(home), nkey(away)
    for x in (prices.get("fixtures") or {}).values():
        f = x.get("slateFixture") or {}
        if nkey(f.get("home")) == h and nkey(f.get("away")) == a:
            return x
    return None


def price_assessment(home: Any, away: Any, prices: dict[str, Any]) -> dict[str, Any]:
    price = find_price_fixture(home, away, prices)
    return {
        "status": price.get("priceStatus") if price else "PRICE_UNAVAILABLE",
        "bookmaker": price.get("bookmaker") if price else prices.get("primaryBookmaker"),
        "identityMatchScore": price.get("identityMatchScore") if price else None,
        "markets": price.get("markets") if price else [],
        "advisoryOnly": True,
        "gatesFootballForecast": False,
        "gatesR1Experiment": False,
    }


def compact(row: dict[str, Any], prices: dict[str, Any]) -> dict[str, Any]:
    return {
        "competition": row.get("competition"),
        "kickoff": row.get("kickoff"),
        "home": row.get("home"),
        "away": row.get("away"),
        "support": row.get("hbtSupportLevel"),
        "predictionMode": row.get("predictionMode"),
        "pick": row.get("pick"),
        "pickProbability": row.get("pickProbability"),
        "probabilityOutput": row.get("probabilityOutput"),
        "tier": row.get("tier"),
        "rawTier": row.get("rawTier"),
        "quality": row.get("quality"),
        "forecastCoverage": row.get("forecastCoverage"),
        "coveragePack": row.get("coveragePack"),
        "fusionEligible": row.get("fusionEligible"),
        "xiState": row.get("xiState"),
        "scoreMarketsExist": row.get("scoreMarketsExist"),
        "scoreMarkets": row.get("scoreMarkets"),
        "validatedEventMarketsExist": row.get("validatedEventMarketsExist"),
        "validatedEventFamilies": row.get("validatedEventFamilies") or [],
        "predictionSource": row.get("predictionSource"),
        "forecastDecision": "MODEL_SUPPORTED",
        "r1ExperimentDecision": "ELIGIBLE_MODEL_ONLY",
        "priceAssessment": price_assessment(row.get("home"), row.get("away"), prices),
    }


def p(row: dict[str, Any]) -> float:
    try:
        return float(row.get("pickProbability") or 0.0)
    except Exception:
        return 0.0


def q(row: dict[str, Any]) -> float:
    try:
        return float(row.get("quality") or 0.0)
    except Exception:
        return 0.0


def confidence_key(row: dict[str, Any]) -> tuple[int, float, float]:
    return (TIER_ORDER.get(row.get("tier"), 4), -p(row), -q(row))


def poisson_over(lam: float, line: float) -> float:
    # Half-line: Over 9.5 means P(X >= 10).
    minimum = int(math.floor(line)) + 1
    term = math.exp(-lam)
    cdf = term
    for k in range(1, minimum):
        term *= lam / k
        cdf += term
    return max(0.0, min(1.0, 1.0 - cdf))


def history_minimum(market: dict[str, Any]) -> tuple[int, dict[str, int]]:
    h = market.get("history") or {}
    keys = ("homeForN", "homeAgainstN", "awayForN", "awayAgainstN")
    counts: dict[str, int] = {}
    for k in keys:
        try:
            counts[k] = int(h.get(k) or 0)
        except Exception:
            counts[k] = 0
    return min(counts.values()) if counts else 0, counts


def event_forecasts(intel: dict[str, Any], target_date: str, prices: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for fixture_key, fx in (intel.get("fixtures") or {}).items():
        if not str(fx.get("kickoff") or "").startswith(target_date):
            continue
        for family in ("corners", "yellowCards", "shots", "shotsOnTarget"):
            market = (fx.get("eventMarkets") or {}).get(family) or {}
            lam = market.get("totalLambda")
            validated = market.get("validatedMarketModel") is True and family in (fx.get("validatedEventFamilies") or [])
            hist_min, counts = history_minimum(market)
            reasons: list[str] = []
            if not validated:
                reasons.append("validated_event_model_not_ready")
            try:
                lam_f = float(lam)
                if not math.isfinite(lam_f) or lam_f <= 0:
                    reasons.append("total_lambda_missing_or_invalid")
            except Exception:
                lam_f = 0.0
                reasons.append("total_lambda_missing_or_invalid")
            if hist_min < EVENT_MIN_HISTORY:
                reasons.append(f"history_coverage_below_{EVENT_MIN_HISTORY}")
            if reasons:
                excluded.append({
                    "fixtureKey": fixture_key, "kickoff": fx.get("kickoff"), "home": fx.get("home"), "away": fx.get("away"),
                    "family": family, "totalLambda": lam, "history": counts, "reasons": reasons,
                })
                continue
            for line in EVENT_LINES[family]:
                over = poisson_over(lam_f, line)
                for side, prob in (("OVER", over), ("UNDER", 1.0 - over)):
                    eligible.append({
                        "fixtureKey": fixture_key,
                        "kickoff": fx.get("kickoff"),
                        "home": fx.get("home"),
                        "away": fx.get("away"),
                        "support": "VALIDATED_EVENT_MODEL",
                        "model": market.get("calibrationVersion"),
                        "family": family,
                        "market": EVENT_LABELS[family],
                        "line": line,
                        "side": side,
                        "exactBetWording": f"{EVENT_LABELS[family]} — {side.title()} {line}",
                        "modelProbability": prob,
                        "fairOdds": (1.0 / prob) if prob > 0 else None,
                        "totalLambda": lam_f,
                        "history": counts,
                        "historyMinimum": hist_min,
                        "forecastDecision": "MODEL_SUPPORTED_EVENT",
                        "r1ExperimentDecision": "ELIGIBLE_MODEL_ONLY",
                        "priceAssessment": price_assessment(fx.get("home"), fx.get("away"), prices),
                    })
    eligible.sort(key=lambda x: -float(x.get("modelProbability") or 0.0))
    return eligible, excluded


def main() -> int:
    s = read(SLATE, {})
    intel = read(INTEL, {})
    gate = s.get("rankingGate") or {}
    coverage = s.get("coverage") or {}
    ex = read(EXPERIMENTS, {})
    prices = read(PRICES, {"status": "PRICE_UNAVAILABLE", "fixtures": {}})
    test_a = next((x for x in ex.get("experiments") or [] if x.get("id") == "PRE_XI_TEST_A_2026-09-15"), None)

    policy = {
        "discoveryGateRequired": True,
        "bookmakerOddsUsedAsFootballModelFeature": False,
        "bookmakerOddsUsedInSimulation": False,
        "bookmakerOddsMayChangeFootballForecast": False,
        "bookmakerOddsMayChangeR1ExperimentEligibility": False,
        "priceAssessmentOnly": True,
        "footballProbabilitiesRecomputed": False,
        "fullModelAndFallbackSeparated": True,
        "eventModelsSeparatedFrom1X2": True,
        "eventMinimumHistoryPerSideForAndAgainst": EVENT_MIN_HISTORY,
        "rawProbabilityIsNotBettingValue": True,
        "universalBestBetsClaimAllowed": False,
        "configuredSourceRankingLabel": "Best HBT-supported candidates from the configured-source discovered slate",
        "testAImmutable": bool((ex.get("policy") or {}).get("testAImmutable") and test_a and test_a.get("state") == "FROZEN_PROSPECTIVE"),
    }

    if gate.get("discoveryComplete") is not True:
        payload = {
            "schemaVersion": "HBT-SLATE-RANKING-2",
            "version": VERSION,
            "targetDate": s.get("targetDate"),
            "status": "BLOCKED_DISCOVERY_INCOMPLETE",
            "policy": policy,
            "coverage": coverage,
            "rankingGate": gate,
            "priceLayer": {"status": prices.get("status"), "provider": prices.get("provider"), "primaryBookmaker": prices.get("primaryBookmaker"), "advisoryOnly": True},
            "reason": "Slate discovery/reconciliation gate is not complete; ranking is intentionally withheld.",
            "testAReference": test_a,
            "rankings": None,
        }
        write(OUTPUT, payload)
        return 2

    rows = [x for x in s.get("fixtures") or [] if x.get("rankEligible") and x.get("pickProbability") is not None]
    full = [x for x in rows if x.get("hbtSupportLevel") == "FULL_MODEL"]
    fallback = [x for x in rows if x.get("hbtSupportLevel") == "FALLBACK"]
    ignored = [x for x in s.get("fixtures") or [] if not x.get("rankEligible")]
    event_rows, event_excluded = event_forecasts(intel, str(s.get("targetDate") or ""), prices)

    raw = sorted(rows, key=lambda x: (-p(x), TIER_ORDER.get(x.get("tier"), 4), -q(x)))
    full_conf = sorted(full, key=confidence_key)
    fallback_conf = sorted(fallback, key=confidence_key)
    ignored_counts: dict[str, int] = {}
    for x in ignored:
        k = str(x.get("hbtSupportLevel") or "UNKNOWN")
        ignored_counts[k] = ignored_counts.get(k, 0) + 1

    price_status = str(prices.get("status") or "PRICE_UNAVAILABLE")
    payload = {
        "schemaVersion": "HBT-SLATE-RANKING-2",
        "version": VERSION,
        "targetDate": s.get("targetDate"),
        "status": "RANKING_READY",
        "policy": policy,
        "coverage": {**coverage, "validatedEventForecastRows": len(event_rows), "eventFamiliesExcluded": len(event_excluded)},
        "rankingGate": gate,
        "priceLayer": {
            "status": price_status,
            "provider": prices.get("provider"),
            "primaryBookmaker": prices.get("primaryBookmaker"),
            "generatedAt": prices.get("generatedAt"),
            "pricedFixtures": prices.get("pricedFixtures", 0),
            "advisoryOnly": True,
            "note": "Prices annotate model calls after prediction. They do not alter HBT probabilities, simulation or R1 experiment eligibility.",
        },
        "testAReference": {
            "id": test_a.get("id") if test_a else None,
            "name": test_a.get("name") if test_a else None,
            "state": test_a.get("state") if test_a else None,
            "stakeZAR": test_a.get("stakeZAR") if test_a else None,
            "legs": test_a.get("legs") if test_a else None,
            "note": "Reference only. Ranking does not alter, remove, replace, or retrospectively optimise Test A.",
        },
        "rankings": {
            "highestRawDeployedPickProbability": [compact(x, prices) for x in raw],
            "strongestFullModelConfidence": [compact(x, prices) for x in full_conf],
            "fallbackOnly": [compact(x, prices) for x in fallback_conf],
            "validatedEventForecasts": event_rows,
            "eventMarketExcluded": event_excluded,
            "priceAssessment": {
                "status": price_status,
                "advisoryOnly": True,
                "reason": "Bookmaker price is reported downstream for money/value/CLV analysis. It does not decide what HBT thinks will happen or whether a model-supported R1 test is eligible."
            },
            "unsupportedOrIgnored": {
                "count": len(ignored),
                "bySupportState": ignored_counts,
                "detailSource": "slate_scanner.json",
                "reason": "Not silently dropped; full discovered fixture rows and exclusion reasons remain in the scanner output."
            }
        }
    }
    write(OUTPUT, payload)
    print("HBT slate ranking ready", {"supported1X2": len(rows), "eventForecastRows": len(event_rows), "eventExcluded": len(event_excluded), "priceStatus": price_status})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
