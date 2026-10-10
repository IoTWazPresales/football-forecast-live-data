#!/usr/bin/env python3
"""Read-only HBT betting desk: complete coverage and honest execution readiness.

Consumes existing forecasts, intelligence and normalized quotes. Never fits a
model, invents goal probabilities, rewrites a prospective card or places bets.
Event tails use the SAME Poisson calculation as the existing event trainer;
held-out lines and extrapolated lines are explicitly separated.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import itertools
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import hbt_execution_surface_v1 as base
import hbt_execution_surface_v1_3 as governed
from hbt_build_prospective_card_v2 import market_map
from hbt_train_event_models_v4 import ptail

ROOT = Path(__file__).resolve().parents[1] / "hbt_live_data"
VERSION = "HBT-BETTING-DESK-1-RESEARCH"
MAIN_KEYS = ("HOME_WIN", "DRAW", "AWAY_WIN", "1X", "X2", "12", "HOME_DNB", "AWAY_DNB")
SCORE_KEYS = {
    "over15": ("TOTAL_GOALS", "TOTAL_GOALS_OVER_1.5", "Over 1.5 goals"),
    "under15": ("TOTAL_GOALS", "TOTAL_GOALS_UNDER_1.5", "Under 1.5 goals"),
    "over25": ("TOTAL_GOALS", "TOTAL_GOALS_OVER_2.5", "Over 2.5 goals"),
    "under25": ("TOTAL_GOALS", "TOTAL_GOALS_UNDER_2.5", "Under 2.5 goals"),
    "over35": ("TOTAL_GOALS", "TOTAL_GOALS_OVER_3.5", "Over 3.5 goals"),
    "under35": ("TOTAL_GOALS", "TOTAL_GOALS_UNDER_3.5", "Under 3.5 goals"),
    "bttsYes": ("BTTS", "BTTS_YES", "Both teams to score — Yes"),
    "bttsNo": ("BTTS", "BTTS_NO", "Both teams to score — No"),
    "homeOver05": ("TEAM_GOALS", "HOME_GOALS_OVER_0.5", "Home over 0.5 goals"),
    "awayOver05": ("TEAM_GOALS", "AWAY_GOALS_OVER_0.5", "Away over 0.5 goals"),
    "homeOver15": ("TEAM_GOALS", "HOME_GOALS_OVER_1.5", "Home over 1.5 goals"),
    "awayOver15": ("TEAM_GOALS", "AWAY_GOALS_OVER_1.5", "Away over 1.5 goals"),
}
EVENTS = {"corners": "CORNERS", "yellowCards": "YELLOW_CARDS",
          "shots": "TOTAL_SHOTS", "shotsOnTarget": "TOTAL_SOT"}


def probability(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and 0 <= value <= 1)


def fixture_key(row):
    f = row.get("fixture") or row
    date = str(f.get("date") or f.get("kickoff") or "")[:10]
    return (date, base.norm(f.get("home")), base.norm(f.get("away")))


def make_market(key, family, selection, win, push=0.0, **metadata):
    loss = max(0.0, 1.0 - win - push)
    return {"market": key, "family": family, "selection": selection,
            "winProbability": win, "pushProbability": push, "lossProbability": loss,
            "profitProbability": win, "nonLossProbability": win + push,
            "fairOdds": (1.0 - push) / win if win > 0 else None, **metadata}


def forecast_markets(pred):
    probs = pred.get("probs")
    if not (isinstance(probs, list) and len(probs) == 3
            and all(probability(p) for p in probs) and abs(sum(probs) - 1) < 1e-9):
        return []
    h, d, a = probs
    f = pred.get("fixture") or {}
    output = []
    for key, m in market_map(h, d, a).items():
        if key not in MAIN_KEYS:
            continue
        push = d if key.endswith("DNB") else 0.0
        win = (h if key == "HOME_DNB" else a) if key.endswith("DNB") else m["p"]
        output.append(make_market(key, m["family"], governed.plain_selection(f.get("home"), f.get("away"), key),
                                  win, push, source="EXACT_FROZEN_FORECAST", mainMarket=True))
    # Do not infer BTTS/totals from a 1X2 vector. Empty/null is unavailable.
    for field, (family, key, label) in SCORE_KEYS.items():
        p = (pred.get("scoreMarkets") or {}).get(field)
        if probability(p):
            output.append(make_market(key, family, label, float(p), source="EXACT_SCORE_MODEL", mainMarket=True))
    return output


def event_markets(intel, params):
    output = []
    for name, prefix in EVENTS.items():
        model = (intel.get("eventMarkets") or {}).get(name) or {}
        artifact = (params.get("models") or {}).get(name) or {}
        lam = model.get("totalLambda")
        delta = (artifact.get("promotionEvidence") or {}).get("holdoutNLLDelta")
        histories = model.get("history") or {}
        if (model.get("validatedMarketModel") is not True
                or model.get("calibrationVersion") != params.get("version")
                or not isinstance(delta, (int, float)) or not math.isfinite(delta) or delta >= 0
                or not isinstance(lam, (int, float)) or not math.isfinite(lam) or not 0 < lam < 200
                or min(int(histories.get(k) or 0) for k in ("homeForN", "homeAgainstN", "awayForN", "awayAgainstN")) < 3):
            continue
        # Only expose lines actually present in the held-out model artifact.
        for line_text, evidence in ((artifact.get("holdout") or {}).get("lines") or {}).items():
            line = float(line_text)
            if line < 0 or line % 1 != .5 or int(evidence.get("n") or 0) <= 0:
                continue
            over = ptail(lam, line)
            for side, p in (("OVER", over), ("UNDER", 1 - over)):
                output.append(make_market(f"{prefix}_{side}_{line:g}", prefix,
                    f"{side.title()} {line:g} {prefix.lower().replace('_', ' ')}", p,
                    source="EXISTING_VALIDATED_EVENT_POISSON", mainMarket=False,
                    modelArtifact=params.get("version"), lineHoldoutN=evidence.get("n"),
                    lineBinaryLogloss=evidence.get("binaryLogloss"),
                    validationScope="family count model; this line has held-out scores, not a guaranteed win rate"))
    return output


def quote_index(doc, target, now):
    """Accept auditable flat quotes; reject conflicts, stale rows and event mixing."""
    quotes, rejected = {}, Counter()
    stamp = base.parse_aware(doc.get("generatedAt"))
    if doc.get("status") != "PRICES_AVAILABLE" or doc.get("targetDate") != target:
        return {}, {"sourceStatus": doc.get("status") or "PRICE_SOURCE_MISSING", "accepted": 0}
    if not stamp or not 0 <= (now - stamp).total_seconds() <= 900 or not doc.get("primaryBookmaker"):
        return {}, {"sourceStatus": "PRICE_DOCUMENT_STALE_OR_UNATTRIBUTABLE", "accepted": 0}
    ids, seen = {}, {}
    for q in doc.get("prices") or []:
        if not isinstance(q, dict):
            rejected["INVALID_ROW"] += 1
            continue
        key = (base.norm(q.get("home")), base.norm(q.get("away")), str(q.get("market") or ""))
        when, ko = base.parse_aware(q.get("collectedAt")), base.parse_aware(q.get("providerKickoff"))
        retrieved = base.parse_aware(q.get("retrievedAt"))
        odds = q.get("odds")
        if (not all(key) or not q.get("eventId") or q.get("bookmaker") != doc["primaryBookmaker"]
                or q.get("period") != "REGULATION_90" or not when or not ko or not retrieved
                or not 0 <= (now - retrieved).total_seconds() <= 900
                or ko.date().isoformat() != target or not 0 <= (now - when).total_seconds() <= 900
                or when >= ko or not isinstance(odds, (int, float)) or isinstance(odds, bool)
                or not math.isfinite(odds) or odds <= 1):
            rejected["QUOTE_PROVENANCE_TIME_OR_PERIOD_INVALID"] += 1
            continue
        ids.setdefault(key[:2], set()).add(str(q["eventId"]))
        seen.setdefault(key, set()).add(float(odds))
        quotes[key] = q
    for key in list(quotes):
        if len(ids[key[:2]]) != 1 or len(seen[key]) != 1:
            quotes.pop(key)
            rejected["AMBIGUOUS_EVENT_OR_CONFLICTING_QUOTE"] += 1
    return quotes, {"sourceStatus": "PRICES_AVAILABLE", "accepted": len(quotes), "rejected": dict(rejected)}


def assess_market(market, pred, timing, blockers, quotes, frozen_at):
    m = dict(market)
    f = pred.get("fixture") or {}
    q = quotes.get((base.norm(f.get("home")), base.norm(f.get("away")), m["market"]))
    blocked = list(blockers)
    if q:
        observed_at, ko = base.parse_aware(q.get("retrievedAt")), base.parse_aware(q.get("providerKickoff"))
        if not frozen_at or not observed_at or observed_at <= frozen_at:
            blocked.append("QUOTE_NOT_AFTER_PREDICTION_FREEZE")
            q = None
        elif ko != base.parse_aware(timing.get("kickoffUtc")):
            blocked.append("QUOTE_KICKOFF_MISMATCH")
            q = None
    odds = q["odds"] if q else None
    ev = m["winProbability"] * (odds - 1) - m["lossProbability"] if odds else None
    if odds is None:
        blocked.append("CURRENT_BOOKMAKER_QUOTE_MISSING")
    if ev is not None and ev >= .25:
        blocked.append("EXTREME_MARKET_DISAGREEMENT_REVIEW")
    min_ev = .07 if pred.get("tier") == "Avoid" or pred.get("coveragePack") == "C1" or base.coverage_stale(pred) else .03
    if ev is not None and ev < min_ev:
        blocked.append("PRICE_BELOW_VALUE_GATE")
    if not m.get("mainMarket"):
        blocked.append("EVENT_EXECUTION_VALIDATION_PENDING")
    # No retrospective quote-aware forecast: immutable capture must be verified.
    m.update({"fixture": f, "observedOdds": odds, "bookmaker": q.get("bookmaker") if q else None,
        "quotedAt": q.get("collectedAt") if q else None, "expectedProfitPerRand": ev,
        "minimumEVGate": min_ev,
        "minimumOddsForValueGate": (1 + min_ev - m["pushProbability"]) / m["winProbability"] if m["winProbability"] > 0 else None,
        "valuePositive": ev is not None and ev > 0,
        "fundingBlockers": sorted(set(blocked)), "stakeReady": not blocked,
        "decision": "VALUE_CANDIDATE" if not blocked else "WATCH" if blocked == ["CURRENT_BOOKMAKER_QUOTE_MISSING"] else "BLOCKED",
        "guaranteedProfit": False})
    return m


def chain_candidates(fixtures, limit=10):
    """Bounded 2–4 leg search, one fixture per leg, separated objectives.

    Marginal products are labelled approximations. Frechet bounds need no
    independence assumption. Push markets need a refund settlement tree and are
    excluded. Nothing here authorizes funded chains.
    """
    pool = []
    for f in fixtures:
        if f.get("started") or f.get("identityBlocked") or not f.get("markets"):
            continue
        ms = [m for m in f["markets"] if m.get("mainMarket") and m["pushProbability"] == 0]
        if ms:
            pool.append(max(ms, key=lambda m: m["winProbability"]))
    pool = sorted(pool, key=lambda m: -m["winProbability"])[:16]
    output = []
    for n in (2, 3, 4):
        for legs in itertools.combinations(pool, n):
            ps = [m["winProbability"] for m in legs]
            approximate = math.prod(ps)
            lower, upper = max(0.0, sum(ps) - (n - 1)), min(ps)
            prices = [m["observedOdds"] for m in legs]
            combined = math.prod(prices) if all(prices) else None
            output.append({"legCount": n, "objective": "HIGH_PROBABILITY_WATCH",
                "jointProbabilityIndependenceApprox": approximate,
                "jointProbabilityBounds": {"lower": lower, "upper": upper},
                "lossProbabilityIndependenceApprox": 1 - approximate,
                "combinedOdds": combined, "returnPerRandIfAllWin": combined,
                "expectedProfitPerRandIndependenceApprox": approximate * combined - 1 if combined else None,
                "expectedProfitPerRandBounds": {"lower": lower * combined - 1, "upper": upper * combined - 1} if combined else None,
                "dependenceValidated": False, "stakeReady": False,
                "fundingBlockers": sorted(set(["CHAIN_DEPENDENCE_NOT_VALIDATED"] + [b for m in legs for b in m["fundingBlockers"]])),
                "legs": [{k: m[k] for k in ("fixture", "market", "selection", "winProbability", "observedOdds")} for m in legs]})
    output.sort(key=lambda c: (-c["jointProbabilityBounds"]["lower"], -c["jointProbabilityIndependenceApprox"]))
    best = output[:limit]
    # Price-positive chains are a separate ranking; never hide safe, short-price
    # legs or call a negative-EV leg a profitable one merely by adding more legs.
    value_pool = []
    for f in fixtures:
        eligible = [m for m in f.get("markets", []) if m["stakeReady"] and m["pushProbability"] == 0]
        if eligible:
            value_pool.append(max(eligible, key=lambda m: (m["winProbability"], m["expectedProfitPerRand"])))
    value_pool.sort(key=lambda m: -m["winProbability"])
    for n in (2, 3, 4):
        for legs in itertools.combinations(value_pool[:12], n):
            p, odds = math.prod(m["winProbability"] for m in legs), math.prod(m["observedOdds"] for m in legs)
            best.append({"legCount": n, "objective": "POSITIVE_VALUE_WATCH",
                "jointProbabilityIndependenceApprox": p, "combinedOdds": odds,
                "expectedProfitPerRandIndependenceApprox": p * odds - 1,
                "jointProbabilityBounds": {"lower": max(0, sum(m["winProbability"] for m in legs) - n + 1), "upper": min(m["winProbability"] for m in legs)},
                "dependenceValidated": False, "stakeReady": False,
                "fundingBlockers": ["CHAIN_DEPENDENCE_NOT_VALIDATED"],
                "legs": [{k: m[k] for k in ("fixture", "market", "selection", "winProbability", "observedOdds")} for m in legs]})
    values = sorted([c for c in best if c["objective"] == "POSITIVE_VALUE_WATCH"], key=lambda c: (-c["jointProbabilityIndependenceApprox"], -c["expectedProfitPerRandIndependenceApprox"]))[:limit]
    return [c for c in best if c["objective"] == "HIGH_PROBABILITY_WATCH"] + values


def build(target, data_root=ROOT, now=None, price_path=None):
    now = now or datetime.now(timezone.utc)
    dated_scanner = data_root / f"slate_scanner_{target}.json"
    dated_prices = data_root / f"market_prices_{target}.json"
    paths = {"forecast": data_root / f"frozen_control_forecast_{target}.json",
        "card": base.capture_path(data_root, target), "scanner": dated_scanner if dated_scanner.exists() else data_root / "slate_scanner.json",
        "intel": data_root / "hbt_1_4_match_intelligence.json", "events": data_root / "event_model_params.json",
        "registry": data_root / "hbt_1_4_feature_registry.json", "learning": data_root / "forensic/hbt_learning_assessment_v1.json",
        "prices": price_path or (dated_prices if dated_prices.exists() else data_root / "market_prices.json"),
        "kickoffProof": data_root / f"hbt_independent_kickoffs_{target}.json",
        "capturePointer": data_root / f"hbt_current_capture_{target}.json"}
    docs = {k: base.read(p, {}) for k, p in paths.items()}
    forecast, card, scanner, intel = (docs[k] for k in ("forecast", "card", "scanner", "intel"))
    global_blocks = []
    if forecast.get("targetDate") != target:
        global_blocks.append("FORECAST_TARGET_MISSING_OR_MISMATCH")
    err = (forecast.get("bridge") or {}).get("goldenMaxAbsError")
    if not isinstance(err, (int, float)) or not math.isfinite(err) or err > 1e-9:
        global_blocks.append("FROZEN_PARITY_UNPROVEN")
    if scanner.get("targetDate") != target:
        global_blocks.append("SCANNER_TARGET_MISMATCH")
    elif not (scanner.get("rankingGate") or {}).get("discoveryComplete"):
        global_blocks.append("SCANNER_COVERAGE_INCOMPLETE")
    frozen_at, capture_at = base.parse_aware(forecast.get("sourceExportedAt")), base.parse_aware(card.get("capturedAt"))
    if frozen_at and frozen_at > now:
        global_blocks.append("FORECAST_SOURCE_CLOCK_IN_FUTURE")
    if capture_at and capture_at > now:
        global_blocks.append("PROSPECTIVE_CAPTURE_CLOCK_IN_FUTURE")
    if card.get("targetDate") != target or not capture_at:
        global_blocks.append("IMMUTABLE_PROSPECTIVE_CAPTURE_MISSING")
    elif frozen_at and frozen_at > capture_at:
        global_blocks.append("PROSPECTIVE_CARD_BEHIND_NEWER_FROZEN_EXPORT")
    if card.get('sourceForecastSha256') and (not paths['forecast'].exists() or card['sourceForecastSha256'] != hashlib.sha256(paths['forecast'].read_bytes()).hexdigest()):
        global_blocks.append('CAPTURE_FORECAST_HASH_MISMATCH')
    quotes, quote_audit = quote_index(docs["prices"], target, now)
    intel_index = {fixture_key(r): r for r in (intel.get("fixtures") or {}).values()}
    card_index = {fixture_key(r): r for r in card.get("candidates") or []}
    fixtures, keys = [], set()
    for pred in forecast.get("predictions") or []:
        f = pred.get("fixture") or {}
        k = fixture_key(pred)
        if k[0] != target:
            continue
        keys.add(k)
        timing = base.verified_kickoff(scanner, target, f.get("home"), f.get("away"))
        ko = base.parse_aware(timing.get("kickoffUtc"))
        ident = base.execution_identity_block(pred, timing)
        blocks = list(global_blocks)
        if ident: blocks.append(ident)
        if not ko or ko <= now: blocks.append("KICKOFF_STARTED_OR_UNKNOWN")
        if frozen_at is None or (ko and frozen_at >= ko): blocks.append("FORECAST_CAPTURE_NOT_PREMATCH")
        proof_block = governed.independent_kickoff_block(f, timing, docs['kickoffProof'], now)
        if proof_block:
            blocks.append(proof_block)
        context = intel_index.get(k) or {}
        readiness = context.get("decisionReadinessState") or context.get("readinessState")
        if not context: blocks.append("MATCH_INTELLIGENCE_NOT_CAPTURED")
        if (context.get("officialXI") or {}).get("confirmed") is not True:
            blocks.append("CONFIRMED_XI_NOT_READY")
        mode = str(pred.get("predictionMode") or "")
        if "FUSION" not in mode and mode != "FULL_MODEL": blocks.append("UNPROMOTED_L0_FALLBACK")
        if base.coverage_stale(pred): blocks.append("STALE_TEAM_STATE")
        captured = card_index.get(k)
        capture_overlay = (captured or {}).get("intelligenceOverlay") or {}
        if capture_overlay.get("readinessState") != "CONFIRMED_XI_READY":
            blocks.append("FROZEN_FORECAST_NOT_CONFIRMED_XI_READY")
        vector = captured.get("probs") if captured else None
        if not vector or any(abs(vector.get(x, -1) - pred["probs"][i]) > 1e-9 for i, x in enumerate(("H", "D", "A"))):
            blocks.append("LATEST_FORECAST_NOT_IN_IMMUTABLE_CAPTURE")
        raw = forecast_markets(pred)
        markets = [assess_market(m, pred, timing, blocks, quotes, frozen_at) for m in raw]
        context_at = base.parse_aware(intel.get("generatedAt"))
        event_blocks = blocks + ([] if context_at and ko and context_at < ko and context_at <= now else ["EVENT_INTELLIGENCE_NOT_PREMATCH"])
        markets += [assess_market(m, pred, timing, event_blocks, quotes, context_at) for m in event_markets(context, docs["events"])]
        most_likely = max([m for m in markets if m["market"] in ("HOME_WIN", "DRAW", "AWAY_WIN")], key=lambda m: m["winProbability"], default=None)
        ready = [m for m in markets if m["stakeReady"]]
        strongest = max(ready, key=lambda m: (m["profitProbability"], m["expectedProfitPerRand"]), default=None)
        best_value = max(ready, key=lambda m: m["expectedProfitPerRand"], default=None)
        families = {m["family"] for m in markets}
        fixtures.append({"fixture": f, "predictionMode": mode, "tier": pred.get("tier"),
            "quality": pred.get("quality"), "coverage": pred.get("coverage"), "readinessState": readiness,
            "kickoffVerification": timing, "started": bool(ko and ko <= now), "identityBlocked": bool(ident),
            "fundingBlockers": sorted(set(blocks)), "markets": markets,
            "mostLikelyOutcome": most_likely, "strongestWinCandidate": strongest, "bestStandaloneValue": best_value,
            "missingMainFamilies": [fam for fam in ("BTTS", "TOTAL_GOALS", "TEAM_GOALS") if fam not in families],
            "bookmakerAvailabilityConfirmed": any(m["observedOdds"] for m in markets)})
    # Every discovered fixture is accounted for, including unsupported/unscored.
    unscored = []
    if scanner.get("targetDate") == target:
        for r in scanner.get("fixtures") or []:
            if fixture_key(r) not in keys:
                unscored.append({k: r.get(k) for k in ("home", "away", "kickoff", "competition", "leagueHint", "hbtSupportLevel", "classificationReason")})
    disappeared = [r.get("fixture") for r in card.get("candidates") or [] if fixture_key(r) not in keys]
    families = docs["registry"].get("families") or {}
    gaps = [{"family": k, "status": v.get("status"), "role": v.get("role")} for k, v in families.items()
            if any(x in str(v.get("status")) for x in ("build", "planned", "partial", "research", "retained-after"))]
    flat = [m for f in fixtures for m in f["markets"]]
    actionable = [m for m in flat if m["stakeReady"]]
    return {"schemaVersion": "HBT-BETTING-DESK-1", "version": VERSION, "targetDate": target,
        "generatedAt": base.iso(now), "readiness": "VALUE_CANDIDATES_REQUIRE_REVIEW" if actionable else "NO_EXECUTABLE_BETS",
        "policy": {"bookmakerOddsAreDecisionLayerOnly": True, "frozenModelMutated": False,
            "historicalCapturesRewritten": False, "guaranteedProfit": False, "automaticBetsPlaced": False,
            "goalProbabilitiesInferredFrom1X2": False, "chainFundingAutomatic": False,
            "priority": "highest profit probability among independently eligible positive-value markets; separate highest EV view"},
        "sourceHashes": {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in paths.items() if p.exists()},
        "sourceFiles": {k: str(p.relative_to(data_root)) if p.is_relative_to(data_root) else str(p.resolve()) for k, p in paths.items() if p.exists()},
        "quoteAudit": quote_audit, "globalBlockers": global_blocks,
        "summary": {"scoredFixtures": len(fixtures), "marketsModelled": len(flat), "readySingles": len(actionable),
            "futureScoredFixtures": sum(not f['started'] and bool(f['kickoffVerification'].get('kickoffUtc')) for f in fixtures),
            "independentlyVerifiedKickoffs": sum(f['kickoffVerification'].get('independentKickoffVerified') is True for f in fixtures),
            "currentCaptureFixtures": len(card.get('candidates') or []),
            "bookmakerPricedMarkets": sum(m["observedOdds"] is not None for m in flat),
            "unscoredDiscoveredFixtures": len(unscored), "previouslyScoredMissingNow": len(disappeared),
            "missingBTTSFixtures": sum("BTTS" in f["missingMainFamilies"] for f in fixtures),
            "modelModes": dict(Counter(f["predictionMode"] for f in fixtures)),
            "blockerCounts": dict(Counter(b for m in flat for b in m["fundingBlockers"]))},
        "intelligence": {"researchOrIncompleteFamilies": gaps, "learningEvidence": docs["learning"].get("evidenceQuality"),
            "promotionRule": docs["learning"].get("nextPromotionRule")},
        "fixtures": fixtures, "unscoredFixtures": unscored, "previouslyScoredMissingNow": disappeared,
        "chains": chain_candidates(fixtures)}


def render(doc):
    e = lambda x: html.escape(str(x if x is not None else "—"))
    rows = []
    for f in doc["fixtures"]:
        fx = f["fixture"]
        ko = base.parse_aware(f["kickoffVerification"].get("kickoffUtc"))
        when = ko.astimezone(ZoneInfo("Africa/Johannesburg")).strftime("%H:%M SAST") if ko else "Kickoff unverified"
        body = []
        for m in f["markets"]:
            fair_text = f'{m["fairOdds"]:.3f}' if m["fairOdds"] is not None else '—'
            body.append(f'<tr data-main="{int(m["mainMarket"])}"><td>{e(m["selection"])}</td><td>{m["winProbability"]:.1%}</td><td>{m["pushProbability"]:.1%}</td><td>{m["lossProbability"]:.1%}</td><td>{fair_text}</td><td>{e(m["observedOdds"])}</td><td>{e(m["decision"])}</td><td class="small">{e(", ".join(m["fundingBlockers"]))}</td></tr>')
        missing = ', '.join(f["missingMainFamilies"]) or 'None'
        rows.append(f'<details class="fixture" open><summary>{e(fx["home"])} vs {e(fx["away"])} · {e(when)} · {e(f["predictionMode"])} · {"STARTED" if f["started"] else "WATCH"}</summary><p>Missing main probabilities: {e(missing)}. Bookmaker markets confirmed: {e(f["bookmakerAvailabilityConfirmed"])}</p><div class="scroll"><table><thead><tr><th>Selection</th><th>Profit chance</th><th>Refund</th><th>Loss</th><th>Fair odds</th><th>Current odds</th><th>Decision</th><th>Blockers</th></tr></thead><tbody>{"".join(body)}</tbody></table></div></details>')
    chains = ''.join(f'<div class="chain"><b>{c["legCount"]} legs — research only</b><p>{e(" + ".join(x["selection"] for x in c["legs"]))}</p><p>Win probability range without assuming independence: {c["jointProbabilityBounds"]["lower"]:.1%}–{c["jointProbabilityBounds"]["upper"]:.1%}. Independence approximation: {c["jointProbabilityIndependenceApprox"]:.1%}. Odds: {e(c["combinedOdds"])}</p></div>' for c in doc["chains"])
    unscored = ''.join(f'<tr><td>{e(x["home"])} vs {e(x["away"])}</td><td>{e(x["competition"])}</td><td>{e(x["hbtSupportLevel"])}</td><td>{e(x["classificationReason"])}</td></tr>' for x in doc["unscoredFixtures"])
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HBT Betting Desk {e(doc['targetDate'])}</title>
<style>body{{background:#10151e;color:#e8eef5;font:15px system-ui;margin:0}}main{{max-width:1500px;margin:auto;padding:28px}}h1{{font-size:30px}}.banner,.fixture,.chain{{background:#1b2432;border:1px solid #3a475a;border-radius:10px;padding:18px;margin:15px 0}}.banner{{border-left:5px solid #e0ae4a}}summary{{cursor:pointer;font-weight:700}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #354257;vertical-align:top}}th{{white-space:nowrap}}.small{{font-size:11px;max-width:400px}}.scroll{{overflow:auto}}input,button{{padding:10px;border-radius:6px}}input{{min-width:300px}}.hide-events [data-main="0"]{{display:none}}a{{color:#9ac9ff}}</style>
<main><h1>HBT Betting Desk · {e(doc['targetDate'])}</h1><p>Generated {e(doc['generatedAt'])}. This snapshot expires as kickoffs and prices change.</p>
<div class="banner"><b>{e(doc['readiness'])}</b><p>{doc['summary']['scoredFixtures']} scored fixtures · {doc['summary']['marketsModelled']} modelled markets · {doc['summary']['bookmakerPricedMarkets']} current priced markets · {doc['summary']['readySingles']} ready singles.</p><p>Model probabilities describe uncertainty. Every bet can lose. A high win probability does not make an overpriced bet profitable.</p><p>Global blockers: {e(', '.join(doc['globalBlockers']) or 'None')}. Price feed: {e(doc['quoteAudit']['sourceStatus'])}.</p></div>
<input id="search" type="search" aria-label="Filter fixtures" placeholder="Search team or league"><button id="events">Show event markets</button>
<section id="fixtures" class="hide-events">{''.join(rows)}</section><h2>Chains to inspect</h2><p>One fixture per leg. These are bounded research candidates, not funded recommendations or an exhaustive optimum. Short-price legs remain visible; chains do not remove their price disadvantage.</p>{chains or '<p>No current chain candidates.</p>'}
<h2>Coverage gaps</h2><p>{doc['summary']['unscoredDiscoveredFixtures']} discovered fixtures have no governed 1X2 forecast. {doc['summary']['previouslyScoredMissingNow']} previously scored fixtures are absent from the latest export. BTTS probabilities missing for {doc['summary']['missingBTTSFixtures']} scored fixtures.</p><details><summary>All unscored fixtures</summary><div class="scroll"><table><tbody>{unscored}</tbody></table></div></details>
<h2>Learning and intelligence</h2><p>{e(doc['intelligence']['learningEvidence'])}</p><p>{e(doc['intelligence']['promotionRule'])}</p><p>{e(', '.join(x['family']+': '+str(x['status']) for x in doc['intelligence']['researchOrIncompleteFamilies']))}</p>
</main><script>const fs=document.getElementById('fixtures');document.getElementById('events').onclick=function(){{fs.classList.toggle('hide-events');this.textContent=fs.classList.contains('hide-events')?'Show event markets':'Hide event markets'}};document.getElementById('search').oninput=function(){{const q=this.value.toLowerCase();document.querySelectorAll('.fixture').forEach(x=>x.hidden=!x.querySelector('summary').textContent.toLowerCase().includes(q))}};</script></html>'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--prices", type=Path)
    ap.add_argument("--as-of", help="Timezone-aware evaluation clock for reproducible/externally verified audits")
    ap.add_argument("--clock-source", default="SYSTEM_UTC")
    args = ap.parse_args()
    datetime.fromisoformat(args.date)
    paths = list(ROOT.glob("hbt_prospective_card_*.json")) + [ROOT / "hbt_1_4_match_intelligence.json"]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.exists()}
    as_of = base.parse_aware(args.as_of) if args.as_of else None
    if args.as_of and not as_of:
        raise SystemExit('--as-of must include an explicit timezone')
    doc = build(args.date, now=as_of, price_path=args.prices)
    doc["evaluationClock"] = {"source": args.clock_source, "explicitAsOf": args.as_of}
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in before.items()), "input mutated"
    base.write(ROOT / f"hbt_betting_desk_{args.date}.json", doc)
    (ROOT / f"hbt_betting_desk_{args.date}.html").write_text(render(doc), encoding="utf-8")
    print(json.dumps({"readiness": doc["readiness"], **doc["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
