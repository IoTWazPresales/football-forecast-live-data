#!/usr/bin/env python3
"""HBT-1.4 international intelligence v3: causal recent-performance interaction.

Research-only downstream challenger. The frozen HBT-1.1.2 runtime and domestic
probabilities are never touched. This script tests whether pre-match recent
international performance adds information conditional on the v1 structural
state, then applies the selected interaction only to the international R0
prospective card.

Missing inputs produce a neutral *contribution* and remain explicitly marked
missing; they are never represented as observed zero values.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import hbt_international_challenger_v1 as v1

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "hbt_live_data"
INTL = DATA / "international"
VERSION = "HBT-1.4-INTERNATIONAL-INTELLIGENCE-3-RECENT-INTERACTION"


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


def softmax(z: list[float]) -> list[float]:
    m = max(z); e = [math.exp(x-m) for x in z]; s = sum(e)
    return [x/s for x in e]


def profile(rows: deque, rating: float, last: dt.date | None, day: dt.date) -> dict[str, Any]:
    xs = list(rows)
    if xs:
        gf = sum(x["gf"] for x in xs) / len(xs)
        ga = sum(x["ga"] for x in xs) / len(xs)
        pts = sum(3 if x["result"] == 1 else 1 if x["result"] == .5 else 0 for x in xs) / (3 * len(xs))
        opp = sum(x["oppRating"] for x in xs) / len(xs)
    else:
        gf = ga = pts = opp = None
    return {
        "elo": rating, "recentN": len(xs), "goalsForMean": gf, "goalsAgainstMean": ga,
        "pointsShare": pts, "recentOpponentEloMean": opp,
        "daysSinceMatch": (day-last).days if last else None,
    }


def historical_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ratings: dict[str, float] = defaultdict(lambda: 1500.0)
    recent: dict[str, deque] = defaultdict(lambda: deque(maxlen=8))
    last: dict[str, dt.date] = {}
    out = []
    for r in history:
        hk, ak = v1.norm(r["home"]), v1.norm(r["away"])
        if not hk or not ak or hk == ak:
            continue
        rh, ra = ratings[hk], ratings[ak]
        hp, ap = profile(recent[hk], rh, last.get(hk), r["date"]), profile(recent[ak], ra, last.get(ak), r["date"])
        home_adv = not bool(r.get("neutral"))
        diff = rh-ra+(65.0 if home_adv else 0.0)
        out.append({
            "date": r["date"], "result": v1.result_code(r["hg"], r["ag"]), "tournament": r.get("tournament"),
            "eloDiff": diff, "homeAdvantage": home_adv, "homeProfile": hp, "awayProfile": ap,
        })
        expected = 1.0/(1.0+10**(-diff/400.0))
        actual = 1.0 if r["hg"] > r["ag"] else 0.0 if r["hg"] < r["ag"] else 0.5
        margin = abs(int(r["hg"])-int(r["ag"]))
        mult = math.sqrt((margin+1.0)/2.0) if margin > 1 else 1.0
        delta = v1.tournament_weight(str(r.get("tournament") or ""))*mult*(actual-expected)
        ratings[hk] = rh+delta; ratings[ak] = ra-delta
        recent[hk].append({"date":r["date"],"gf":r["hg"],"ga":r["ag"],"oppRating":ra,"result":actual})
        recent[ak].append({"date":r["date"],"gf":r["ag"],"ga":r["hg"],"oppRating":rh,"result":1.0-actual})
        last[hk] = r["date"]; last[ak] = r["date"]
    return out


def residual_features(hp: dict[str, Any], ap: dict[str, Any]) -> dict[str, Any]:
    available = {}
    def both(k: str) -> tuple[float, float] | None:
        a, b = hp.get(k), ap.get(k)
        if isinstance(a,(int,float)) and isinstance(b,(int,float)):
            available[k] = True; return float(a), float(b)
        available[k] = False; return None
    pts = both("pointsShare")
    gf = both("goalsForMean"); ga = both("goalsAgainstMean")
    opp = both("recentOpponentEloMean")
    rest = both("daysSinceMatch")
    return {
        "pointsShareDiff": (pts[0]-pts[1]) if pts else None,
        "recentGoalDiffDiff": ((gf[0]-ga[0])-(gf[1]-ga[1])) if gf and ga else None,
        "recentOpponentStrengthDiff": ((opp[0]-opp[1])/400.0) if opp else None,
        "restDiffScaled": max(-1.0,min(1.0,(rest[0]-rest[1])/30.0)) if rest else None,
        "availability": available,
    }


def adjusted_probs(row: dict[str, Any], base_params: tuple[float,float,float,float], w: tuple[float,float,float,float]) -> tuple[list[float],dict[str,Any]]:
    slope, home_logit, draw_intercept, draw_mismatch = base_params
    d = float(row["eloDiff"])/400.0; home = 1.0 if row.get("homeAdvantage") else 0.0
    f = residual_features(row["homeProfile"],row["awayProfile"])
    values = [f["pointsShareDiff"],f["recentGoalDiffDiff"],f["recentOpponentStrengthDiff"],f["restDiffScaled"]]
    contribs = [0.0 if x is None else float(x)*coef for x,coef in zip(values,w)]
    adj = sum(contribs)
    p = softmax([slope*d+home_logit*home+adj, draw_intercept-draw_mismatch*abs(d), -slope*d-adj])
    return p,{**f,"weights":{"pointsShare":w[0],"goalDifference":w[1],"opponentStrength":w[2],"rest":w[3]},"contributions":contribs,"totalLogitAdjustment":adj}


def metrics(rows: list[dict[str,Any]], base_params: tuple[float,float,float,float], w: tuple[float,float,float,float]) -> dict[str,Any]:
    n=correct=0; ll=br=0.0; bins=defaultdict(lambda:[0,0.0,0.0])
    for r in rows:
        p,_=adjusted_probs(r,base_params,w); y={"H":0,"D":1,"A":2}[r["result"]]
        n+=1; correct+=int(max(range(3),key=lambda i:p[i])==y); ll += -math.log(max(p[y],1e-15))
        one=[0.0,0.0,0.0];one[y]=1.0;br += sum((p[i]-one[i])**2 for i in range(3))
        top=max(p); hit=1.0 if max(range(3),key=lambda i:p[i])==y else 0.0; z=bins[min(9,int(top*10))];z[0]+=1;z[1]+=top;z[2]+=hit
    ece=sum((z[0]/n)*abs(z[1]/z[0]-z[2]/z[0]) for z in bins.values()) if n else None
    return {"n":n,"logLoss":ll/n if n else None,"brier":br/n if n else None,"accuracy":correct/n if n else None,"topPickECE":ece}


def select_weights(rows: list[dict[str,Any]], base_params: tuple[float,float,float,float]) -> tuple[tuple[float,float,float,float],dict[str,Any]]:
    # Intentionally conservative grid; the challenger must earn complexity.
    grid_pts=(-0.20,0.0,0.20,0.40)
    grid_gd=(-0.10,0.0,0.10,0.20)
    grid_opp=(-0.15,0.0,0.15)
    grid_rest=(-0.05,0.0,0.05)
    best=(0.0,0.0,0.0,0.0); bm=metrics(rows,base_params,best)
    for a in grid_pts:
        for b in grid_gd:
            for c in grid_opp:
                for d in grid_rest:
                    w=(a,b,c,d); m=metrics(rows,base_params,w)
                    if m["n"] and m["logLoss"] < bm["logLoss"]:
                        best,bm=w,m
    return best,bm


def current_adjustment(row: dict[str,Any], base_params: tuple[float,float,float,float], weights: tuple[float,float,float,float]) -> tuple[list[float],dict[str,Any]]:
    state=row.get("state") or {}; hp=state.get("home") or {}; ap=state.get("away") or {}
    vc=row.get("venueContext") or {}
    diff=state.get("eloDiffWithHomeAdvantage")
    if not isinstance(diff,(int,float)):
        return [],{"reason":"missing structural state"}
    # v1 stores +65 in eloDiffWithHomeAdvantage. Remove it when venue context removed home advantage.
    use_home=bool(vc.get("homeAdvantageApplied",True))
    elo_diff=float(diff) if use_home else float(diff)-65.0
    hist={"eloDiff":elo_diff,"homeAdvantage":use_home,"homeProfile":hp,"awayProfile":ap}
    return adjusted_probs(hist,base_params,weights)


def main() -> int:
    ap=argparse.ArgumentParser();ap.add_argument("--date",required=True);args=ap.parse_args();target=dt.date.fromisoformat(args.date)
    src=INTL/f"hbt_international_prospective_{target.isoformat()}.json"; doc=read(src,{})
    if doc.get("targetDate")!=target.isoformat(): raise SystemExit("prospective international card missing or wrong date")

    pinned,meta=v1.load_history(); countries={v1.norm(r["home"]) for r in pinned}|{v1.norm(r["away"]) for r in pinned}
    history,supp=v1.supplement_recent(pinned,target,countries); history=[r for r in history if r["date"]<target]
    rows=historical_rows(history)
    selection=[r for r in rows if dt.date(2023,1,1)<=r["date"]<=dt.date(2024,12,31)]
    holdout=[r for r in rows if dt.date(2025,1,1)<=r["date"]<target]
    base_params_doc=(doc.get("validation") or {}).get("selectedParams") or {}
    base_params=(float(base_params_doc.get("eloSlope",1.0)),float(base_params_doc.get("homeLogit",0.0)),float(base_params_doc.get("drawIntercept",0.0)),float(base_params_doc.get("drawMismatchPenalty",0.0)))
    zero=(0.0,0.0,0.0,0.0); weights,sel=select_weights(selection,base_params)
    hold=metrics(holdout,base_params,weights); base_hold=metrics(holdout,base_params,zero)
    improves=bool(hold["n"] and hold["logLoss"]<base_hold["logLoss"] and hold["brier"]<base_hold["brier"])

    out_rows=[]
    for original in doc.get("prospectiveCandidates") or []:
        r=json.loads(json.dumps(original)); p,explain=current_adjustment(r,base_params,weights)
        r.setdefault("intelligenceCoverage",{})["recentPerformanceInteractionTested"] = True
        r["recentPerformanceInteraction"]={"selectedWeights":weights,"explanation":explain,"validatedHoldoutImprovement":improves,"predictiveInfluenceAllowedInResearchChallenger":improves}
        if p and improves:
            r["baseStructuralProbabilityBeforeRecentInteraction"]=r.get("probs")
            r["probs"]={"H":p[0],"D":p[1],"A":p[2]}; r["pick"]=("H","D","A")[max(range(3),key=lambda i:p[i])];r["pickProbability"]=max(p);r["derivedMarkets"]=v1.derived_markets(p)
            r["predictionMode"]="INTERNATIONAL_STRUCTURAL_PLUS_RECENT_CHALLENGER_V3"
        r["execution"]={"class":"R0_SHADOW_RESEARCH","fundingAllowed":False,"reason":"international challenger remains unpromoted; recent interaction is research-only"}
        out_rows.append(r)

    validation={"selectionWindow":["2023-01-01","2024-12-31"],"holdoutWindow":["2025-01-01",target.isoformat()],"baseParams":base_params_doc,"selectedRecentWeights":{"pointsShare":weights[0],"goalDifference":weights[1],"opponentStrength":weights[2],"rest":weights[3]},"selection":sel,"holdout":hold,"structuralOnlyHoldout":base_hold,"improvesHoldoutLogLossAndBrier":improves,"promotionAllowed":False,"promotionBlock":"requires clean prospective confirmation and broader HBT-1.4 interaction/ablation validation"}
    out={"schemaVersion":"HBT-INTERNATIONAL-INTELLIGENCE-3","version":VERSION,"generatedAt":v1.now(),"targetDate":target.isoformat(),"source":src.name,"policy":{"researchOnly":True,"frozenHBT112Mutated":False,"domesticForecastsMutated":False,"bookmakerOddsRead":False,"missingIsZero":False,"missingContributionNeutral":True,"automaticPromotion":False,"automaticFunding":False},"historySource":meta,"recentSupplement":supp,"validation":validation,"summary":{"prospectiveRows":len(out_rows),"recentInteractionApplied":sum(1 for r in out_rows if r.get("predictionMode")=="INTERNATIONAL_STRUCTURAL_PLUS_RECENT_CHALLENGER_V3"),"fundedRows":0},"prospectiveCandidates":out_rows}
    write(INTL/f"hbt_international_intelligence_{target.isoformat()}.json",out)
    write(INTL/"hbt_international_recent_validation.json",{"version":VERSION,"generatedAt":out["generatedAt"],"validation":validation})
    print(json.dumps({"targetDate":target.isoformat(),"validation":validation,"summary":out["summary"]},indent=2));return 0

if __name__=="__main__": raise SystemExit(main())
