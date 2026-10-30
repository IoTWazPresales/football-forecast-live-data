#!/usr/bin/env python3
"""Rank existing immutable HBT Fusion P1/P2 market research, never funded bets.

Inputs are first-add captures, not mutable latest predictions. Fusion H/D/A
derived double-chance markets are distinct from the L4 goal-model markets.
No bookmaker price or outcome data is read.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "hbt_live_data"
LEAGUES = {"en.1", "es.1", "de.1", "it.1", "fr.1"}
GOAL_KEYS = {
    "over15": "Over 1.5 match goals",
    "under15": "Under 1.5 match goals",
    "over25": "Over 2.5 match goals",
    "under25": "Under 2.5 match goals",
    "over35": "Over 3.5 match goals",
    "under35": "Under 3.5 match goals",
    "bttsYes": "Both teams to score - Yes",
    "bttsNo": "Both teams to score - No",
    "homeOver05": "Home team over 0.5 goals",
    "awayOver05": "Away team over 0.5 goals",
    "homeOver15": "Home team over 1.5 goals",
    "awayOver15": "Away team over 1.5 goals",
}
def utc_time(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is unverified")
    return parsed.astimezone(dt.timezone.utc)

def prob(x) -> bool:
    return type(x) in (float, int) and math.isfinite(x) and 0 <= x <= 1

def distribution(x) -> bool:
    return (isinstance(x, list) and len(x) == 3
            and all(prob(v) for v in x) and abs(sum(x) - 1) < 1e-9)

def extract_capture(path: Path, date: str) -> list[dict]:
    raw = path.read_bytes()
    doc = json.loads(raw)
    if doc.get("schemaVersion") != "HBT-FUSION-FIRST-ADD-1":
        raise ValueError("not an HBT immutable Fusion first-add")
    if doc.get("targetDate") != date or doc.get("policy", {}).get("immutableFirstAdd") is not True:
        raise ValueError("date/immutability mismatch")
    if doc.get("policy", {}).get("bettingEligible") is not False:
        raise ValueError("funded capture not permitted in research-only watch")
    fx = doc.get("forecast") or {}
    fixture = fx.get("fixture") or {}
    if fx.get("status") != "RESEARCH_ONLY" or fx.get("executionEligible") is not False:
        raise ValueError("only rejected-for-funding research forecasts can enter")
    if fx.get("predictionMode") not in {"PRE-XI FUSION", "CONFIRMED-XI FUSION"}:
        raise ValueError("not a Fusion forecast")
    if fixture.get("date") != date or fixture.get("league") not in LEAGUES:
        raise ValueError("date/native league mismatch")
    if not all(str(fixture.get(k) or "").strip() for k in ("home", "away", "time")):
        raise ValueError("missing fixture identity or kickoff")
    kickoff = utc_time(f"{date}T{fixture['time']}:00Z")
    captured = utc_time(doc.get("capturedAt"))
    if captured >= kickoff or not fx.get("diagnostics", {}).get("preKickoff"):
        raise ValueError("capture was not recorded before kickoff")
    if not distribution(fx.get("probs")):
        raise ValueError("invalid Fusion H/D/A probabilities")
    markets = fx.get("scoreMarkets") or {}
    if not distribution(markets.get("hda")):
        raise ValueError("invalid goal-distribution H/D/A probabilities")
    if not all(prob(markets[k]) for k in GOAL_KEYS if k in markets):
        raise ValueError("invalid goal-market probability")
    h, d, a = fx["probs"]
    captured_stage = "P2" if fx["predictionMode"] == "CONFIRMED-XI FUSION" else "P1"
    if not path.name.endswith(f"_{captured_stage}.json"):
        raise ValueError("first-add file and model stage disagree")
    immutable_sha = hashlib.sha256(raw).hexdigest()
    base = {
        "fixture": fixture,
        "fixtureKey": f"{date}|{fixture['league']}|{fixture['home']}|{fixture['away']}",
        "stage": captured_stage,
        "capturedAt": doc["capturedAt"],
        "captureSha256": immutable_sha,
        "marketPriceAvailable": False,
        "bettingEligible": False,
        "suggestedStakeRand": 0,
    }
    out = []
    for key, label, value in (
        ("1X", "Home win or draw", h+d),
        ("X2", "Away win or draw", d+a),
        ("12", "Either team wins", h+a),
    ):
        out.append({**base, "market": key, "selection": label,
                    "modelProbability": value, "probabilitySource": "FUSION_HDA"})
    for key, label in GOAL_KEYS.items():
        if key in markets:
            out.append({**base, "market": key, "selection": label,
                        "modelProbability": markets[key],
                        "probabilitySource": "L4_POISSON_GOAL_DISTRIBUTION"})
    return out

def build(date: str, root: Path = ROOT) -> dict:
    date = dt.date.fromisoformat(date).isoformat()
    directory = root / "captures" / "fusion"
    files = sorted(directory.glob(f"hbt_fusion_firstadd_{date}_*_P[12].json"))
    groups = {}
    for path in files:
        rows = extract_capture(path, date)
        identity = rows[0]["fixtureKey"]
        stage = rows[0]["stage"]
        k = (identity, stage)
        if k in groups:
            raise ValueError("duplicate immutable first-add capture for fixture/stage")
        groups[k] = rows
    # Prefer the actual P2 if one exists, but P1 and P2 are not independent matches.
    selected = {}
    for (identity, stage), rows in groups.items():
        if identity not in selected or stage == "P2":
            selected[identity] = rows
    flat = [row for rows in selected.values() for row in rows]
    flat.sort(key=lambda r: (-r["modelProbability"], r["fixtureKey"], r["market"]))
    best = sorted((max(rows, key=lambda r: r["modelProbability"]) for rows in selected.values()),
                  key=lambda r: -r["modelProbability"])
    return {
        "schemaVersion": "HBT-FIRST-ADD-MARKET-WATCH-1",
        "targetDate": date,
        "status": "RESEARCH_ONLY_NOT_BETTING_READY",
        "policy": {
            "immovableOriginalFirstAdd": True,
            "P1AndP2CountAsOneFixture": True,
            "deriveDoubleChanceFromFusionNotL4": True,
            "goalMarketsFromOriginalL4Only": True,
            "noModelRetraining": True,
            "noOddsInPrediction": True,
            "noIndependentMarketCalibrationClaim": True,
            "noBettingEligibility": True,
            "noAccumulatorEligibility": True,
            "notAnExecutableQuote": True,
            "noStakeRecommendation": True,
        },
        "summary": {
            "immutableFirstAddFiles": len(files),
            "uniqueFixturesWithFusionOutput": len(selected),
            "marketsShown": len(flat),
            "highestProbabilityDoesNotMeanHighestEV": True,
        },
        "bestPerFixture": best,
        "allRankedMarkets": flat,
    }

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    doc = build(args.date, args.root)
    destination = args.output or args.root / f"hbt_firstadd_market_watch_{args.date}.json"
    destination.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(doc["summary"], indent=2))

if __name__ == "__main__":
    main()
