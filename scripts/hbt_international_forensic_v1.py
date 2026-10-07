#!/usr/bin/env python3
"""Guard-aware forensic settlement for HBT-1.4 international prospective evidence.

Settles only immutable pre-kickoff international challenger rows that already
exist in the repository. It never fabricates missed prospective predictions,
never reads bookmaker odds, and never retunes model parameters.

Outputs are idempotent:
- hbt_international_forensic_settlement.json
- hbt_international_evidence_registry.json
- hbt_international_learning_assessment.json

Identity/timing/context blocked rows remain auditable but are excluded from
predictive-learning metrics.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import urllib.parse
from pathlib import Path
from typing import Any

import hbt_international_challenger_v1 as v1

ROOT = Path(__file__).resolve().parents[1]
INTL = ROOT / "hbt_live_data" / "international"
VERSION = "HBT-1.4-INTERNATIONAL-FORENSIC-1"


def read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_date_from_name(path: Path) -> dt.date | None:
    try:
        return dt.date.fromisoformat(path.stem.rsplit("_", 1)[-1])
    except Exception:
        return None


def score_value(v: Any) -> int | None:
    if isinstance(v, dict):
        for k in ("value", "displayValue", "score"):
            if k in v:
                return score_value(v.get(k))
        return None
    try:
        return int(float(str(v)))
    except Exception:
        return None


def fetch_result(event_id: str) -> dict[str, Any]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/summary?event={urllib.parse.quote(event_id)}"
    try:
        raw = json.loads(v1.http_bytes(url, 20).decode("utf-8", "replace"))
    except Exception as exc:
        return {"available": False, "completed": False, "error": str(exc)[:240]}

    header = raw.get("header") or {}
    comps = header.get("competitions") or []
    comp = comps[0] if comps else {}
    status = ((comp.get("status") or {}).get("type") or {})
    completed = bool(status.get("completed"))
    teams = comp.get("competitors") or []

    def side(which: str) -> dict[str, Any]:
        row = next((x for x in teams if x.get("homeAway") == which), {})
        team = row.get("team") or {}
        return {
            "name": team.get("displayName") or team.get("name") or "",
            "id": str(team.get("id") or ""),
            "score": score_value(row.get("score")),
        }

    home, away = side("home"), side("away")
    return {
        "available": True,
        "completed": completed,
        "status": status.get("name") or status.get("description"),
        "home": home,
        "away": away,
        "competition": (header.get("league") or {}),
    }


def result_code(h: int, a: int) -> str:
    return "H" if h > a else "A" if h < a else "D"


def prob_fingerprint(row: dict[str, Any]) -> str:
    payload = {
        "fixture": row.get("fixture"),
        "predictionMode": row.get("predictionMode"),
        "probs": row.get("probs"),
        "capture": row.get("capture"),
        "sourceFixtureId": row.get("sourceFixtureId"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def evidence_id(source: str, row: dict[str, Any]) -> str:
    payload = f"{source}|{row.get('sourceFixtureId')}|{prob_fingerprint(row)}"
    return hashlib.sha256(payload.encode()).hexdigest()


def outcome_metrics(probs: dict[str, Any], result: str) -> tuple[float, float, bool] | None:
    try:
        p = [float(probs[x]) for x in ("H", "D", "A")]
    except Exception:
        return None
    if any((x < 0 or x > 1 or not math.isfinite(x)) for x in p):
        return None
    y = {"H": 0, "D": 1, "A": 2}[result]
    ll = -math.log(max(p[y], 1e-15))
    brier = sum((p[i] - (1.0 if i == y else 0.0)) ** 2 for i in range(3))
    hit = max(range(3), key=lambda i: p[i]) == y
    return ll, brier, hit


def aggregate(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    vals = []
    for r in rows:
        m = r.get(key)
        if isinstance(m, dict) and all(k in m for k in ("logLoss", "brier", "topPickHit")):
            vals.append(m)
    if not vals:
        return {"n": 0, "logLoss": None, "brier": None, "accuracy": None}
    return {
        "n": len(vals),
        "logLoss": sum(float(x["logLoss"]) for x in vals) / len(vals),
        "brier": sum(float(x["brier"]) for x in vals) / len(vals),
        "accuracy": sum(1 for x in vals if x["topPickHit"]) / len(vals),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="Current causal target date YYYY-MM-DD")
    args = ap.parse_args()
    target = dt.date.fromisoformat(args.date)

    old_registry = read(INTL / "hbt_international_evidence_registry.json", {})
    old_ids = {str(x.get("evidenceId")) for x in (old_registry.get("records") or []) if x.get("evidenceId")}

    records: list[dict[str, Any]] = []
    source_cards = 0
    for path in sorted(INTL.glob("hbt_international_intelligence_????-??-??.json")):
        card_date = parse_date_from_name(path)
        if not card_date or card_date >= target:
            continue
        doc = read(path, {})
        if doc.get("targetDate") != card_date.isoformat():
            continue
        source_cards += 1
        for row in doc.get("prospectiveCandidates") or []:
            eid = evidence_id(path.name, row)
            fx = row.get("fixture") or {}
            capture = row.get("capture") or {}
            vc = row.get("venueContext") or {}
            event_id = str(row.get("sourceFixtureId") or "")
            reasons = []

            if capture.get("statusAtCapture") != "PRE_KICKOFF":
                reasons.append("TIMING_NOT_PRE_KICKOFF")
            if row.get("cleanProspectiveEligible") is not True:
                reasons.append("PROSPECTIVE_GUARD_NOT_CLEAN")
            if vc.get("probabilityContextVerified") is not True:
                reasons.append("VENUE_CONTEXT_UNVERIFIED")
            if not event_id:
                reasons.append("EVENT_ID_MISSING")
            if not row.get("probs"):
                reasons.append("PROBABILITY_MISSING")

            settled = fetch_result(event_id) if event_id else {"available": False, "completed": False}
            if not settled.get("available"):
                reasons.append("RESULT_SOURCE_UNAVAILABLE")
            elif not settled.get("completed"):
                reasons.append("RESULT_NOT_FINAL")

            identity_ok = False
            outcome = None
            current_metrics = None
            structural_metrics = None
            if settled.get("available"):
                h_exp, a_exp = v1.norm(fx.get("home")), v1.norm(fx.get("away"))
                h_got, a_got = v1.norm((settled.get("home") or {}).get("name")), v1.norm((settled.get("away") or {}).get("name"))
                identity_ok = bool(h_exp and a_exp and h_exp == h_got and a_exp == a_got)
                if not identity_ok:
                    reasons.append("IDENTITY_MISMATCH")
                hs, aas = (settled.get("home") or {}).get("score"), (settled.get("away") or {}).get("score")
                if settled.get("completed") and isinstance(hs, int) and isinstance(aas, int):
                    outcome = result_code(hs, aas)
                    if identity_ok:
                        mm = outcome_metrics(row.get("probs") or {}, outcome)
                        if mm:
                            current_metrics = {"logLoss": mm[0], "brier": mm[1], "topPickHit": mm[2]}
                        base = row.get("baseStructuralProbabilityBeforeRecentInteraction")
                        bm = outcome_metrics(base or {}, outcome) if isinstance(base, dict) else None
                        if bm:
                            structural_metrics = {"logLoss": bm[0], "brier": bm[1], "topPickHit": bm[2]}

            eligible = not reasons and bool(outcome and current_metrics)
            records.append({
                "evidenceId": eid,
                "evidenceClass": "CLEAN_PROSPECTIVE" if eligible else "GUARD_BLOCKED_OR_PENDING",
                "learningEligible": eligible,
                "sourceArtifact": path.name,
                "targetDate": card_date.isoformat(),
                "fixture": fx,
                "sourceFixtureId": event_id or None,
                "probabilityFingerprint": prob_fingerprint(row),
                "predictionMode": row.get("predictionMode"),
                "probs": row.get("probs"),
                "baseStructuralProbabilityBeforeRecentInteraction": row.get("baseStructuralProbabilityBeforeRecentInteraction"),
                "quality": row.get("quality"),
                "capture": capture,
                "venueContext": vc,
                "resultVerification": settled,
                "identityVerified": identity_ok,
                "result": outcome,
                "predictiveMetrics": current_metrics,
                "structuralOnlyMetrics": structural_metrics,
                "exclusionReasons": sorted(set(reasons)),
            })

    # Unique/idempotent by evidenceId.
    uniq = {r["evidenceId"]: r for r in records}
    records = [uniq[k] for k in sorted(uniq)]
    eligible = [r for r in records if r.get("learningEligible")]

    current = aggregate(eligible, "predictiveMetrics")
    structural = aggregate(eligible, "structuralOnlyMetrics")
    if current["n"] and structural["n"] == current["n"]:
        delta_ll = current["logLoss"] - structural["logLoss"]
        delta_br = current["brier"] - structural["brier"]
        if delta_ll < 0 and delta_br < 0:
            interaction_status = "PROSPECTIVE_SUPPORTING"
        elif delta_ll > 0 and delta_br > 0:
            interaction_status = "PROSPECTIVE_CONTRADICTING"
        else:
            interaction_status = "PROSPECTIVE_MIXED"
    else:
        delta_ll = delta_br = None
        interaction_status = "INSUFFICIENT_COMPARABLE_PROSPECTIVE_EVIDENCE"

    new_ids = {r["evidenceId"] for r in records} - old_ids
    generated = now()
    settlement = {
        "schemaVersion": "HBT-INTERNATIONAL-FORENSIC-SETTLEMENT-1",
        "version": VERSION,
        "generatedAt": generated,
        "asOfTargetDate": target.isoformat(),
        "policy": {
            "retrospectivePredictionsFabricated": False,
            "identityTimingBlockedExcludedFromLearning": True,
            "bookmakerOddsRead": False,
            "modelRetuned": False,
            "existingIntelligenceDeleted": False,
        },
        "summary": {
            "sourceCards": source_cards,
            "uniqueEvidenceRows": len(records),
            "learningEligible": len(eligible),
            "blockedOrPending": len(records) - len(eligible),
            "newUniqueEvidence": len(new_ids),
        },
        "records": records,
    }
    registry = {
        "schemaVersion": "HBT-INTERNATIONAL-EVIDENCE-REGISTRY-1",
        "generatedAt": generated,
        "asOfTargetDate": target.isoformat(),
        "idempotentKey": "evidenceId",
        "policy": {
            "cleanProspectiveOnlyForPredictiveLearning": True,
            "legacyEvidenceHypothesisOnly": True,
            "guardBlockedRowsRetainedForAudit": True,
            "automaticPromotion": False,
        },
        "summary": settlement["summary"],
        "records": records,
    }
    assessment = {
        "schemaVersion": "HBT-INTERNATIONAL-LEARNING-ASSESSMENT-1",
        "generatedAt": generated,
        "asOfTargetDate": target.isoformat(),
        "newEvidenceAdded": bool(new_ids),
        "cleanProspective": current,
        "structuralOnlyComparable": structural,
        "recentInteractionProspectiveStatus": interaction_status,
        "deltaLogLossRecentVsStructural": delta_ll,
        "deltaBrierRecentVsStructural": delta_br,
        "promotionAllowed": False,
        "promotionBlock": "clean prospective evidence remains too limited for governed promotion; continue shadow confirmation and interaction/ablation testing",
        "retuningPerformed": False,
    }

    write(INTL / "hbt_international_forensic_settlement.json", settlement)
    write(INTL / "hbt_international_evidence_registry.json", registry)
    write(INTL / "hbt_international_learning_assessment.json", assessment)
    print(json.dumps({"settlement": settlement["summary"], "assessment": assessment}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
