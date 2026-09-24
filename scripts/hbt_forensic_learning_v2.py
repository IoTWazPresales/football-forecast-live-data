#!/usr/bin/env python3
"""HBT forensic learning v2.

Adds two hard rules to v1 without mutating predictive intelligence:
1) execution-surface identity/timing blocks are guard evidence, not model-learning data;
2) exact frozen R0 markets are settled even when stake is zero.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import hbt_forensic_learning_v1 as base

DATA = base.DATA
FORENSIC = base.FORENSIC
VERSION = "HBT-FORENSIC-LEARNING-2-GUARD-AWARE"


def load_surface(date: str) -> dict[str, Any]:
    return base.read_json(DATA / f"hbt_execution_surface_{date}.json", {})


def surface_index(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in doc.get("rows") or []:
        fx = row.get("fixture") or {}
        key = base.fixture_key(fx.get("home"), fx.get("away"))
        if key != "|":
            out[key] = row
    return out


def update_registry(audits: list[dict[str, Any]]) -> dict[str, Any]:
    path = FORENSIC / "hbt_learning_hypotheses.json"
    reg = base.read_json(path, {"schemaVersion": "HBT-LEARNING-HYPOTHESES-1", "version": VERSION, "hypotheses": {}})
    hyp = reg.setdefault("hypotheses", {})
    for a in audits:
        if not a.get("learning", {}).get("eligibleForPredictiveLearning", True):
            continue
        for tag in a.get("learning", {}).get("hypothesisTags", []):
            z = hyp.setdefault(tag, {"status": "OBSERVE", "occurrences": 0, "lossOccurrences": 0, "examples": [], "promotionAllowed": False})
            z["occurrences"] += 1
            if a.get("execution", {}).get("settlement") == "LOSS" or a.get("shadowR0", {}).get("settlement") == "LOSS" or a.get("predictionOutcome", {}).get("topPickCorrect") is False:
                z["lossOccurrences"] += 1
            ex = {
                "date": a.get("date"), "fixture": a.get("fixture"),
                "actual": a.get("actual", {}).get("result"),
                "sourceHash": a.get("preMatch", {}).get("immutableHash"),
            }
            if ex not in z["examples"]:
                z["examples"] = (z["examples"] + [ex])[-12:]
    reg["updatedAt"] = base.now_iso()
    reg["version"] = VERSION
    reg["policy"] = {
        "automaticModelMutation": False,
        "automaticFeaturePromotion": False,
        "promotionRequiresHistoricalBacktest": True,
        "promotionRequiresUnseenHoldoutImprovement": True,
        "preserveExistingIntelligence": True,
        "executionGuardBlockedRowsExcludedFromPredictiveLearning": True,
    }
    base.write_json(path, reg)
    return reg


def run(date: str) -> dict[str, Any]:
    source_path, source_doc, rows = base.source_candidates(date)
    scoreboard = base.fetch_scoreboard(date)
    execution = base.load_execution(date)
    exec_idx = {base.fixture_key(x.get("home"), x.get("away")): x for x in execution.get("singles") or []}
    surface_doc = load_surface(date)
    surf_idx = surface_index(surface_doc)

    audits: list[dict[str, Any]] = []
    for row in rows:
        fx = base.row_fixture(row)
        home, away = fx.get("home"), fx.get("away")
        key = base.fixture_key(home, away)
        surface = surf_idx.get(key)
        guard_reason = (surface or {}).get("executionBlockReason")
        learning_eligible = guard_reason is None

        event_id = str(fx.get("sourceFixtureId") or "")
        result = scoreboard.get(f"id:{event_id}") if event_id else None
        result = result or scoreboard.get(key)
        p = base.probs3(row)
        audit: dict[str, Any] = {
            "date": date,
            "fixture": f"{home} vs {away}",
            "home": home,
            "away": away,
            "preMatch": {
                "sourceFile": source_path.name,
                "sourceCapturedAt": source_doc.get("capturedAt") or source_doc.get("generatedAt"),
                "immutableHash": base.canonical_hash(row),
                "origin": row.get("origin") or source_doc.get("origin"),
                "tier": row.get("tier"), "rawTier": row.get("rawTier"), "quality": row.get("quality"),
                "coverage": row.get("coverage"), "coveragePack": row.get("coveragePack"),
                "predictionMode": row.get("predictionMode"), "probsHDA": p,
                "bookmakerObservedBeforeCapture": bool((source_doc.get("policy") or {}).get("bookmakerPriceObservedBeforeCapture", False)),
            },
            "executionGuard": {
                "surfacePresent": surface is not None,
                "eligibleAtSurface": (surface or {}).get("executionEligibleNow"),
                "blockReason": guard_reason,
                "guardOutcome": "BLOCKED_CORRECTLY_NO_MODEL_LEARNING" if guard_reason else "NOT_BLOCKED",
            },
            "actual": {"settled": False},
            "predictionOutcome": {},
            "shadowR0": {},
            "execution": {},
            "processEvidence": {},
            "learning": {"eligibleForPredictiveLearning": learning_eligible},
        }

        if not result or not result.get("completed") or result.get("homeScore") is None or result.get("awayScore") is None or not p:
            audit["learning"].update({
                "hypothesisTags": [] if not learning_eligible else ["UNSETTLED_OR_RESULT_DATA_GAP"],
                "researchRequired": learning_eligible,
                "modelMutationAllowed": False,
                "featurePromotionAllowed": False,
            })
            audits.append(audit)
            continue

        hs, as_ = float(result["homeScore"]), float(result["awayScore"])
        rc = base.result_code(hs, as_)
        actual_idx = {"H": 0, "D": 1, "A": 2}[rc]
        actual_p = p[actual_idx]
        pick_idx = max(range(3), key=lambda i: p[i])
        pick = ["H", "D", "A"][pick_idx]
        y = [1.0 if i == actual_idx else 0.0 for i in range(3)]
        brier = sum((p[i] - y[i]) ** 2 for i in range(3))
        logloss = -math.log(max(actual_p, 1e-12))
        audit["actual"] = {
            "settled": True, "homeScore": hs, "awayScore": as_, "result": rc,
            "eventId": result.get("eventId"), "competition": result.get("competition"),
        }
        audit["predictionOutcome"] = {
            "topPick": pick, "topPickProbability": p[pick_idx], "topPickCorrect": pick == rc,
            "actualOutcomeProbability": actual_p, "brier": brier, "logLoss": logloss,
        }

        if surface and (surface.get("r0Tracking") or {}).get("marketFrozen"):
            r0 = surface.get("r0Tracking") or {}
            market = str(r0.get("marketFrozen") or "")
            audit["shadowR0"] = {
                "market": market,
                "selection": r0.get("selectionFrozen"),
                "stake": 0,
                "settlement": base.settle_market({"market": market}, hs, as_),
                "eligibleForCalibration": learning_eligible,
            }

        ex = exec_idx.get(key)
        market_result = None
        if ex:
            market_result = base.settle_market(ex, hs, as_)
            odds = float(ex.get("odds")) if ex.get("odds") is not None else None
            stake = float(ex.get("stake")) if ex.get("stake") is not None else None
            if market_result == "WIN" and odds and stake is not None:
                ret = stake * odds
            elif market_result == "VOID" and stake is not None:
                ret = stake
            elif market_result == "LOSS":
                ret = 0.0
            else:
                ret = None
            audit["execution"] = {
                **ex, "settlement": market_result, "return": ret,
                "profit": (ret - stake) if ret is not None and stake is not None else None,
            }

        if not learning_eligible:
            audit["learning"].update({
                "hypothesisTags": [],
                "researchRequired": False,
                "modelMutationAllowed": False,
                "featurePromotionAllowed": False,
                "nextStep": "Retain as execution-guard evidence only; exclude from calibration and predictive learning",
            })
            audits.append(audit)
            continue

        summary = base.summary_for(str(result.get("eventId") or event_id), fx.get("league"))
        post = base.parse_stats(summary)
        flags = base.process_flags(post, home, away, rc, pick)
        audit["processEvidence"] = post
        tags = base.hypothesis_tags(row, actual_p, market_result or audit.get("shadowR0", {}).get("settlement"), flags)
        audit["learning"].update({
            "hypothesisTags": tags,
            "researchRequired": bool(market_result == "LOSS" or audit.get("shadowR0", {}).get("settlement") == "LOSS" or pick != rc or tags),
            "modelMutationAllowed": False,
            "featurePromotionAllowed": False,
            "nextStep": "Historical backtest + unseen holdout validation before any promotion" if tags else "Accumulate calibration evidence",
        })
        audits.append(audit)

    settled_rows = [a for a in audits if a.get("actual", {}).get("settled")]
    eligible = [a for a in settled_rows if a.get("learning", {}).get("eligibleForPredictiveLearning")]
    blocked = [a for a in audits if not a.get("learning", {}).get("eligibleForPredictiveLearning")]
    top_correct = sum(1 for a in eligible if a.get("predictionOutcome", {}).get("topPickCorrect"))
    r0_rows = [a for a in eligible if a.get("shadowR0", {}).get("settlement") in {"WIN", "LOSS", "VOID"}]
    r0_w = sum(a["shadowR0"]["settlement"] == "WIN" for a in r0_rows)
    r0_l = sum(a["shadowR0"]["settlement"] == "LOSS" for a in r0_rows)
    r0_v = sum(a["shadowR0"]["settlement"] == "VOID" for a in r0_rows)
    exec_rows = [a for a in settled_rows if a.get("execution", {}).get("settlement")]
    stake = sum(float(a["execution"].get("stake") or 0) for a in exec_rows)
    ret = sum(float(a["execution"].get("return") or 0) for a in exec_rows)

    out = {
        "schemaVersion": "HBT-FORENSIC-AUDIT-2",
        "version": VERSION,
        "generatedAt": base.now_iso(),
        "targetDate": date,
        "policy": {
            "preMatchForecastImmutable": True,
            "postMatchEvidenceMayNotRewriteCapture": True,
            "executionGuardBlockedRowsExcludedFromPredictiveLearning": True,
            "exactR0MarketSettlementEnabled": True,
            "automaticModelMutation": False,
            "automaticFeaturePromotion": False,
            "preserveExistingIntelligence": True,
            "hypothesesMustBeBacktested": True,
            "holdoutValidationRequired": True,
        },
        "source": {
            "prospectiveCard": source_path.name,
            "sourceHash": base.canonical_hash(source_doc),
            "executionSurface": f"hbt_execution_surface_{date}.json" if surface_doc else None,
        },
        "summary": {
            "rawForecastRows": len(audits),
            "settledRows": len(settled_rows),
            "learningEligibleSettled": len(eligible),
            "guardBlockedRows": len(blocked),
            "topPickCorrectEligible": top_correct,
            "topPickAccuracyEligible": top_correct / len(eligible) if eligible else None,
            "meanBrierEligible": sum(a["predictionOutcome"]["brier"] for a in eligible) / len(eligible) if eligible else None,
            "meanLogLossEligible": sum(a["predictionOutcome"]["logLoss"] for a in eligible) / len(eligible) if eligible else None,
            "shadowR0Settled": len(r0_rows),
            "shadowR0Wins": int(r0_w), "shadowR0Losses": int(r0_l), "shadowR0Voids": int(r0_v),
            "verifiedExecutions": len(exec_rows),
            "executionStake": stake, "executionReturn": ret, "executionProfit": ret - stake,
        },
        "audits": audits,
        "multis": execution.get("multis") or [],
    }
    FORENSIC.mkdir(parents=True, exist_ok=True)
    base.write_json(FORENSIC / f"hbt_forensic_{date}.json", out)
    update_registry(audits)
    return out


def self_test() -> None:
    assert base.settle_market({"market": "1X"}, 1, 1) == "WIN"
    assert base.settle_market({"market": "12"}, 1, 1) == "LOSS"
    assert surface_index({"rows": [{"fixture": {"home": "A", "away": "B"}}]})
    print("HBT forensic v2 self-test: PASS")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test(); return 0
    if not args.date:
        raise SystemExit("--date required")
    out = run(args.date)
    print(json.dumps(out["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
