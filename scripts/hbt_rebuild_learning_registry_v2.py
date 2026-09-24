#!/usr/bin/env python3
"""Rebuild HBT learning hypothesis registry from unique forensic evidence.

This is intentionally idempotent. Re-running a forensic day cannot inflate counts.
Legacy v1 audits are preserved as a separate lower-trust evidence class; v2
execution-guard-aware audits contribute clean evidence only when explicitly
eligible for predictive learning.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hbt_forensic_learning_v1 import FORENSIC, now_iso, read_json, write_json

VERSION = "HBT-LEARNING-REGISTRY-2-UNIQUE-EVIDENCE"
OUT = FORENSIC / "hbt_learning_hypotheses_v2.json"


def evidence_key(tag: str, audit: dict[str, Any]) -> str:
    pre = audit.get("preMatch") or {}
    return "|".join([
        tag,
        str(audit.get("date") or ""),
        str(audit.get("fixture") or ""),
        str(pre.get("immutableHash") or ""),
    ])


def is_loss(audit: dict[str, Any]) -> bool:
    if (audit.get("execution") or {}).get("settlement") == "LOSS":
        return True
    if (audit.get("shadowR0") or {}).get("settlement") == "LOSS":
        return True
    return (audit.get("predictionOutcome") or {}).get("topPickCorrect") is False


def main() -> int:
    hypotheses: dict[str, dict[str, Any]] = {}
    seen_global: set[str] = set()
    files = sorted(p for p in FORENSIC.glob("hbt_forensic_*.json") if "research" not in p.name)
    audit_files = 0
    audit_rows = 0
    clean_rows = 0
    legacy_rows = 0
    blocked_rows = 0

    for path in files:
        doc = read_json(path, {})
        if not doc.get("audits"):
            continue
        audit_files += 1
        schema = str(doc.get("schemaVersion") or "")
        is_v2 = schema == "HBT-FORENSIC-AUDIT-2"
        for audit in doc.get("audits") or []:
            audit_rows += 1
            learning = audit.get("learning") or {}
            eligible = bool(learning.get("eligibleForPredictiveLearning", True))
            if is_v2 and not eligible:
                blocked_rows += 1
                continue
            evidence_class = "CLEAN_GUARD_AWARE" if is_v2 else "LEGACY_V1_UNFILTERED"
            if is_v2:
                clean_rows += 1
            else:
                legacy_rows += 1
            for tag in learning.get("hypothesisTags") or []:
                key = evidence_key(str(tag), audit)
                if key in seen_global:
                    continue
                seen_global.add(key)
                h = hypotheses.setdefault(str(tag), {
                    "status": "OBSERVE",
                    "promotionAllowed": False,
                    "uniqueOccurrences": 0,
                    "cleanOccurrences": 0,
                    "legacyOccurrences": 0,
                    "uniqueLossOccurrences": 0,
                    "cleanLossOccurrences": 0,
                    "legacyLossOccurrences": 0,
                    "examples": [],
                    "evidenceIds": [],
                })
                loss = is_loss(audit)
                h["uniqueOccurrences"] += 1
                h["uniqueLossOccurrences"] += int(loss)
                if evidence_class == "CLEAN_GUARD_AWARE":
                    h["cleanOccurrences"] += 1
                    h["cleanLossOccurrences"] += int(loss)
                else:
                    h["legacyOccurrences"] += 1
                    h["legacyLossOccurrences"] += int(loss)
                h["evidenceIds"].append(key)
                ex = {
                    "date": audit.get("date"),
                    "fixture": audit.get("fixture"),
                    "actual": (audit.get("actual") or {}).get("result"),
                    "sourceHash": (audit.get("preMatch") or {}).get("immutableHash"),
                    "evidenceClass": evidence_class,
                    "lossEvidence": loss,
                }
                h["examples"] = (h["examples"] + [ex])[-20:]

    out = {
        "schemaVersion": "HBT-LEARNING-HYPOTHESES-2",
        "version": VERSION,
        "generatedAt": now_iso(),
        "policy": {
            "idempotentUniqueEvidenceCounting": True,
            "executionGuardBlockedRowsExcluded": True,
            "legacyV1EvidencePreservedSeparately": True,
            "legacyV1EvidenceMayNotAutoPromote": True,
            "automaticModelMutation": False,
            "automaticFeaturePromotion": False,
            "promotionRequiresHistoricalBacktest": True,
            "promotionRequiresUnseenHoldoutImprovement": True,
            "preserveExistingIntelligence": True,
        },
        "coverage": {
            "forensicFiles": audit_files,
            "auditRows": audit_rows,
            "cleanGuardAwareRows": clean_rows,
            "legacyV1Rows": legacy_rows,
            "guardBlockedRowsExcluded": blocked_rows,
            "uniqueEvidenceItems": len(seen_global),
        },
        "hypotheses": hypotheses,
    }
    write_json(OUT, out)
    print(json.dumps({"coverage": out["coverage"], "hypotheses": len(hypotheses)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
