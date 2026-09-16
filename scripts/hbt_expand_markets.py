#!/usr/bin/env python3
"""Expand a date-scoped HBT forecast into market-level alternatives.

This is a decision/output layer only. It never changes HBT probabilities, never reads
bookmaker odds to form football probabilities, and never fabricates goal/event markets.

For every valid 1X2 probability vector it derives mathematically exact:
- home/draw/away 1X2
- double chance 1X, X2, 12
- draw-no-bet home/away (push on draw; fair odds derived from win/loss only)

If the forecast already contains validated scoreMarkets, it also exposes those exact
probabilities (totals, BTTS, team goals). No score-market probability is inferred from
1X2 alone.
"""
from __future__ import annotations

import argparse, json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'hbt_live_data'


def read(p: Path, default: Any):
    try: return json.loads(p.read_text(encoding='utf-8'))
    except Exception: return default


def write(p: Path, obj: Any):
    p.parent.mkdir(parents=True, exist_ok=True)
    t=p.with_suffix(p.suffix+'.tmp'); t.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); t.replace(p)


def valid_probs(v):
    return isinstance(v,list) and len(v)==3 and all(isinstance(x,(int,float)) and 0<=float(x)<=1 for x in v) and abs(sum(v)-1)<0.02


def fair(p):
    return (1.0/p) if p and p>0 else None


def add(rows, fx, family, selection, p, source, quality=None, tier=None, push=None, meta=None):
    rows.append({
        'fixture':fx,'family':family,'selection':selection,'modelProbability':p,
        'fairOdds':fair(p) if push is None else None,'pushProbability':push,
        'source':source,'quality':quality,'sourceTier':tier,'meta':meta or {},
    })


def expand(pred: dict[str,Any], source_type: str):
    probs=pred.get('probs');
    if not valid_probs(probs): return []
    h,d,a=map(float,probs); fx=pred.get('fixture') or {}; q=pred.get('quality'); tier=pred.get('tier')
    rows=[]
    add(rows,fx,'1X2','HOME WIN',h,source_type,q,tier)
    add(rows,fx,'1X2','DRAW',d,source_type,q,tier)
    add(rows,fx,'1X2','AWAY WIN',a,source_type,q,tier)
    add(rows,fx,'DOUBLE_CHANCE','1X — Home or Draw',h+d,source_type,q,tier)
    add(rows,fx,'DOUBLE_CHANCE','X2 — Draw or Away',d+a,source_type,q,tier)
    add(rows,fx,'DOUBLE_CHANCE','12 — Either Team to Win',h+a,source_type,q,tier)
    # DNB is a push market: fair decimal odds solve p_win*(odds-1)-p_loss=0.
    non_draw=h+a
    if h>0:
        rows.append({'fixture':fx,'family':'DRAW_NO_BET','selection':'HOME DNB','modelProbabilityConditional':h/non_draw if non_draw else None,'winProbability':h,'lossProbability':a,'pushProbability':d,'fairOdds':(non_draw/h) if h else None,'source':source_type,'quality':q,'sourceTier':tier,'meta':{}})
    if a>0:
        rows.append({'fixture':fx,'family':'DRAW_NO_BET','selection':'AWAY DNB','modelProbabilityConditional':a/non_draw if non_draw else None,'winProbability':a,'lossProbability':h,'pushProbability':d,'fairOdds':(non_draw/a) if a else None,'source':source_type,'quality':q,'sourceTier':tier,'meta':{}})

    sm=pred.get('scoreMarkets') or {}
    exact=[
        ('TOTAL_GOALS','Over 1.5',sm.get('over15')),('TOTAL_GOALS','Under 1.5',sm.get('under15')),
        ('TOTAL_GOALS','Over 2.5',sm.get('over25')),('TOTAL_GOALS','Under 2.5',sm.get('under25')),
        ('TOTAL_GOALS','Over 3.5',sm.get('over35')),('TOTAL_GOALS','Under 3.5',sm.get('under35')),
        ('BTTS','BTTS Yes',sm.get('bttsYes')),('BTTS','BTTS No',sm.get('bttsNo')),
        ('TEAM_GOALS','Home Over 0.5',sm.get('homeOver05')),('TEAM_GOALS','Away Over 0.5',sm.get('awayOver05')),
        ('TEAM_GOALS','Home Over 1.5',sm.get('homeOver15')),('TEAM_GOALS','Away Over 1.5',sm.get('awayOver15')),
    ]
    for fam,sel,pv in exact:
        if isinstance(pv,(int,float)) and 0<=float(pv)<=1: add(rows,fx,fam,sel,float(pv),source_type,q,tier,meta={'scoreModelExact':True})
    return rows


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--forecast',required=True); ap.add_argument('--output',required=True); ap.add_argument('--min-prob',type=float,default=0.0); args=ap.parse_args()
    src=OUT/args.forecast; doc=read(src,{})
    rows=[]; source_type=str(doc.get('sourceLabVersion') or doc.get('sourceEngineVersion') or src.name)
    for pred in doc.get('predictions') or []: rows.extend(expand(pred,source_type))
    def rp(x): return float(x.get('modelProbability') if x.get('modelProbability') is not None else x.get('modelProbabilityConditional') or 0)
    rows=[x for x in rows if rp(x)>=args.min_prob]
    rows.sort(key=lambda x:(-rp(x),str((x.get('fixture') or {}).get('time') or ''),str(x.get('family') or '')))
    payload={'schemaVersion':'HBT-MARKET-EXPANSION-1','targetDate':doc.get('targetDate'),'sourceForecast':src.name,'policy':{'bookmakerOddsUsedAsPredictiveFeature':False,'footballProbabilitiesMutated':False,'derived1X2MarketsExact':True,'scoreMarketsOnlyWhenProvidedByModel':True,'avoidIsMarketLevelNotFixtureLevel':True},'candidates':rows}
    write(OUT/args.output,payload)
    print('expanded',len(rows),'market candidates to',args.output)

if __name__=='__main__': main()
