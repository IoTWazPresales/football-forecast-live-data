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
from datetime import datetime, timezone
import math
import hbt_execution_surface_v1 as base
import hbt_execution_surface_v1_2 as risk

VERSION = "HBT-EXECUTION-SURFACE-1.3.2-GOVERNED-RESEARCH"
_PRICE_INDEX: dict[tuple[str, str, str], float] = {}
_MARKET_AUDITS: dict[tuple[str, str], dict[str, Any]] = {}
_QUOTE_TIMES: dict[tuple[str, str], set[datetime]] = {}
_QUOTE_KICKOFFS: dict[tuple[str, str], set[datetime]] = {}


def _put(out: dict[tuple[str, str, str], float], home: Any, away: Any, market: str, value: Any) -> None:
    try:
        odds = float(value)
    except Exception:
        return
    if not math.isfinite(odds) or odds <= 1.0:
        return
    out[(base.norm(home), base.norm(away), market.upper())] = odds


def price_index(price_doc: dict[str, Any]) -> dict[tuple[str, str, str], float]:
    """Fail closed unless odds are fresh, attributable and for the target slate.

    Existing collector writes PRICE_SOURCE_UNCONFIGURED without a key.
    Ignore unaudited manual rows and provider-specific nested odds: the collector
    must normalize them with bookmaker + event ID before they can be acted on.
    """
    global _PRICE_INDEX
    _PRICE_INDEX = {}
    _QUOTE_TIMES.clear()
    _QUOTE_KICKOFFS.clear()
    if price_doc.get("status") != "PRICES_AVAILABLE":
        return _PRICE_INDEX
    try:
        collected = datetime.fromisoformat(str(price_doc["generatedAt"]).replace("Z", "+00:00"))
        if collected.tzinfo is None:
            return _PRICE_INDEX
        age_seconds = (datetime.now(timezone.utc) - collected.astimezone(timezone.utc)).total_seconds()
        if not 0 <= age_seconds <= 900:
            return _PRICE_INDEX
        slate = base.read(base.ROOT / "slate_scanner.json", {})
        if price_doc.get("targetDate") != slate.get("targetDate"):
            return _PRICE_INDEX
    except (KeyError, TypeError, ValueError):
        return _PRICE_INDEX

    bookmaker = str(price_doc.get("primaryBookmaker") or "").strip()
    if not bookmaker:
        return _PRICE_INDEX
    event_ids: dict[tuple[str, str, str], set[str]] = {}
    quote_values: dict[tuple[str, str, str], set[float]] = {}
    for r in price_doc.get("prices") or []:
        if not isinstance(r, dict) or not r.get("eventId") or r.get("bookmaker") != bookmaker:
            continue
        if not r.get("home") or not r.get("away"):
            continue
        row_at = base.parse_aware(r.get("collectedAt"))
        observed_at = base.parse_aware(r.get("retrievedAt"))
        kickoff = base.parse_aware(r.get("providerKickoff"))
        if (not row_at or not observed_at or not kickoff or r.get("period") != "REGULATION_90"
                or not 0 <= (datetime.now(timezone.utc) - row_at).total_seconds() <= 900
                or not 0 <= (datetime.now(timezone.utc) - observed_at).total_seconds() <= 900
                or kickoff.date().isoformat() != price_doc.get("targetDate") or row_at >= kickoff):
            continue
        key = (base.norm(r["home"]), base.norm(r["away"]), str(r.get("market") or "").upper())
        if key[2] not in {"HOME_WIN", "DRAW", "AWAY_WIN", "1X", "X2", "12"}:
            continue
        event_ids.setdefault(key, set()).add(str(r["eventId"]))
        _QUOTE_TIMES.setdefault(key[:2], set()).add(observed_at)
        _QUOTE_KICKOFFS.setdefault(key[:2], set()).add(kickoff)
        try:
            quote_values.setdefault(key, set()).add(float(r.get("odds")))
        except (TypeError, ValueError):
            continue
        _put(_PRICE_INDEX, r["home"], r["away"], key[2], r.get("odds"))
    # A fixture cannot safely combine markets from different provider event IDs.
    by_fixture: dict[tuple[str, str], set[str]] = {}
    for key, ids in event_ids.items():
        by_fixture.setdefault(key[:2], set()).update(ids)
    for key, ids in event_ids.items():
        if len(ids) != 1 or len(by_fixture[key[:2]]) != 1 or len(quote_values.get(key, set())) != 1:
            _PRICE_INDEX.pop(key, None)
    return _PRICE_INDEX

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
    """Record every 1X2/DC market, then prefer an eligible value candidate.

    Previously the highest raw EV won even when that market was quarantined,
    masking a lower-EV alternative that passed execution controls.
    """
    markets = row.get("derivedMarkets") or {}
    fx = row.get("fixture") or {}
    home, away = str(fx.get("home") or ""), str(fx.get("away") or "")
    candidates = []
    assessed = []
    for key in ("HOME_WIN", "DRAW", "AWAY_WIN", "1X", "X2", "12"):
        m = markets.get(key)
        if not isinstance(m, dict) or not isinstance(m.get("p"), (int, float)):
            continue
        p = float(m["p"])
        if not math.isfinite(p) or not 0 < p < 1:
            continue
        odds = _PRICE_INDEX.get((base.norm(home), base.norm(away), key))
        ev = p * odds - 1.0 if odds else None
        # Provisional assessment: actual kickoff identity/timing is checked by
        # the base execution layer before any funded recommendation.
        governance = classify_stake(row, p, odds, True)
        eligible = bool(odds and governance.get("stakeRand", 0) > 0)
        assessed.append({"market": key, "probability": p, "fairOdds": 1 / p,
                         "minimumOddsR1": governance.get("minimumOddsR1"),
                         "odds": odds, "rawEV": ev,
                         "provisionalValueEligible": eligible,
                         "decision": governance.get("executionClass"),
                         "fundingBlockers": governance.get("fundingBlockers", [])})
        candidates.append((key, m, ev, eligible))

    likely = max(
        (x for x in assessed if x["market"] in {"HOME_WIN", "DRAW", "AWAY_WIN"}),
        key=lambda x: x["probability"], default=None,
    )
    chain_role = max(
        (x for x in assessed if x["market"] in {"HOME_WIN", "AWAY_WIN", "1X", "X2", "12"}),
        key=lambda x: x["probability"], default=None,
    )
    _MARKET_AUDITS[(base.norm(home), base.norm(away))] = {
        "mostLikelyOutcome": likely, "highestProbabilityChainRoleWatch": chain_role,
        "allMarketAssessments": assessed,
        "bestProvisionalValue": max(
            (x for x in assessed if x["provisionalValueEligible"]),
            key=lambda x: x["rawEV"], default=None,
        ),
        "extremeValueDisagreementNeedsReview": any(
            x["rawEV"] is not None and x["rawEV"] >= .25 for x in assessed
        ),
    }
    priced = [x for x in candidates if x[2] is not None]
    if priced:
        viable = [x for x in priced if x[3]]
        winner = max(viable or priced, key=lambda x: (float(x[2]), float(x[1]["p"])))
        return winner[0], winner[1]

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

    # Promotion/readiness controls are independent of raw bookmaker value.
    # L0 fallback and PRE-XI overlays are research, not validated funded signals.
    blockers = []
    mode = str(row.get("predictionMode") or "")
    if mode != "FULL_MODEL" and "FUSION" not in mode:
        blockers.append("UNPROMOTED_L0_FALLBACK")
    readiness = (row.get("intelligenceOverlay") or {}).get("readinessState")
    if readiness != "CONFIRMED_XI_READY":
        blockers.append("CONFIRMED_XI_NOT_READY")
    if risk.base.coverage_stale(row):
        blockers.append("STALE_TEAM_STATE")
    if "MATCH_INTELLIGENCE_NOT_CAPTURED" in gaps:
        blockers.append("MATCH_INTELLIGENCE_NOT_CAPTURED")
    if blockers:
        result["stakeRand"] = 0
        result["executionClass"] = "R0_RESEARCH_READINESS_BLOCKED"
        result["nativeCleanForR2"] = False
    result["fundingBlockers"] = blockers
    result["robustnessReview"] = {
        "required": bool(blockers),
        "tier": tier or None,
        "matchIntelligenceCaptured": "MATCH_INTELLIGENCE_NOT_CAPTURED" not in gaps,
    }
    return result


_ORIGINAL_EXECUTION_IDENTITY_BLOCK = base.execution_identity_block


def governed_execution_identity_block(row: dict[str, Any], timing: dict[str, Any]) -> str | None:
    """A discovery timestamp is not independent kickoff confirmation.

    Provide hbt_live_data/hbt_independent_kickoffs_YYYY-MM-DD.json with
    targetDate and confirmations: [{home,away,kickoffUtc,independentSource,
    sourceUrl,verifiedAt}]. Same-source restatements are not independent.
    Missing/mismatched proof blocks staking but preserves research forecasts.
    """
    original = _ORIGINAL_EXECUTION_IDENTITY_BLOCK(row, timing)
    if original:
        timing["independentKickoffVerified"] = False
        return original
    fx = row.get("fixture") or {}
    date = str(fx.get("date") or "")
    # A later exact frozen export supersedes the older prospective slate for
    # live execution, without retrospectively editing its historical forecasts.
    current_export = base.read(base.ROOT / f"frozen_control_forecast_{date}.json", {})
    original_card = base.read(base.ROOT / f"hbt_prospective_card_{date}.json", {})
    current_at = base.parse_aware(current_export.get("sourceExportedAt"))
    old_at = base.parse_aware(original_card.get("capturedAt"))
    quote_times = _QUOTE_TIMES.get((base.norm(fx.get("home")), base.norm(fx.get("away"))), set())
    quote_kickoffs = _QUOTE_KICKOFFS.get((base.norm(fx.get("home")), base.norm(fx.get("away"))), set())
    if quote_kickoffs and quote_kickoffs != {base.parse_aware(timing.get("kickoffUtc"))}:
        return "QUOTE_KICKOFF_IDENTITY_DISAGREEMENT"
    if quote_times and (not old_at or any(t <= old_at for t in quote_times)):
        return "QUOTE_NOT_AFTER_IMMUTABLE_PREDICTION_FREEZE"
    if (current_export.get("targetDate") == date and current_at and old_at and current_at > old_at):
        timing["independentKickoffVerified"] = False
        return "PROSPECTIVE_CARD_BEHIND_NEWER_FROZEN_EXPORT"
    proof = base.read(base.ROOT / f"hbt_independent_kickoffs_{date}.json", {})
    if proof.get("targetDate") != date:
        timing["independentKickoffVerified"] = False
        return "INDEPENDENT_KICKOFF_CONFIRMATION_MISSING"
    matched = []
    for c in proof.get("confirmations") or []:
        if not isinstance(c, dict):
            continue
        if base.norm(c.get("home")) != base.norm(fx.get("home")) or base.norm(c.get("away")) != base.norm(fx.get("away")):
            continue
        if not c.get("sourceUrl") or not c.get("independentSource") or not base.parse_aware(c.get("verifiedAt")):
            continue
        if str(c.get("independentSource")).strip().lower() == str(timing.get("source") or "").strip().lower():
            continue
        matched.append(c)
    if len(matched) != 1:
        timing["independentKickoffVerified"] = False
        return "INDEPENDENT_KICKOFF_CONFIRMATION_MISSING_OR_AMBIGUOUS"
    official = base.parse_aware(matched[0].get("kickoffUtc"))
    discovered = base.parse_aware(timing.get("kickoffUtc"))
    if not official or official != discovered:
        timing["independentKickoffVerified"] = False
        return "KICKOFF_INDEPENDENT_SOURCE_DISAGREEMENT"
    if base.parse_aware(matched[0]["verifiedAt"]) >= discovered:
        timing["independentKickoffVerified"] = False
        return "KICKOFF_PROOF_CAPTURED_AFTER_START"
    timing["independentKickoffVerified"] = True
    timing["independentSource"] = matched[0]["independentSource"]
    timing["independentSourceUrl"] = matched[0]["sourceUrl"]
    return None


def main() -> int:
    _MARKET_AUDITS.clear()
    if not hasattr(base, "_ORIG_PLAIN_SELECTION"):
        base._ORIG_PLAIN_SELECTION = base.plain_selection
    base.price_index = price_index
    base.primary_market = primary_market
    base.plain_selection = plain_selection
    base.classify_stake = classify_stake
    base.execution_identity_block = governed_execution_identity_block
    base.VERSION = VERSION
    original_write = base.write

    def write_with_market_audit(path: Any, doc: Any) -> None:
        if isinstance(doc, dict) and str(path).endswith(".json") and "hbt_execution_surface_" in str(path):
            for surface_row in doc.get("rows") or []:
                fx = surface_row.get("fixture") or {}
                audit = _MARKET_AUDITS.get((base.norm(fx.get("home")), base.norm(fx.get("away"))))
                if audit:
                    audit["fixtureExecutionEligibleNow"] = surface_row.get("executionEligibleNow", False)
                    audit["fixtureExecutionBlockReason"] = surface_row.get("executionBlockReason")
                    if not surface_row.get("executionEligibleNow"):
                        for assessment in audit.get("allMarketAssessments") or []:
                            assessment["provisionalValueEligible"] = False
                            assessment["fundingBlockers"] = sorted(set(assessment.get("fundingBlockers", []) + [surface_row.get("executionBlockReason") or "FIXTURE_EXECUTION_BLOCKED"]))
                        audit["bestProvisionalValue"] = None
                    surface_row["fullMarketDecisionAudit"] = audit
            doc.setdefault("policy", {})["unpromotedOrUnconfirmedProposalsAreResearchOnly"] = True
            doc["policy"]["quotesRequireFreshSourceEventIdBookmakerAndTargetDate"] = True
            doc["policy"]["stakingRequiresIndependentKickoffConfirmation"] = True
            doc["policy"]["stakingRequiresLatestFrozenExportReconciliation"] = True
            # Product-of-marginals is a research approximation, not a funded
            # accumulator risk model. Preserve shadow chains, but never fund
            # automatically without a validated dependence/correlation layer.
            doc["policy"]["fundedChainsRequireValidatedDependenceModel"] = True
            for chain in doc.get("chains") or []:
                chain["independenceAssumptionUnvalidated"] = bool(chain.get("approximateIndependence"))
                if int(chain.get("stakeRand") or 0) > 0:
                    chain["previousExecutionClass"] = chain.get("executionClass")
                    chain["stakeRand"] = 0
                    chain["executionClass"] = "R0_CHAIN_DEPENDENCE_NOT_VALIDATED"
            doc.setdefault("summary", {})["fundedChains"] = 0
        original_write(path, doc)

    base.write = write_with_market_audit
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
