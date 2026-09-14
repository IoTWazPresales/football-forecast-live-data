#!/usr/bin/env python3
"""Apply validated HBT-1.3 event-market parameters to the live feed.

This is the promoted market-specific path for corners, yellow cards, team shots
and SOT once event_model_params.json proves holdout improvement. Red cards stay
research-only because their holdout NLL did not beat baseline.
"""
from __future__ import annotations
import json, math
from pathlib import Path
from typing import Any

import hbt_collect_market_intelligence_v4_runtime_xhr as base

v4=base.run.v4
ROOT=Path(__file__).resolve().parents[1]
PARAMS=ROOT/'hbt_live_data'/'event_model_params.json'
_orig_profile=v4.team_recent_profile


def _ew(vals:list[float],decay:float)->tuple[float|None,float]:
    if not vals:return None,0.0
    vals=vals[-30:];num=den=0.0
    for i,x in enumerate(vals):
        w=decay**(len(vals)-1-i);num+=w*float(x);den+=w
    return (num/den if den else None),den

def _shrink(mean:float|None,neff:float,prior:float|None,prior_n:float)->float|None:
    if prior is None:return mean
    if mean is None:return float(prior)
    return (float(mean)*neff+float(prior)*prior_n)/max(1e-9,neff+prior_n)

def _params()->dict[str,Any]:
    try:return json.load(open(PARAMS,encoding='utf-8'))
    except Exception:return {}
EP=_params()
MAP={'corners':'corners','yellowCards':'yellow_cards','shots':'shots','shotsOnTarget':'shots_on_target','redCards':'red_cards'}


def calibrated_profile(team_id:str,prev:list[dict[str,Any]],cache:dict[str,Any]):
    metrics,rows=_orig_profile(team_id,prev,cache)
    league=str((prev[-1] if prev else {}).get('league') or '')
    split={}
    for family,key in MAP.items():
        model=((EP.get('models') or {}).get(family) or {});par=model.get('parameters') or {};prior=((EP.get('livePriors') or {}).get(league) or {}).get(family) or {}
        decay=float(par.get('decay') or .94);pn=float(par.get('priorN') or 2.0)
        vals={'homeFor':[],'homeAgainst':[],'awayFor':[],'awayAgainst':[]}
        for x in rows:
            ev=x.get('event') or {};own=x.get('own') or {};opp=x.get('opp') or {}
            ov=own.get(key);pv=opp.get(key)
            if ov is None or pv is None:continue
            if str(ev.get('homeId') or '')==str(team_id):vals['homeFor'].append(float(ov));vals['homeAgainst'].append(float(pv))
            elif str(ev.get('awayId') or '')==str(team_id):vals['awayFor'].append(float(ov));vals['awayAgainst'].append(float(pv))
        z={}
        for name,arr in vals.items():
            mean,n=_ew(arr,decay);side='home' if name.startswith('home') else 'away';pr=prior.get(side+'Mean');z[name]=_shrink(mean,n,pr,pn);z[name+'N']=len(arr);z[name+'EffectiveN']=n
        z['holdoutNLLDelta']=(model.get('promotionEvidence') or {}).get('holdoutNLLDelta');z['promoted']=family!='redCards' and z['holdoutNLLDelta'] is not None and z['holdoutNLLDelta']<0
        split[family]=z
    metrics['calibratedVenueSplit']=split;return metrics,rows

v4.team_recent_profile=calibrated_profile


def apply()->None:
    try:data=json.load(open(v4.OUTPUT,encoding='utf-8'))
    except Exception:return
    for row in (data.get('fixtures') or {}).values():
        h=(row.get('homeDetail') or {}).get('recent') or {};a=(row.get('awayDetail') or {}).get('recent') or {};em=row.setdefault('eventMarkets',{})
        promoted=[]
        for family in ('corners','yellowCards','shots','shotsOnTarget','redCards'):
            hs=(h.get('calibratedVenueSplit') or {}).get(family) or {};as_=(a.get('calibratedVenueSplit') or {}).get(family) or {};model=((EP.get('models') or {}).get(family) or {});par=model.get('parameters') or {};blend=float(par.get('attackBlend') or .5)
            hf,ha=hs.get('homeFor'),hs.get('homeAgainst');af,aa=as_.get('awayFor'),as_.get('awayAgainst')
            mh=(blend*hf+(1-blend)*aa) if hf is not None and aa is not None else None
            ma=(blend*af+(1-blend)*ha) if af is not None and ha is not None else None
            target=em.setdefault(family,{})
            target.update({'homeLambda':mh,'awayLambda':ma,'totalLambda':(mh+ma if mh is not None and ma is not None else None),'calibrationVersion':EP.get('version'),'holdoutNLLDelta':(model.get('promotionEvidence') or {}).get('holdoutNLLDelta'),'validatedMarketModel':family!='redCards' and (model.get('promotionEvidence') or {}).get('holdoutNLLDelta',1)>=-999 and (model.get('promotionEvidence') or {}).get('holdoutNLLDelta',1)<0})
            if target['validatedMarketModel'] and target['totalLambda'] is not None:promoted.append(family)
        row['validatedEventFamilies']=promoted
        rd=row.setdefault('readiness',{});rd['corners']='corners' in promoted;rd['cards']='yellowCards' in promoted;rd['teamShots']='shots' in promoted;rd['teamSOT']='shotsOnTarget' in promoted;rd['redCards']=False
    data.setdefault('policy',{})['validatedEventModels']='corners, yellow cards, team shots, team SOT use frozen HBT-1.3 event calibration; red cards remain research-only'
    data['eventCalibrationVersion']=EP.get('version')
    base.run.p.write_json(v4.OUTPUT,data)


def main()->int:
    rc=v4.main();apply();base.run.postprocess();return rc

if __name__=='__main__':raise SystemExit(main())
