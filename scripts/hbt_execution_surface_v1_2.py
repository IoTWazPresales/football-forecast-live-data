#!/usr/bin/env python3
"""HBT execution surface v1.2 risk-adjusted value policy.

Wraps v1.1 without changing any football probability. Legacy exploratory
forensics showed materially weaker raw outcome performance in stale/C1 rows, so
these rows require a larger bookmaker edge before real-money execution. This is
a bankroll/execution control only, not a model coefficient change.
"""
from __future__ import annotations

from typing import Any
import hbt_execution_surface_v1 as base

VERSION = "HBT-EXECUTION-SURFACE-1.2-RISK-ADJUSTED"


def classify_stake(row: dict[str, Any], p: float, odds: float | None, execution_ok: bool) -> dict[str, Any]:
    fair = 1.0 / p if p > 0 else None
    c1 = row.get("coveragePack") == "C1"
    stale = base.coverage_stale(row)
    quality = float(row.get("quality") or 0)
    elevated_risk = c1 or stale

    # Native/current: +3% EV can fund R1, +7% can fund R2 if q>=0.90.
    # C1/stale: +7% EV is required just for R1; never R2.
    r1_ev = 0.07 if elevated_risk else 0.03
    r2_ev = 0.07
    min_r1 = (1.0 + r1_ev) / p if p > 0 else None
    min_r2 = (1.0 + r2_ev) / p if p > 0 else None
    ev = p * odds - 1.0 if odds else None
    native_clean = (not c1) and (not stale) and quality >= 0.90

    stake = 0
    execution_class = "R0_SHADOW"
    if execution_ok and ev is not None:
        if ev >= r2_ev and native_clean:
            stake, execution_class = 2, "R2_STRONG_VALUE_NATIVE_CURRENT"
        elif ev >= r1_ev:
            stake = 1
            execution_class = "R1_POSITIVE_VALUE_ELEVATED_RISK" if elevated_risk else "R1_POSITIVE_VALUE"
        else:
            execution_class = "R0_PRICE_BELOW_RISK_ADJUSTED_VALUE_GATE"
    elif not execution_ok:
        execution_class = "R0_EXECUTION_BLOCKED"
    else:
        execution_class = "R0_UNPRICED"

    return {
        "fairOdds": fair,
        "minimumOddsR1": min_r1,
        "minimumOddsR2": min_r2,
        "observedOdds": odds,
        "expectedValue": ev,
        "stakeRand": stake,
        "executionClass": execution_class,
        "nativeCleanForR2": native_clean,
        "riskAdjustedValueGate": {
            "c1": c1,
            "stale": stale,
            "elevatedRisk": elevated_risk,
            "minimumEVForR1": r1_ev,
            "minimumEVForR2": r2_ev if native_clean else None,
            "probabilityChangedByRiskPolicy": False,
        },
    }


def main() -> int:
    base.classify_stake = classify_stake
    base.VERSION = VERSION
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
