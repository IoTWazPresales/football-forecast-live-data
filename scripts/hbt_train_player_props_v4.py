#!/usr/bin/env python3
"""HBT-1.3R causal player-prop calibration.

Confirmed-XI scenario. Understat match rosters identify starters; target-match
minutes/shots/SOT/goals are outcomes only and never features. Player rates are
seeded by the previous completed season and updated strictly after each match.

Selection: 2024-25 Big Five. Frozen holdout: 2025-26 Big Five.
Markets: 1+/2+/3+ shots, 1+/2+ SOT, anytime goal.
Bookmaker odds are excluded.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json, math, time
from collections import defaultdict
from pathlib import Path
from typing import Any

import hbt_collect_players_espn as net

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'hbt_live_data'; OUTPUT=OUT/'player_prop_model_params.json'
VERSION='HBT-1.3R-PLAYER-PROP-CAL'
LEAGUES=['EPL','La_liga','Bundesliga','Serie_A','Ligue_1']
SELECTION=2024; HOLDOUT=2025
PRIOR_MINUTES=[180.,360.,720.,1080.]
SCALES=[.78,.88,.96,1.0,1.06,1.14,1.24]
SOT_SHARE={'F':.39,'M':.34,'D':.25,'GK':.12,'X':.32}


def f(v:Any,default:float=0.)->float:
    try:return float(v)
    except:return default

def pos_group(raw:str)->str:
    s=str(raw or '').upper()
    if s in {'GK','G'}:return 'GK'
    if s=='SUB':return 'X'
    if any(x in s for x in ('FW','FWR','FWL','CF','ST')) or s in {'F'}:return 'F'
    if any(x in s for x in ('AM','ML','MR','MC','DM','M')):return 'M'
    if any(x in s for x in ('DC','DL','DR','DML','DMR','D')):return 'D'
    return 'X'
def player_id(q:dict[str,Any])->str:return str(q.get('player_id') or q.get('id') or '')
def league_data(league:str,season:int)->dict[str,Any]:
    return net.http_json(f'https://understat.com/getLeagueData/{league}/{season}',30,3)
def match_data(mid:str)->dict[str,Any]:
    return net.http_json(f'https://understat.com/getMatchData/{mid}',25,3)
def match_list(pack:dict[str,Any])->list[dict[str,Any]]:
    rows=pack.get('dates') or []
    out=[]
    for r in rows:
      if not r.get('isResult'):continue
      mid=str(r.get('id') or '')
      if not mid:continue
      stamp=str(r.get('datetime') or r.get('date') or '')
      out.append({'id':mid,'datetime':stamp})
    return out
def roster_sides(raw:dict[str,Any])->dict[str,dict[str,dict[str,Any]]]:
    ro=raw.get('rosters') or {};out={'h':{},'a':{}}
    for side in ('h','a'):
      src=ro.get(side) or {}
      vals=src.values() if isinstance(src,dict) else src if isinstance(src,list) else []
      for q in vals:
        if not isinstance(q,dict):continue
        pid=player_id(q)
        if pid:out[side][pid]=q
    return out
def shot_actual(raw:dict[str,Any])->dict[str,dict[str,int]]:
    res=defaultdict(lambda:{'shots':0,'sot':0,'goals':0})
    sh=raw.get('shots') or {}
    for side in ('h','a'):
      for q in sh.get(side) or []:
        if not isinstance(q,dict):continue
        pid=str(q.get('player_id') or '')
        if not pid:continue
        z=res[pid];z['shots']+=1;typ=str(q.get('result') or '')
        if typ in {'Goal','SavedShot'}:z['sot']+=1
        if typ=='Goal':z['goals']+=1
    return res

def prior_pack(league:str,season:int)->tuple[dict[str,dict[str,float]],dict[str,dict[str,float]]]:
    raw=league_data(league,season-1);players=raw.get('players') or []
    by={};grp=defaultdict(lambda:{'minutes':0.,'shots':0.,'xg':0.,'goals':0.})
    for q in players:
      pid=str(q.get('id') or q.get('player_id') or '')
      mins=f(q.get('time'));shots=f(q.get('shots'));xg=f(q.get('xG'));goals=f(q.get('goals'));pg=pos_group(q.get('position'))
      if mins<=0:continue
      if pid:by[pid]={'minutes':mins,'shots':shots,'xg':xg,'goals':goals,'pg':pg}
      g=grp[pg];g['minutes']+=mins;g['shots']+=shots;g['xg']+=xg;g['goals']+=goals
    rates={}
    for pg,g in grp.items():
      m=max(1.,g['minutes']);rates[pg]={'shot90':90*g['shots']/m,'xg90':90*g['xg']/m,'goal90':90*g['goals']/m,'sot90':90*g['shots']/m*SOT_SHARE.get(pg,.32)}
    return by,rates

def fetch_season(league:str,season:int)->tuple[list[dict[str,Any]],dict[str,dict[str,float]],dict[str,dict[str,float]]]:
    pack=league_data(league,season);matches=match_list(pack);prior,rates=prior_pack(league,season)
    data=[]
    def one(r:dict[str,Any]):
      try:return {**r,'data':match_data(r['id'])}
      except Exception as e:return {**r,'data':None,'error':str(e)}
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
      for i,z in enumerate(ex.map(one,matches)):
        if z.get('data'):data.append(z)
        if i and i%80==0:print(league,season,'fetched',i,'/',len(matches),flush=True)
    data.sort(key=lambda x:x.get('datetime') or '')
    return data,prior,rates

def ptail(lam:float,n:int)->float:
    lam=max(1e-8,lam);term=math.exp(-lam);cdf=term
    for k in range(1,n):term*=lam/k;cdf+=term
    return max(0.,min(1.,1-cdf))
def ll(y:int,p:float)->float:
    p=max(1e-9,min(1-1e-9,p));return -(y*math.log(p)+(1-y)*math.log(1-p))

def replay(season_data:dict[str,tuple[list[dict[str,Any]],dict[str,dict[str,float]],dict[str,dict[str,float]]]],prior_minutes:float,scales:dict[str,float])->dict[str,Any]:
    sums=defaultdict(float);counts=defaultdict(int);base_sums=defaultdict(float);rows=0
    per_market=defaultdict(lambda:{'ll':0.,'baseLL':0.,'brier':0.,'baseBrier':0.,'n':0})
    for league,(matches,prev,rates) in season_data.items():
      state=defaultdict(lambda:{'minutes':0.,'shots':0.,'sot':0.,'xg':0.,'goals':0.,'starts':0.,'startMinutes':0.})
      for m in matches:
        raw=m['data'];rost=roster_sides(raw);act=shot_actual(raw)
        starters=[]
        for side in ('h','a'):
          for pid,q in rost[side].items():
            pos=str(q.get('position') or '')
            if pos.upper()=='SUB' or pos_group(pos)=='GK':continue
            starters.append((pid,q))
        for pid,q in starters:
          pg=pos_group(q.get('position'));pr=prev.get(pid);gprior=rates.get(pg) or rates.get('X') or {'shot90':1.,'sot90':.32,'xg90':.12,'goal90':.10}
          if pr and f(pr.get('minutes'))>0:
            pm=f(pr['minutes']);p_sh=90*f(pr.get('shots'))/pm;p_xg=90*f(pr.get('xg'))/pm;p_sot=p_sh*SOT_SHARE.get(pg,.32)
          else:p_sh,p_xg,p_sot=gprior['shot90'],gprior['xg90'],gprior['sot90']
          st=state[pid];cm=st['minutes'];den=cm+prior_minutes
          sh90=(90*st['shots']/max(1.,cm)*cm + p_sh*prior_minutes)/max(1.,den) if cm>0 else p_sh
          so90=(90*st['sot']/max(1.,cm)*cm + p_sot*prior_minutes)/max(1.,den) if cm>0 else p_sot
          xg90=(90*st['xg']/max(1.,cm)*cm + p_xg*prior_minutes)/max(1.,den) if cm>0 else p_xg
          min_est=max(55.,min(90.,st['startMinutes']/st['starts'] if st['starts'] else 78.))
          lam={'shots':sh90/90*min_est*scales['shots'],'sot':so90/90*min_est*scales['sot'],'goal':xg90/90*min_est*scales['goal']}
          blam={'shots':gprior['shot90']/90*78.,'sot':gprior['sot90']/90*78.,'goal':gprior['xg90']/90*78.}
          ac=act.get(pid) or {'shots':int(f(q.get('shots'))),'sot':0,'goals':int(f(q.get('goals')))}
          for family,levels in (('shots',(1,2,3)),('sot',(1,2)),('goal',(1,))):
            actual=ac['goals'] if family=='goal' else ac[family]
            for n in levels:
              key='anytimeGoal' if family=='goal' else f'{family}{n}Plus';y=int(actual>=n);prb=ptail(lam[family],n);bp=ptail(blam[family],n);z=per_market[key];z['ll']+=ll(y,prb);z['baseLL']+=ll(y,bp);z['brier']+=(y-prb)**2;z['baseBrier']+=(y-bp)**2;z['n']+=1
          rows+=1
        # target outcome becomes state only now
        for side in ('h','a'):
          for pid,q in rost[side].items():
            pos=str(q.get('position') or '')
            mins=f(q.get('time'));st=state[pid];ac=act.get(pid) or {'shots':int(f(q.get('shots'))),'sot':0,'goals':int(f(q.get('goals')))}
            st['minutes']+=mins;st['shots']+=ac['shots'];st['sot']+=ac['sot'];st['xg']+=f(q.get('xG'));st['goals']+=ac['goals']
            if pos.upper()!='SUB' and pos_group(pos)!='GK':st['starts']+=1;st['startMinutes']+=mins
    markets={}
    for k,z in per_market.items():
      n=max(1,z['n']);markets[k]={'n':z['n'],'logloss':z['ll']/n,'baselineLogloss':z['baseLL']/n,'deltaLogloss':(z['ll']-z['baseLL'])/n,'brier':z['brier']/n,'baselineBrier':z['baseBrier']/n,'deltaBrier':(z['brier']-z['baseBrier'])/n}
    score=sum(v['logloss'] for v in markets.values())/max(1,len(markets));return {'starterRows':rows,'score':score,'markets':markets}

def main()->int:
    OUT.mkdir(parents=True,exist_ok=True);all_data={};audit=[]
    for season in (SELECTION,HOLDOUT):
      all_data[season]={}
      for league in LEAGUES:
        try:
          x=fetch_season(league,season);all_data[season][league]=x;audit.append({'league':league,'season':season,'matches':len(x[0]),'status':'loaded'})
        except Exception as e:audit.append({'league':league,'season':season,'matches':0,'status':'failed','error':str(e)[:200]})
    # tune each family scale jointly with common prior minutes using selection score
    best=None
    for pm in PRIOR_MINUTES:
      # first tune family scales one by one around shared state replay; small grid exhaustive 4*7^3 is still fine but expensive
      scales={'shots':1.,'sot':1.,'goal':1.}
      for fam in ('shots','sot','goal'):
        pick=None
        for sc in SCALES:
          cand=dict(scales);cand[fam]=sc;z=replay(all_data[SELECTION],pm,cand)
          keys=[k for k in z['markets'] if (k.startswith('shots') if fam=='shots' else k.startswith('sot') if fam=='sot' else k=='anytimeGoal')]
          score=sum(z['markets'][k]['logloss'] for k in keys)/max(1,len(keys))
          if pick is None or score<pick[0]:pick=(score,sc)
        scales[fam]=pick[1]
      z=replay(all_data[SELECTION],pm,scales)
      if best is None or z['score']<best[0]:best=(z['score'],pm,dict(scales),z)
      print('candidate',pm,scales,z['score'],flush=True)
    assert best
    _,pm,scales,sel=best;hold=replay(all_data[HOLDOUT],pm,scales)
    payload={'schemaVersion':'HBT-PLAYER-PROP-1','version':VERSION,'generatedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'source':'Understat getLeagueData/getMatchData','sourcePolicy':'confirmed starting XI allowed; target minutes/shots/SOT/goals are outcome-only; bookmaker odds excluded','selectionSeason':SELECTION,'holdoutSeason':HOLDOUT,'parameters':{'priorMinutes':pm,'scales':scales},'selection':sel,'holdout':hold,'sourceAudit':audit,'promotionEvidence':{'allHoldoutMarkets':{k:{'n':v['n'],'deltaLogloss':v['deltaLogloss'],'deltaBrier':v['deltaBrier']} for k,v in hold['markets'].items()}}}
    OUTPUT.write_text(json.dumps(payload,separators=(',',':')),encoding='utf-8');print('selected',pm,scales,'holdout score',hold['score']);print(json.dumps(payload['promotionEvidence'],indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
