#!/usr/bin/env python3
"""HBT execution surface v1.3 — choose value, not merely safest probability.

This is a downstream execution-layer change only. Football probabilities remain
immutable. If bookmaker prices are available, every supported derived market is
evaluated independently and the highest-EV market is surfaced. If prices are
absent, the legacy safest R0 market remains the display fallback.

Supported priced families:
- 1X2: HOME_WIN / DRAW / AWAY_WIN
- Double chance: 1X / X2 / 12

DNB remains surfaced as secondary R0 until bookmaker DNB quote normalization is
fully validated. Execution robustness extends v1.2 without changing football probabilities:
- native/current R1 >= +3% EV
- native/current + quality >= .90 + tier A/B R2 >= +7% EV
- C1, stale, or tier Avoid R1 >= +7% EV; never R2
- MATCH_INTELLIGENCE_NOT_CAPTURED caps at R1
- extreme raw EV >= +25% is quarantined for model/identity review rather than funded
"""
from __future__ import annotations

from typing import Any
import hbt_execution_surface_v1 as base
import hbt_execution_surface_v1_2 as risk

VERSION = "HBT-EXECUTION-SURFACE-1.3.1-ROBUST-VALUE"
_PRICE_INDEX: dict[tuple[str, str, str], float] = {}


def _put(out: dict[tuple[str, str, str], float], home: Any, away: Any, market: str, value: Any) -> None:
    try:
        odds = float(value)
    except Exception:
        return
    if odds <= 1.0:
        return
    out[(base.norm(home), base.norm(away), market.upper())] = odds


def price_index(price_doc: dict[str, Any]) -> dict[tuple[str, str, str], float]:
    """Accept both legacy flat price rows and HBT market_prices nested provider format."""
    global _PRICE_INDEX
    out: dict[tuple[str, str, str], float] = {}

    # Legacy/explicit flat rows.
    for r in price_doc.get("prices") or []:
        _put(out, r.get("home"), r.get("away"), str(r.get("market") or ""), r.get("odds"))

    # Nested Odds-API.io sidecar.
    for item in (price_doc.get("fixtures") or {}).values():
        fx = item.get("slateFixture") or {}
        home, away = fx.get("home"), fx.get("away")
        for m in item.get("markets") or []:
            name = str(m.get("name") or "").strip().lower()
            for q in m.get("odds") or []:
                if not isinstance(q, dict):
                    continue
                if name in {"moneyline", "ml", "match winner", "1x2"}:
                    _put(out, home, away, "HOME_WIN", q.get("home"))
                    _put(out, home, away, "DRAW", q.get("draw"))
                    _put(out, home, away, "AWAY_WIN", q.get("away"))
                elif "double chance" in name or name in {"dc", "double_chance"}:
                    # Provider schemas vary; support common key names fail-closed.
                    for key, aliases in {
                        "1X": ("1x", "homeDraw", "home_draw", "homeOrDraw"),
                        "X2": ("x2", "awayDraw", "drawAway", "away_draw", "awayOrDraw"),
                        "12": ("12", "homeAway", "home_away", "eitherTeam"),
                    }.items():
                        for alias in aliases:
                            if alias in q:
                                _put(out, home, away, key, q.get(alias))
                                break

    _PRICE_INDEX = out
    return out


def plain_selection(home: str, away: str, market: str) -> str:
    if market == "HOME_WIN":
        return f"{home} — Match Winner"
    if market == "DRAW":
        return f"{home} vs {away} — Draw"
    if market == "AWAY_WIN":
        return f"{away} — Match Winner"
    return base._ORIG_PLAIN_SELECTION(home, away, market) if hasattr(base, "_ORIG_PLAIN_SELECTION") else _legacy_plain(home, away, market)


def _legacy_plain(home: str, away: str, market: str) -> str:
    if market == "1X": return f"{home} OR Draw — Double Chance (1X)"
    if market == "X2": return f"{away} OR Draw — Double Chance (X2)"
    if market == "12": return f"{home} OR {away} — Either team wins, draw loses (12)"
    if market == "HOME_DNB": return f"{home} — Draw No Bet (draw = refund)"
    if market == "AWAY_DNB": return f"{away} — Draw No Bet (draw = refund)"
    return market


def primary_market(row: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    markets = row.get("derivedMarkets") or {}
    fx = row.get("fixture") or {}
    home, away = str(fx.get("home") or ""), str(fx.get("away") or "")

    candidates: list[tuple[str, dict[str, Any], float | None]] = []
    for key in ("HOME_WIN", "DRAW", "AWAY_WIN", "1X", "X2", "12"):
        m = markets.get(key)
        if not isinstance(m, dict) or not isinstance(m.get("p"), (int, float)):
            continue
        odds = _PRICE_INDEX.get((base.norm(home), base.norm(away), key))
        ev = float(m["p"]) * odds - 1.0 if odds else None
        candidates.append((key, m, ev))

    priced = [x for x in candidates if x[2] is not None]
    if priced:
        # Highest model EV wins. Probability is only a tiebreaker.
        best = max(priced, key=lambda x: (float(x[2]), float(x[1]["p"])))
        return best[0], best[1]

    # No price: preserve legacy conservative R0 display behaviour.
    dc = [(k, markets[k]) for k in ("1X", "X2", "12")
          if isinstance(markets.get(k), dict) and isinstance(markets[k].get("p"), (int, float))]
    return max(dc, key=lambda x: float(x[1]["p"])) if dc else None


def classify_stake(row: dict[str, Any], p: float, odds: float | None, execution_ok: bool) -> dict[str, Any]:
    """Apply value gates plus robustness controls; never mutate football probability."""
    result = risk.classify_stake(row, p, odds, execution_ok)
    ev = result.get("expectedValue")
    tier = str(row.get("tier") or "")
    gaps = set(((row.get("intelligenceOverlay") or {}).get("intelligenceGaps") or []))
    coverage_risk = result.get("riskAdjustedValueGate") or {}

    # An extreme apparent edge is more likely to be a stale/identity/model-domain
    # disagreement until independently checked. Preserve it for research, but fail
    # closed for funding.
    if execution_ok and isinstance(ev, (int, float)) and ev >= 0.25:
        result["stakeRand"] = 0
        result["executionClass"] = "R0_EXTREME_MARKET_DISAGREEMENT_REVIEW"
        result["robustnessReview"] = {
            "required": True,
            "reason": "raw model EV >= 25%; verify identity, freshness, domain and current match intelligence before execution",
        }
        return result

    # 'Avoid' is an HBT risk signal. It can only become R1 at the stronger +7%
    # edge gate; it can never jump to R2 merely because price is generous.
    if execution_ok and isinstance(ev, (int, float)) and tier == "Avoid":
        result["nativeCleanForR2"] = False
        result["riskAdjustedValueGate"]["elevatedRisk"] = True
        result["riskAdjustedValueGate"]["minimumEVForR1"] = 0.07
        result["riskAdjustedValueGate"]["minimumEVForR2"] = None
        if ev >= 0.07:
            result["stakeRand"] = 1
            result["executionClass"] = "R1_POSITIVE_VALUE_TIER_AVOID_REVIEWED"
        else:
            result["stakeRand"] = 0
            result["executionClass"] = "R0_PRICE_BELOW_AVOID_VALUE_GATE"

    # R2 is reserved for stronger HBT confidence, not quality score alone.
    if result.get("stakeRand") == 2 and tier not in {"A", "B"}:
        result["stakeRand"] = 1
        result["executionClass"] = "R1_VALUE_R2_BLOCKED_BY_TIER"
        result["nativeCleanForR2"] = False

    # If the match-intelligence snapshot was not captured, keep positive-value
    # candidates visible but cap them at R1 until the context collector catches up.
    if result.get("stakeRand") == 2 and "MATCH_INTELLIGENCE_NOT_CAPTURED" in gaps:
        result["stakeRand"] = 1
        result["executionClass"] = "R1_VALUE_R2_BLOCKED_BY_INTELLIGENCE_GAP"
        result["nativeCleanForR2"] = False

    result["robustnessReview"] = {
        "required": False,
        "tier": tier or None,
        "matchIntelligenceCaptured": "MATCH_INTELLIGENCE_NOT_CAPTURED" not in gaps,
    }
    return result


def main() -> int:
    if not hasattr(base, "_ORIG_PLAIN_SELECTION"):
        base._ORIG_PLAIN_SELECTION = base.plain_selection
    base.price_index = price_index
    base.primary_market = primary_market
    base.plain_selection = plain_selection
    base.classify_stake = classify_stake
    base.VERSION = VERSION
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
