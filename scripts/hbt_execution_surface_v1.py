#!/usr/bin/env python3
"""HBT execution surface v1.

Downstream-only layer. It NEVER changes HBT football probabilities.
It freezes an exact R0 market, verifies kickoff using timezone-aware discovery,
optionally applies Betway prices after the forecast freeze, assigns R0/R1/R2,
and builds shadow chains from independently supported legs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT = Path("hbt_live_data")
VERSION = "HBT-EXECUTION-SURFACE-1"


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


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(d: dt.datetime | None) -> str | None:
    return d.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z") if d else None


def norm(value: Any) -> str:
    s = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(fc|cf|afc|ac|ssc|sc|rc|club|football|futbol|the)\b", " ", s)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def team_similarity(a: Any, b: Any) -> float:
    x, y = norm(a), norm(b)
    if not x or not y:
        return 0.0
    if x == y:
        return 1.0
    sx, sy = set(x.split()), set(y.split())
    if sx <= sy or sy <= sx:
        return 0.95
    jac = len(sx & sy) / max(1, len(sx | sy))
    return max(jac, SequenceMatcher(None, x, y).ratio())


def parse_aware(value: Any) -> dt.datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    # Naive clocks are forbidden for execution eligibility.
    if not (s.endswith("Z") or re.search(r"[+-]\d\d:\d\d$", s)):
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d.astimezone(dt.timezone.utc) if d.tzinfo else None
    except Exception:
        return None


def source_priority(row: dict[str, Any]) -> int:
    src = " ".join(str(x or "") for x in (row.get("fixtureSources") or [row.get("source")])).upper()
    if "ESPN:" in src:
        return 100
    if "ESPN_ALL" in src:
        return 90
    if "THESPORTSDB" in src:
        return 60
    if "OPENFOOTBALL" in src:
        return 30
    return 10


def verified_kickoff(scanner: dict[str, Any], target_date: str, home: str, away: str) -> dict[str, Any]:
    best: tuple[float, int, dict[str, Any], dt.datetime] | None = None
    for row in scanner.get("fixtures") or []:
        ko = parse_aware(row.get("kickoff"))
        if not ko or ko.date().isoformat() != target_date:
            continue
        hs = team_similarity(home, row.get("home"))
        aws = team_similarity(away, row.get("away"))
        if min(hs, aws) < 0.72:
            continue
        candidate = ((hs + aws) / 2.0, source_priority(row), row, ko)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        return {"verified": False, "kickoffUtc": None, "reason": "NO_TIMEZONE_AWARE_DISCOVERY_MATCH"}
    score, _, row, ko = best
    return {
        "verified": True,
        "kickoffUtc": iso(ko),
        "source": row.get("source"),
        "fixtureSources": row.get("fixtureSources") or [],
        "sourceFixtureId": row.get("sourceFixtureId"),
        "identityScore": round(score, 6),
        "reason": "TIMEZONE_AWARE_DISCOVERY_MATCH",
    }


def namespace_block(row: dict[str, Any]) -> str | None:
    fx = row.get("fixture") or {}
    r = row.get("resolution") or {}
    text = " ".join(str(x or "") for x in [fx.get("competition"), fx.get("competitionSlug"), r.get("competition"), fx.get("home"), fx.get("away")]).lower()
    if any(x in text for x in ("women", "women's", "womens", "vrouwen", "femen", "feminin")):
        return "WOMENS_NAMESPACE"
    if re.search(r"\bu(?:17|18|19|20|21|23)\b", text) or any(x in text for x in ("reserve", "reserves", "youth")):
        return "YOUTH_RESERVE_NAMESPACE"
    return None


def primary_market(row: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    markets = row.get("derivedMarkets") or {}
    eligible: list[tuple[str, dict[str, Any]]] = []
    for key in ("1X", "X2", "12"):
        m = markets.get(key)
        if isinstance(m, dict) and isinstance(m.get("p"), (int, float)):
            eligible.append((key, m))
    if not eligible:
        return None
    return max(eligible, key=lambda x: float(x[1]["p"]))


def secondary_market(row: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    probs = row.get("probs") or {}
    markets = row.get("derivedMarkets") or {}
    h, a = float(probs.get("H") or 0), float(probs.get("A") or 0)
    key = "HOME_DNB" if h >= a else "AWAY_DNB"
    m = markets.get(key)
    return (key, m) if isinstance(m, dict) else None


def plain_selection(home: str, away: str, market: str) -> str:
    if market == "1X":
        return f"{home} OR Draw — Double Chance (1X)"
    if market == "X2":
        return f"{away} OR Draw — Double Chance (X2)"
    if market == "12":
        return f"{home} OR {away} — Either team wins, draw loses (12)"
    if market == "HOME_DNB":
        return f"{home} — Draw No Bet (draw = refund)"
    if market == "AWAY_DNB":
        return f"{away} — Draw No Bet (draw = refund)"
    return market


def coverage_stale(row: dict[str, Any]) -> bool:
    return "stale" in str(row.get("coverage") or "").lower()


def price_index(price_doc: dict[str, Any]) -> dict[tuple[str, str, str], float]:
    out: dict[tuple[str, str, str], float] = {}
    rows = price_doc.get("prices") or []
    for r in rows:
        try:
            odds = float(r.get("odds"))
        except Exception:
            continue
        if odds <= 1:
            continue
        out[(norm(r.get("home")), norm(r.get("away")), str(r.get("market") or "").upper())] = odds
    return out


def classify_stake(row: dict[str, Any], p: float, odds: float | None, execution_ok: bool) -> dict[str, Any]:
    fair = 1.0 / p if p > 0 else None
    min_r1 = 1.03 / p if p > 0 else None
    min_r2 = 1.07 / p if p > 0 else None
    ev = p * odds - 1.0 if odds else None
    c1 = row.get("coveragePack") == "C1"
    quality = float(row.get("quality") or 0)
    native_clean = (not c1) and (not coverage_stale(row)) and quality >= 0.90
    stake = 0
    execution_class = "R0_SHADOW"
    if execution_ok and ev is not None:
        if ev >= 0.07 and native_clean:
            stake, execution_class = 2, "R2_STRONG_VALUE"
        elif ev >= 0.03:
            stake, execution_class = 1, "R1_POSITIVE_VALUE"
        else:
            execution_class = "R0_PRICE_BELOW_VALUE_GATE"
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
    }


def product(values: list[float]) -> float:
    x = 1.0
    for v in values:
        x *= v
    return x


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--prices", default=None, help="Optional post-freeze manual Betway price JSON")
    args = ap.parse_args()
    target = args.date
    card = read(ROOT / f"hbt_prospective_card_{target}.json", {})
    scanner = read(ROOT / "slate_scanner.json", {})
    if not card.get("candidates"):
        raise SystemExit(f"no prospective card for {target}")
    if scanner.get("targetDate") != target:
        raise SystemExit(f"slate_scanner targetDate {scanner.get('targetDate')} does not match {target}")
    prices = price_index(read(Path(args.prices), {}) if args.prices else {})
    captured = now_utc()
    rows: list[dict[str, Any]] = []

    for row in card.get("candidates") or []:
        fx = row.get("fixture") or {}
        home, away = str(fx.get("home") or ""), str(fx.get("away") or "")
        timing = verified_kickoff(scanner, target, home, away)
        ko = parse_aware(timing.get("kickoffUtc")) if timing.get("verified") else None
        block = namespace_block(row)
        execution_ok = bool(ko and ko > captured and not block)
        pm = primary_market(row)
        sm = secondary_market(row)
        if not pm:
            continue
        market, m = pm
        p = float(m.get("p") or 0)
        odds = prices.get((norm(home), norm(away), market))
        stake = classify_stake(row, p, odds, execution_ok)
        rows.append({
            "fixture": {"home": home, "away": away, "date": target, "league": fx.get("league")},
            "origin": row.get("origin"),
            "predictionFrozenAt": card.get("capturedAt"),
            "executionSurfaceGeneratedAt": iso(captured),
            "kickoffVerification": timing,
            "executionEligibleNow": execution_ok,
            "executionBlockReason": block or ("KICKOFF_ALREADY_STARTED" if ko and ko <= captured else None) or (None if timing.get("verified") else timing.get("reason")),
            "signal": {
                "tier": row.get("tier"), "rawTier": row.get("rawTier"), "quality": row.get("quality"),
                "coverage": row.get("coverage"), "coveragePack": row.get("coveragePack"),
                "market": market, "selection": plain_selection(home, away, market),
                "probability": p, "family": m.get("family"),
            },
            "secondaryR0": ({
                "market": sm[0], "selection": plain_selection(home, away, sm[0]),
                "fairOdds": sm[1].get("fairOdds"), "conditionalP": sm[1].get("conditionalP"),
                "winP": sm[1].get("winP"), "pushP": sm[1].get("pushP"), "lossP": sm[1].get("lossP"),
            } if sm else None),
            "value": stake,
            "r0Tracking": {"stakeRand": 0, "marketFrozen": market, "selectionFrozen": plain_selection(home, away, market)},
        })

    rows.sort(key=lambda r: (-float((r.get("signal") or {}).get("probability") or 0), str((r.get("kickoffVerification") or {}).get("kickoffUtc") or "")))
    chain_pool = [r for r in rows if r.get("executionEligibleNow")]
    chains = []
    for n, name in ((3, "R0_CORE_3"), (5, "R0_CORE_5")):
        legs = chain_pool[:n]
        if len(legs) == n:
            joint = product([float(x["signal"]["probability"]) for x in legs])
            chains.append({
                "name": name, "stakeRand": 0, "executionClass": "R0_SHADOW_CHAIN",
                "approximateIndependence": True, "jointModelProbabilityApprox": joint,
                "fairOddsApprox": (1.0 / joint if joint > 0 else None),
                "legs": [{"fixture": x["fixture"], "market": x["signal"]["market"], "selection": x["signal"]["selection"], "p": x["signal"]["probability"]} for x in legs],
            })
    funded = [r for r in rows if int((r.get("value") or {}).get("stakeRand") or 0) > 0]
    funded_chain_legs = [r for r in funded if float((r.get("value") or {}).get("expectedValue") or -1) >= 0.03]
    if len(funded_chain_legs) >= 2:
        legs = funded_chain_legs[:3]
        joint = product([float(x["signal"]["probability"]) for x in legs])
        chains.append({
            "name": "FUNDED_VALUE_CHAIN", "stakeRand": 1, "executionClass": "R1_CHAIN_ALL_LEGS_PASS_VALUE_GATE",
            "approximateIndependence": True, "jointModelProbabilityApprox": joint,
            "legs": [{"fixture": x["fixture"], "market": x["signal"]["market"], "selection": x["signal"]["selection"], "p": x["signal"]["probability"], "odds": x["value"]["observedOdds"], "ev": x["value"]["expectedValue"]} for x in legs],
        })

    out = {
        "schemaVersion": "HBT-EXECUTION-SURFACE-1", "version": VERSION,
        "targetDate": target, "generatedAt": iso(captured),
        "policy": {
            "footballProbabilitiesImmutable": True,
            "bookmakerPriceObservedOnlyAfterPredictionFreeze": True,
            "r0Default": True,
            "r1MinimumModelEV": 0.03,
            "r2MinimumModelEV": 0.07,
            "r2RequiresNativeCurrentQualityAtLeast": 0.90,
            "c1MaximumFundedStakeRand": 1,
            "executionRequiresTimezoneAwareVerifiedKickoff": True,
            "startedFixtureAction": "R0_BLOCKED_IN_PLAY",
            "chainLegMustIndependentlyPassValueGateForFunding": True,
            "sameMatchCorrelatedLegsAllowed": False,
        },
        "sourceProspectiveCard": f"hbt_prospective_card_{target}.json",
        "priceSource": args.prices,
        "summary": {
            "surfaces": len(rows), "executionEligibleNow": sum(1 for r in rows if r.get("executionEligibleNow")),
            "fundedSingles": len(funded), "fundedStakeRand": sum(int(r["value"]["stakeRand"]) for r in funded),
            "r0Singles": len(rows) - len(funded), "chains": len(chains),
        },
        "rows": rows, "chains": chains,
    }
    write(ROOT / f"hbt_execution_surface_{target}.json", out)
    print(json.dumps(out["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
