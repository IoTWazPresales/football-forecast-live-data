#!/usr/bin/env python3
"""HBT L5 historical value backtest — research only.

This script NEVER changes football probabilities. It joins an immutable frozen HBT
holdout export to historical bookmaker prices and evaluates betting value.

Primary protocol is declared before running the result:
- EPL 2018-19 frozen HBT L1 final holdout (2019-03-01 onward)
- Bet365 H/D/A historical pre-match prices
- at most one 1X2 bet per fixture
- choose the outcome with highest model EV
- primary minimum EV = +5%
- flat 1-unit stakes
- 0%, 2%, 10%, 15% are sensitivity checks only
"""
from __future__ import annotations

import csv
import io
import json
import math
import random
import re
import unicodedata
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "research" / "l5" / "epl_2018_19_frozen_l1_final.csv"
OUTDIR = ROOT / "research" / "l5" / "output"
OUTDIR.mkdir(parents=True, exist_ok=True)

ODDS_URL = "https://raw.githubusercontent.com/obameyan/QoreSDK-Premire-League/master/data/PremierLeague/2018-19.csv"
PRIMARY_THRESHOLD = 0.05
SENSITIVITY_THRESHOLDS = [0.00, 0.02, 0.05, 0.10, 0.15]
OUTCOMES = ["H", "D", "A"]
Y_TO_RESULT = {0: "H", 1: "D", 2: "A"}

ALIASES = {
    "manchester united": "man united",
    "man united": "man united",
    "manchester city": "man city",
    "man city": "man city",
    "newcastle united": "newcastle",
    "newcastle": "newcastle",
    "tottenham hotspur": "tottenham",
    "tottenham": "tottenham",
    "wolverhampton wanderers": "wolves",
    "wolverhampton": "wolves",
    "wolves": "wolves",
    "afc bournemouth": "bournemouth",
    "bournemouth": "bournemouth",
    "brighton hove albion": "brighton",
    "brighton": "brighton",
    "west ham united": "west ham",
    "west ham": "west ham",
    "huddersfield town": "huddersfield",
    "huddersfield": "huddersfield",
    "leicester city": "leicester",
    "leicester": "leicester",
    "cardiff city": "cardiff",
    "cardiff": "cardiff",
}


def team_key(value: str) -> str:
    s = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    s = s.lower().replace("&", " ")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    # Strip generic football suffix/prefix only after explicit normalisation.
    toks = [t for t in s.split() if t not in {"fc", "cf"}]
    s = " ".join(toks)
    return ALIASES.get(s, s)


def iso_from_fd(value: str) -> str:
    d, m, y = value.strip().split("/")
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "HBT-L5-research/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8-sig")


def load_baseline():
    with BASELINE.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        out.append({
            "date": r["date"],
            "home": r["home"],
            "away": r["away"],
            "homeKey": team_key(r["home"]),
            "awayKey": team_key(r["away"]),
            "y": int(r["y"]),
            "modelP": [float(r["pH"]), float(r["pD"]), float(r["pA"])],
        })
    return out


def load_odds():
    text = fetch_text(ODDS_URL)
    rows = list(csv.DictReader(io.StringIO(text)))
    out = {}
    duplicates = []
    for r in rows:
        if not r.get("Date") or not r.get("HomeTeam") or not r.get("AwayTeam"):
            continue
        try:
            odds = [float(r["B365H"]), float(r["B365D"]), float(r["B365A"])]
        except (KeyError, TypeError, ValueError):
            continue
        if not all(math.isfinite(x) and x > 1 for x in odds):
            continue
        key = (iso_from_fd(r["Date"]), team_key(r["HomeTeam"]), team_key(r["AwayTeam"]))
        item = {
            "date": key[0], "home": r["HomeTeam"], "away": r["AwayTeam"],
            "odds": odds, "result": r.get("FTR"),
            "marketAvg": [float(r[x]) if r.get(x) else None for x in ("BbAvH", "BbAvD", "BbAvA")],
            "marketMax": [float(r[x]) if r.get(x) else None for x in ("BbMxH", "BbMxD", "BbMxA")],
        }
        if key in out:
            duplicates.append(key)
        out[key] = item
    return out, duplicates


def max_drawdown(profits):
    equity = peak = 0.0
    max_dd = 0.0
    for p in profits:
        equity += p
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def evaluate(joined, threshold: float):
    bets = []
    for r in joined:
        evs = [r["modelP"][i] * r["odds"][i] - 1.0 for i in range(3)]
        idx = max(range(3), key=lambda i: evs[i])
        if evs[idx] + 1e-12 < threshold:
            continue
        won = r["y"] == idx
        profit = r["odds"][idx] - 1.0 if won else -1.0
        bets.append({
            "date": r["date"], "home": r["home"], "away": r["away"],
            "selection": OUTCOMES[idx], "modelP": r["modelP"][idx],
            "odds": r["odds"][idx], "modelEV": evs[idx], "won": won, "profit": profit,
            "marketVigFreeP": r["vigFree"][idx],
            "edgeVsVigFreeP": r["modelP"][idx] - r["vigFree"][idx],
        })
    n = len(bets)
    profit = sum(b["profit"] for b in bets)
    wins = sum(b["won"] for b in bets)
    return {
        "threshold": threshold,
        "bets": n,
        "wins": wins,
        "hitRate": wins / n if n else None,
        "profitUnits": profit,
        "roi": profit / n if n else None,
        "avgOdds": sum(b["odds"] for b in bets) / n if n else None,
        "avgModelEV": sum(b["modelEV"] for b in bets) / n if n else None,
        "avgEdgeVsVigFreeP": sum(b["edgeVsVigFreeP"] for b in bets) / n if n else None,
        "maxDrawdownUnits": max_drawdown([b["profit"] for b in bets]),
        "betsDetail": bets,
    }


def bootstrap_roi(bets, B=5000, seed=112):
    if not bets:
        return None
    by_date = defaultdict(list)
    for b in bets:
        by_date[b["date"]].append(b["profit"])
    blocks = list(by_date.values())
    rng = random.Random(seed)
    vals = []
    for _ in range(B):
        p = 0.0; n = 0
        for _ in range(len(blocks)):
            block = blocks[rng.randrange(len(blocks))]
            p += sum(block); n += len(block)
        vals.append(p / n if n else 0.0)
    vals.sort()
    return [vals[int(0.025 * B)], vals[min(B - 1, int(0.975 * B))]]


def model_pick_benchmark(joined):
    bets = []
    for r in joined:
        idx = max(range(3), key=lambda i: r["modelP"][i])
        won = r["y"] == idx
        profit = r["odds"][idx] - 1.0 if won else -1.0
        bets.append({"date": r["date"], "profit": profit, "won": won, "odds": r["odds"][idx]})
    n = len(bets); profit = sum(x["profit"] for x in bets); wins = sum(x["won"] for x in bets)
    return {"bets": n, "wins": wins, "hitRate": wins/n, "profitUnits": profit, "roi": profit/n, "maxDrawdownUnits": max_drawdown([x["profit"] for x in bets])}


def main():
    base = load_baseline()
    odds_map, duplicate_odds = load_odds()
    joined, missing, result_mismatches = [], [], []
    for r in base:
        key = (r["date"], r["homeKey"], r["awayKey"])
        o = odds_map.get(key)
        if not o:
            missing.append({"date": r["date"], "home": r["home"], "away": r["away"], "key": key})
            continue
        implied = [1/x for x in o["odds"]]
        overround = sum(implied)
        vig_free = [x/overround for x in implied]
        rr = {**r, "odds": o["odds"], "vigFree": vig_free, "overround": overround-1,
              "fdHome": o["home"], "fdAway": o["away"], "fdResult": o["result"]}
        if o["result"] and o["result"] != Y_TO_RESULT[r["y"]]:
            result_mismatches.append({"date": r["date"], "home": r["home"], "away": r["away"], "hbt": Y_TO_RESULT[r["y"]], "source": o["result"]})
        joined.append(rr)

    if missing:
        raise SystemExit(f"Join incomplete: {len(missing)} frozen rows missing odds; first={missing[:5]}")
    if result_mismatches:
        raise SystemExit(f"Outcome mismatch: {result_mismatches[:5]}")
    if len(joined) != len(base):
        raise SystemExit("Frozen-row count changed during join")

    sensitivity = {}
    for t in SENSITIVITY_THRESHOLDS:
        m = evaluate(joined, t)
        m["roiDateBlockBootstrap95"] = bootstrap_roi(m["betsDetail"])
        sensitivity[f"{int(round(t*100))}pct"] = m

    primary = sensitivity["5pct"]
    result = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "footballModelModified": False,
        "sourcePredictiveModel": "Frozen HBT-0.5P L1 parameters / HBT-1.1.2 benchmark",
        "cohort": {"league": "EPL", "start": min(r["date"] for r in joined), "end": max(r["date"] for r in joined), "frozenRows": len(base), "joinedRows": len(joined)},
        "oddsSource": {"name": "Football-Data.co.uk mirror", "mirror": ODDS_URL, "bookmaker": "Bet365", "columns": ["B365H", "B365D", "B365A"], "timingCaveat": "Historical pre-match/pre-closing benchmark; no observation timestamp. Does not prove transfer to a specific current bookmaker or lead time."},
        "protocol": {"oneBetMaxPerFixture": True, "flatStakeUnits": 1, "primaryMinModelEV": PRIMARY_THRESHOLD, "primaryDeclaredBeforeResult": True, "sensitivityThresholds": SENSITIVITY_THRESHOLDS, "accumulators": False, "oddsFeedBackIntoProbability": False},
        "joinAudit": {"missing": missing, "outcomeMismatches": result_mismatches, "duplicateOddsKeys": len(duplicate_odds)},
        "market": {"meanBet365Overround": sum(r["overround"] for r in joined)/len(joined)},
        "alwaysBetHighestModelProbability": model_pick_benchmark(joined),
        "primary5pct": primary,
        "sensitivity": sensitivity,
    }
    # Avoid duplicating the same verbose detail inside primary and sensitivity.
    result["primary5pct"] = {k:v for k,v in primary.items() if k != "betsDetail"}
    for m in result["sensitivity"].values():
        m.pop("betsDetail", None)

    out = OUTDIR / "hbt_l5_epl_2018_19_final_backtest.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "joinedRows": len(joined),
        "marketOverround": result["market"]["meanBet365Overround"],
        "alwaysPick": result["alwaysBetHighestModelProbability"],
        "primary5pct": result["primary5pct"],
        "sensitivity": {k:{kk:vv for kk,vv in v.items() if kk != "betsDetail"} for k,v in result["sensitivity"].items()},
        "output": str(out),
    }, indent=2))

if __name__ == "__main__":
    main()
