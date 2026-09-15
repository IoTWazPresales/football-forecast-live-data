#!/usr/bin/env python3
"""Rank HBT slate candidates only after the discovery gate passes.

This consumes slate_scanner.json; it does not fetch odds, retrain models, create
probabilities, or alter live experiments. FULL_MODEL and FALLBACK stay separate.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hbt_live_data"
SLATE = OUT / "slate_scanner.json"
EXPERIMENTS = OUT / "live_experiments.json"
OUTPUT = OUT / "ranked_candidates.json"
VERSION = "HBT-SLATE-RANKER-1"
TIER_ORDER = {"A": 0, "B": 1, "C": 2, "Avoid": 3, None: 4, "": 4}


def read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write(path: Path, obj: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def compact(row: dict[str, Any]) -> dict[str, Any]:
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


def main() -> int:
    s = read(SLATE, {})
    gate = s.get("rankingGate") or {}
    coverage = s.get("coverage") or {}
    ex = read(EXPERIMENTS, {})
    test_a = next((x for x in ex.get("experiments") or [] if x.get("id") == "PRE_XI_TEST_A_2026-09-15"), None)

    policy = {
        "discoveryGateRequired": True,
        "bookmakerOddsUsed": False,
        "footballProbabilitiesRecomputed": False,
        "fullModelAndFallbackSeparated": True,
        "rawProbabilityIsNotBettingValue": True,
        "universalBestBetsClaimAllowed": False,
        "configuredSourceRankingLabel": "Best HBT-supported candidates from the configured-source discovered slate",
        "testAImmutable": bool((ex.get("policy") or {}).get("testAImmutable") and test_a and test_a.get("state") == "FROZEN_PROSPECTIVE"),
    }

    if gate.get("discoveryComplete") is not True:
        payload = {
            "schemaVersion": "HBT-SLATE-RANKING-1",
            "version": VERSION,
            "targetDate": s.get("targetDate"),
            "status": "BLOCKED_DISCOVERY_INCOMPLETE",
            "policy": policy,
            "coverage": coverage,
            "rankingGate": gate,
            "reason": "Slate discovery/reconciliation gate is not complete; ranking is intentionally withheld.",
            "testAReference": test_a,
            "rankings": None,
        }
        write(OUTPUT, payload)
        print("HBT slate ranking blocked: discovery incomplete")
        return 2

    rows = [x for x in s.get("fixtures") or [] if x.get("rankEligible") and x.get("pickProbability") is not None]
    full = [x for x in rows if x.get("hbtSupportLevel") == "FULL_MODEL"]
    fallback = [x for x in rows if x.get("hbtSupportLevel") == "FALLBACK"]
    ignored = [x for x in s.get("fixtures") or [] if not x.get("rankEligible")]

    raw = sorted(rows, key=lambda x: (-p(x), TIER_ORDER.get(x.get("tier"), 4), -q(x)))
    full_conf = sorted(full, key=confidence_key)
    fallback_conf = sorted(fallback, key=confidence_key)
    ignored_counts: dict[str, int] = {}
    for x in ignored:
        k = str(x.get("hbtSupportLevel") or "UNKNOWN")
        ignored_counts[k] = ignored_counts.get(k, 0) + 1

    payload = {
        "schemaVersion": "HBT-SLATE-RANKING-1",
        "version": VERSION,
        "targetDate": s.get("targetDate"),
        "status": "RANKING_READY",
        "policy": policy,
        "coverage": coverage,
        "rankingGate": gate,
        "testAReference": {
            "id": test_a.get("id") if test_a else None,
            "name": test_a.get("name") if test_a else None,
            "state": test_a.get("state") if test_a else None,
            "stakeZAR": test_a.get("stakeZAR") if test_a else None,
            "legs": test_a.get("legs") if test_a else None,
            "note": "Reference only. Ranking does not alter, remove, replace, or retrospectively optimise Test A.",
        },
        "rankings": {
            "highestRawDeployedPickProbability": [compact(x) for x in raw],
            "strongestFullModelConfidence": [compact(x) for x in full_conf],
            "fallbackOnly": [compact(x) for x in fallback_conf],
            "experimentalValueVsPrice": {
                "status": "UNAVAILABLE_NO_BOOKMAKER_PRICE",
                "reason": "The football model and slate scanner deliberately exclude bookmaker odds. Probability alone is not betting value."
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
    print("HBT slate ranking ready", {
        "supported": len(rows), "fullModel": len(full), "fallback": len(fallback), "ignored": len(ignored),
        "rawTop": [(x.get("pick"), round(100*p(x), 2), x.get("hbtSupportLevel")) for x in raw[:5]],
        "fullTop": [(x.get("pick"), round(100*p(x), 2), x.get("tier")) for x in full_conf],
        "fallbackTop": [(x.get("pick"), round(100*p(x), 2), x.get("tier")) for x in fallback_conf[:5]],
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
