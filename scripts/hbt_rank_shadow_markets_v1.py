#!/usr/bin/env python3
"""Rank prospective HBT shadow markets without depending on frozen L0 parity.

This is a research/test output layer only.
- Never mutates HBT intelligence or predictive parameters.
- Never uses bookmaker odds to create probabilities.
- Only exposes player-prop rows that passed the HBT-1.4.2 confirmed-XI identity
  gate and holdout-market validation.
- Event markets remain fail-closed unless the live collector emitted an explicit
  validated probability.
- Frozen-control 1X2/derived goal markets remain separately blocked when the
  exact frozen L0 runtime is unavailable. Their parity problem must not suppress
  independently validated shadow-market tests.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hbt_live_data"
INTEL = OUT / "hbt_1_4_match_intelligence.json"
FROZEN_STATUS = OUT / "forecast_bridge_status.json"
VERSION = "HBT-SHADOW-MARKET-RANKER-1"

PROP_FIELDS = {
    "shots1Plus": ("pShot1Plus", "PLAYER_SHOTS", "1+ shots"),
    "shots2Plus": ("pShot2Plus", "PLAYER_SHOTS", "2+ shots"),
    "shots3Plus": ("pShot3Plus", "PLAYER_SHOTS", "3+ shots"),
    "sot1Plus": ("pSOT1Plus", "PLAYER_SOT", "1+ shots on target"),
    "sot2Plus": ("pSOT2Plus", "PLAYER_SOT", "2+ shots on target"),
    "anytimeGoal": ("pAnytimeGoalRaw", "ANYTIME_GOAL", "anytime goalscorer"),
}


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


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_dt(v: Any) -> dt.datetime | None:
    try:
        x = dt.datetime.fromisoformat(str(v or "").replace("Z", "+00:00"))
        return x if x.tzinfo else x.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def fair(p: float | None) -> float | None:
    return 1.0 / p if isinstance(p, (int, float)) and p > 0 else None


def explicit_event_probabilities(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose only explicit probability fields from validated event families.

    We intentionally do not turn lambdas/means into market probabilities here.
    That would create a new model in the output layer.
    """
    allowed = set(row.get("validatedEventFamilies") or [])
    event = row.get("eventMarkets") or {}
    out: list[dict[str, Any]] = []
    for family in sorted(allowed):
        d = event.get(family)
        if not isinstance(d, dict):
            continue
        for key, val in d.items():
            lk = str(key).lower()
            if not (lk.startswith("p") or "prob" in lk):
                continue
            if not isinstance(val, (int, float)) or not (0 <= float(val) <= 1):
                continue
            p = float(val)
            out.append({
                "origin": "HBT_SHADOW",
                "action": "TEST",
                "family": f"EVENT_{family.upper()}",
                "marketKey": str(key),
                "selection": f"{family}: {key}",
                "modelProbability": p,
                "fairOdds": fair(p),
                "priceStatus": "UNPRICED_TEST",
                "validation": "live event family marked validated; explicit probability emitted by HBT collector",
            })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    intel = read(INTEL, {})
    bridge = read(FROZEN_STATUS, {})
    captured = dt.datetime.now(dt.timezone.utc)
    candidates: list[dict[str, Any]] = []
    fixture_states: list[dict[str, Any]] = []

    for fid, row in (intel.get("fixtures") or {}).items():
        kickoff = parse_dt(row.get("kickoff"))
        if not kickoff or kickoff.date().isoformat() != args.date:
            continue

        fx = {
            "fixtureId": fid,
            "eventId": row.get("eventId"),
            "league": row.get("league"),
            "home": row.get("home"),
            "away": row.get("away"),
            "kickoff": row.get("kickoff"),
        }
        before_kickoff = captured < kickoff.astimezone(dt.timezone.utc)
        state = row.get("decisionReadinessState") or row.get("readinessState")
        prop = row.get("playerProps") or {}
        actionable = bool(prop.get("actionable") and before_kickoff)
        n_before = len(candidates)

        if actionable:
            for side in ("home", "away"):
                for p in ((prop.get("marketRows") or {}).get(side) or []):
                    name = str(p.get("name") or "").strip()
                    allowed = set(p.get("actionableMarkets") or [])
                    for market in sorted(allowed):
                        spec = PROP_FIELDS.get(market)
                        if not spec:
                            continue
                        field, family, label = spec
                        value = p.get(field)
                        if not isinstance(value, (int, float)) or not (0 <= float(value) <= 1):
                            continue
                        prob = float(value)
                        candidates.append({
                            "origin": "HBT_SHADOW",
                            "action": "TEST",
                            "fixture": fx,
                            "side": side,
                            "family": family,
                            "marketKey": market,
                            "selection": f"{name} {label}",
                            "player": name,
                            "modelProbability": prob,
                            "fairOdds": fair(prob),
                            "priceStatus": "UNPRICED_TEST",
                            "confirmedXIIdentityMatch": p.get("confirmedXIIdentityMatch") is True,
                            "validationArtifact": p.get("validatedMarketArtifactVersion"),
                            "validationScope": p.get("marketValidationScope"),
                        })

        # Independent validated event families may also be tested, but only when
        # the collector itself emitted explicit probabilities.
        if before_kickoff:
            for q in explicit_event_probabilities(row):
                q["fixture"] = fx
                candidates.append(q)

        fixture_states.append({
            **fx,
            "capturedBeforeKickoff": before_kickoff,
            "decisionReadinessState": state,
            "playerPropsActionable": actionable,
            "validatedEventFamilies": row.get("validatedEventFamilies") or [],
            "emittedTestCandidates": len(candidates) - n_before,
            "passReasons": (["kickoff_already_started"] if not before_kickoff else [])
                + ([] if actionable else ["confirmed_xi_player_prop_gate_not_ready"])
                + ([] if row.get("validatedEventFamilies") else ["no_validated_event_family_probability"]),
        })

    candidates.sort(key=lambda x: (-float(x.get("modelProbability") or 0), str((x.get("fixture") or {}).get("kickoff") or ""), str(x.get("selection") or "")))

    frozen_ok = bridge.get("status") in {"PARITY_OK", "READY"} and bridge.get("parityPassed") is True
    payload = {
        "schemaVersion": "HBT-SHADOW-TEST-1",
        "version": VERSION,
        "targetDate": args.date,
        "capturedAt": now_iso(),
        "state": "FROZEN_PROSPECTIVE_CAPTURE",
        "policy": {
            "origin": "HBT_SHADOW",
            "bookmakerOddsUsedAsPredictiveFeature": False,
            "predictiveIntelligenceMutated": False,
            "preXiCaptureOverwrittenByLaterXi": False,
            "postKickoffBackfillAllowed": False,
            "betRequiresCurrentPrice": True,
            "unpricedValidatedCandidateAction": "TEST",
            "unsupportedOrUnvalidatedMarketAction": "PASS",
            "frozenParityBlocksIndependentShadowMarkets": False,
            "frozenParityStillRequiredForFrozenControlClaims": True,
            "externalAnalysisMayNotBeReclassifiedAsHBT": True,
        },
        "frozenControl": {
            "available": frozen_ok,
            "bridgeStatus": bridge.get("status"),
            "oneXTwoAndDerivedGoalMarkets": "AVAILABLE" if frozen_ok else "PASS_CONTROL_PARITY_BLOCKED",
        },
        "supportedShadowFamilies": ["PLAYER_SHOTS", "PLAYER_SOT", "ANYTIME_GOAL", "validated explicit event-market probabilities"],
        "fixtureStates": fixture_states,
        "candidates": candidates,
        "coverage": {
            "fixtures": len(fixture_states),
            "testCandidates": len(candidates),
            "confirmedXiFixturesWithProps": sum(1 for x in fixture_states if x.get("playerPropsActionable")),
        },
    }
    name = args.output or f"hbt_shadow_test_{args.date}.json"
    write(OUT / name, payload)
    print(json.dumps(payload["coverage"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
