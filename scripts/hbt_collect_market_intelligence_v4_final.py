#!/usr/bin/env python3
"""Final HBT-1.3 live market-intelligence runtime.

Adds the frozen player-prop calibration to the same-source Football-Data event
runtime. Player shots/SOT/anytime-goal probabilities are calibrated with the
selection-frozen scale factors that improved every player-prop family on the
2025-26 holdout. They remain action-eligible only for a confirmed starting XI.
"""
from __future__ import annotations
import json, math
from pathlib import Path

import hbt_collect_market_intelligence_v4_footballdata as base

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'hbt_live_data';OUTPUT=OUT/'market_intelligence.json';PROP=OUT/'player_prop_model_params.json'

def ptail(lam:float,n:int)->float:
    lam=max(1e-9,float(lam));term=math.exp(-lam);cdf=term
    for k in range(1,n):term*=lam/k;cdf+=term
    return max(0.0,min(1.0,1.0-cdf))

def apply_player_calibration()->None:
    data=json.load(open(OUTPUT,encoding='utf-8'));p=json.load(open(PROP,encoding='utf-8'))
    scales=(p.get('parameters') or {}).get('scales') or {};evidence=(p.get('promotionEvidence') or {}).get('allHoldoutMarkets') or {}
    ok=all(float(v.get('deltaLogloss',1))<0 for v in evidence.values()) and len(evidence)>=6
    sides=players=0
    for row in (data.get('fixtures') or {}).values():
        row.setdefault('policy',{})['playerProps']='validated only for confirmed starting XI; expected-XI values are WATCH context until lineup confirmation'
        for side in ('homeDetail','awayDetail'):
            arr=(row.get(side) or {}).get('players') or []
            matched=0
            for z in arr:
                if not z.get('understatId'):continue
                sh=max(0.0,float(z.get('lambdaShots') or 0))*float(scales.get('shots') or 1)
                so=max(0.0,float(z.get('lambdaSOT') or 0))*float(scales.get('sot') or 1)
                go=max(0.0,float(z.get('lambdaGoalRaw') or 0))*float(scales.get('goal') or 1)
                z.update({'lambdaShots':round(sh,4),'lambdaSOT':round(so,4),'lambdaGoalRaw':round(go,4),
                          'pShot1Plus':ptail(sh,1),'pShot2Plus':ptail(sh,2),'pShot3Plus':ptail(sh,3),
                          'pSOT1Plus':ptail(so,1),'pSOT2Plus':ptail(so,2),'pAnytimeGoalRaw':ptail(go,1),
                          'playerPropCalibrationVersion':p.get('version'),'validatedPlayerPropModel':bool(ok)})
                matched+=1;players+=1
            if matched:sides+=1
        row.setdefault('readiness',{})['playerProps']=bool(ok and any((row.get(s) or {}).get('players') for s in ('homeDetail','awayDetail')))
        row['playerPropActionGate']='CONFIRMED-XI only'
    data['playerPropCalibrationVersion']=p.get('version')
    data.setdefault('policy',{})['playerPropRuntime']='HBT-1.3 frozen scale calibration; all six holdout families beat position baseline; actionable only on confirmed XI'
    data.setdefault('health',{})['playerValidatedSides']=sides
    data.setdefault('health',{})['playerValidatedRows']=players
    base.base.base.run.p.write_json(OUTPUT,data)

def main()->int:
    rc=base.main();apply_player_calibration();return rc

if __name__=='__main__':raise SystemExit(main())
