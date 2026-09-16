#!/usr/bin/env python3
"""HBT intelligence integrity + live quality audit.

This guard deliberately DOES NOT alter model probabilities, weights, features, or
match-intelligence payloads. It snapshots the guarded intelligence after collection
and verifies that downstream slate/price/ranking logic did not mutate it.

It also emits an observability-only quality audit so missing intelligence is visible
instead of being silently treated as zero or "good enough".
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "hbt_live_data"
INTEL = DATA / "hbt_1_4_match_intelligence.json"
REGISTRY = DATA / "hbt_1_4_feature_registry.json"
AUDIT = DATA / "hbt_intelligence_quality_audit.json"
SNAPSHOT = Path("/tmp/hbt_intelligence_integrity.sha256")
VERSION = "HBT-INTELLIGENCE-INTEGRITY-GUARD-1"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, obj: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def both_source_known(block: dict[str, Any]) -> bool:
    return bool((block.get("home") or {}).get("sourceKnown") and (block.get("away") or {}).get("sourceKnown"))


def finite_positive(v: Any) -> bool:
    try:
        x = float(v)
        return math.isfinite(x) and x > 0
    except Exception:
        return False


def audit_fixture(fx: dict[str, Any]) -> dict[str, bool]:
    tactical = fx.get("tactical") or {}
    impact = fx.get("playerTeamImpact") or {}
    setp = fx.get("setPieces") or {}
    gk = fx.get("shotStoppingGoalkeeper") or {}
    referee = fx.get("referee") or {}
    weather = fx.get("weatherVenue") or {}
    manager = fx.get("manager") or {}
    formation = fx.get("formation") or {}
    events = fx.get("eventMarkets") or {}
    props = fx.get("playerProps") or {}
    prop_rows = props.get("marketRows") or {}
    confirmed = fx.get("officialXI") or {}

    event_ok = True
    for fam in ("corners", "yellowCards", "shots", "shotsOnTarget"):
        m = events.get(fam) or {}
        h = m.get("history") or {}
        hist = [int(h.get(k) or 0) for k in ("homeForN", "homeAgainstN", "awayForN", "awayAgainstN")]
        event_ok = event_ok and m.get("validatedMarketModel") is True and finite_positive(m.get("totalLambda")) and min(hist or [0]) >= 3

    return {
        "confirmedXIObserved": confirmed.get("confirmed") is True,
        "confirmedXIFeaturesReady": fx.get("decisionReadinessState") == "CONFIRMED_XI_FEATURES_READY" and fx.get("testBComputable") is True,
        "tacticalDataReady": int(((tactical.get("home") or {}).get("n") or 0)) > 0 and int(((tactical.get("away") or {}).get("n") or 0)) > 0,
        "playerTeamImpactReady": finite_positive((impact.get("homeStarterAttack") or {}).get("matchedN")) and finite_positive((impact.get("awayStarterAttack") or {}).get("matchedN")) and impact.get("starterAttackIndexDiff") is not None,
        "workloadReady": both_source_known(fx.get("workload") or {}),
        "travelReady": both_source_known(fx.get("travel") or {}),
        "refereeReady": referee.get("known") is True and int(referee.get("priorMatches") or 0) > 0,
        "weatherContextReady": weather.get("qualityGate") is True and weather.get("usableForContext") is True,
        "managerReady": bool(manager.get("homeCoach") and manager.get("awayCoach")),
        "formationReady": bool((formation.get("home") or {}).get("confirmed") and (formation.get("away") or {}).get("confirmed")),
        "setPieceReady": int(((setp.get("home") or {}).get("priorMatchN") or 0)) > 0 and int(((setp.get("away") or {}).get("priorMatchN") or 0)) > 0,
        "goalkeeperReady": int(gk.get("homeGoalkeeperPriorN") or 0) > 0 and int(gk.get("awayGoalkeeperPriorN") or 0) > 0 and gk.get("homeGoalkeeperResidual") is not None and gk.get("awayGoalkeeperResidual") is not None,
        "validatedEventMarketsReady": event_ok,
        "validatedPlayerPropsReady": bool((prop_rows.get("home") or []) and (prop_rows.get("away") or [])),
    }


def validate_contract(reg: dict[str, Any], intel: dict[str, Any]) -> None:
    rp = reg.get("policy") or {}
    ip = intel.get("policy") or {}
    assert rp.get("bookmakerOddsUsed") is False, "registry allows bookmaker odds"
    assert rp.get("missingIsZero") is False, "registry treats missing intelligence as zero"
    assert ip.get("bookmakerOddsUsed") is False, "live intelligence contains bookmaker influence"
    assert ip.get("frozenPredictiveModelMutated") is False, "frozen predictive model mutation detected"
    assert ip.get("testAImmutable") is True, "Test A immutability contract broken"

    families = reg.get("families") or {}
    market = families.get("marketPrice") or {}
    assert market.get("status") == "decision-layer-only", market
    assert market.get("role") == "non-football", market

    # Research/context families must never silently become predictive just because
    # data exists. Promotion requires a separate validated model artifact.
    for name, fam in families.items():
        status = str(fam.get("status") or "")
        role = str(fam.get("role") or "")
        if any(tag in status for tag in ("build", "research", "partial", "retained-after")):
            assert role != "predictive", f"unvalidated family silently promoted: {name}"

    for name in ("corners", "yellowCards", "teamShots", "teamSOT"):
        assert (families.get(name) or {}).get("status") == "validated", name
    for name in ("playerShots", "playerSOT", "goalscorer"):
        assert (families.get(name) or {}).get("status") == "validated-confirmed-XI", name


def build_audit(reg: dict[str, Any], intel: dict[str, Any], digest: str) -> dict[str, Any]:
    fixtures = intel.get("fixtures") or {}
    per_fixture = {}
    totals: dict[str, int] = {}
    for key, fx in fixtures.items():
        flags = audit_fixture(fx)
        per_fixture[key] = {
            "home": fx.get("home"),
            "away": fx.get("away"),
            "kickoff": fx.get("kickoff"),
            "decisionReadinessState": fx.get("decisionReadinessState"),
            "flags": flags,
        }
        for k, v in flags.items():
            totals[k] = totals.get(k, 0) + int(bool(v))

    n = len(fixtures)
    coverage = {
        k: {"readyFixtures": v, "totalFixtures": n, "coverage": (v / n if n else 0.0)}
        for k, v in sorted(totals.items())
    }
    return {
        "schemaVersion": "HBT-INTELLIGENCE-QUALITY-AUDIT-1",
        "version": VERSION,
        "sourceGeneratedAt": intel.get("generatedAt"),
        "sourcePredictiveModel": intel.get("sourcePredictiveModel"),
        "sourceIntelligenceSha256": digest,
        "policy": {
            "observabilityOnly": True,
            "predictiveWeightsChanged": False,
            "probabilitiesChanged": False,
            "missingIsZero": False,
            "bookmakerOddsUsed": False,
            "downstreamMayMutateIntelligence": False,
            "researchFamilyPromotionRequiresChronologicalOOSValidation": True,
            "researchFamilyPromotionRequiresAblation": True,
            "researchFamilyPromotionRequiresCalibrationCheck": True,
        },
        "fixtureCount": n,
        "coverage": coverage,
        "health": intel.get("health") or {},
        "perFixture": per_fixture,
    }


def snapshot() -> int:
    reg, intel = read(REGISTRY), read(INTEL)
    validate_contract(reg, intel)
    digest = sha256(INTEL)
    SNAPSHOT.write_text(digest + "\n", encoding="utf-8")
    write(AUDIT, build_audit(reg, intel, digest))
    print("HBT intelligence integrity snapshot", digest, "fixtures", len(intel.get("fixtures") or {}))
    return 0


def verify() -> int:
    if not SNAPSHOT.exists():
        raise RuntimeError("intelligence snapshot hash is missing")
    expected = SNAPSHOT.read_text(encoding="utf-8").strip()
    actual = sha256(INTEL)
    assert actual == expected, f"DOWNSTREAM INTELLIGENCE MUTATION DETECTED: {expected} != {actual}"
    reg, intel = read(REGISTRY), read(INTEL)
    validate_contract(reg, intel)
    audit = read(AUDIT)
    audit["downstreamIntegrityVerified"] = True
    audit["verifiedIntelligenceSha256"] = actual
    write(AUDIT, audit)
    print("HBT downstream intelligence integrity verified", actual)
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "snapshot"
    if mode == "snapshot":
        raise SystemExit(snapshot())
    if mode == "verify":
        raise SystemExit(verify())
    raise SystemExit(f"usage: {Path(sys.argv[0]).name} [snapshot|verify]")
