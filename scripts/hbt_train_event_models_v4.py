#!/usr/bin/env python3
"""Causal historical calibration for HBT-1.3 team event markets.

Uses Football-Data Big-Five league CSVs. Every prediction is emitted before the
match row updates team/league state. Parameters are selected on 2023-24 and
2024-25 only, then frozen for a 2025-26 holdout.

Families: corners, yellow cards, team shots, shots on target, red cards.
Bookmaker odds are not inputs.
"""
from __future__ import annotations
import csv, io, json, math, urllib.request, datetime as dt
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'hbt_live_data'
OUTPUT=OUT/'event_model_params.json'
UA='Mozilla/5.0 (compatible; HBT-Event-Training/1.0)'
LEAGUES={'E0':'en.1','SP1':'es.1','D1':'de.1','I1':'it.1','F1':'fr.1'}
SEASONS=list(range(2014,2026))
METRICS={
 'corners':('HC','AC',[8.5,9.5,10.5]),
 'yellowCards':('HY','AY',[3.5,4.5,5.5]),
 'shots':('HS','AS',[20.5,24.5,28.5]),
 'shotsOnTarget':('HST','AST',[7.5,8.5,9.5]),
 'redCards':('HR','AR',[0.5,1.5]),
}
GRID=[(d,n,b) for d in (.72,.82,.89,.94,.97) for n in (2.,5.,8.,12.) for b in (.4,.5,.6)]


def fetch_text(url:str)->str:
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/csv,*/*'})
    with urllib.request.urlopen(req,timeout=30) as r:return r.read().decode('utf-8-sig','replace')
def season_code(y:int)->str:return f'{y%100:02d}{(y+1)%100:02d}'
def parse_date(s:str)->dt.date|None:
    s=(s or '').strip()
    for f in ('%d/%m/%Y','%d/%m/%y'):
        try:return dt.datetime.strptime(s,f).date()
        except:pass
    return None
def num(x:Any)->float|None:
    try:
        if x is None or str(x).strip()=='':return None
        return float(x)
    except:return None

def load()->tuple[list[dict[str,Any]],list[dict[str,Any]]]:
    out=[];audit=[]
    for y in SEASONS:
      sc=season_code(y)
      for div,league in LEAGUES.items():
        url=f'https://www.football-data.co.uk/mmz4281/{sc}/{div}.csv'
        try:
          txt=fetch_text(url);rows=list(csv.DictReader(io.StringIO(txt)));n=0
          for r in rows:
            d=parse_date(r.get('Date',''));h=(r.get('HomeTeam') or '').strip();a=(r.get('AwayTeam') or '').strip()
            if not d or not h or not a:continue
            z={'date':d,'season':y,'league':league,'home':h,'away':a};good=False
            for name,(hc,ac,_) in METRICS.items():
              hv,av=num(r.get(hc)),num(r.get(ac));z[name]=(hv,av);good=good or (hv is not None and av is not None)
            if good:out.append(z);n+=1
          audit.append({'season':y,'league':league,'rows':n,'url':url,'status':'loaded'})
        except Exception as e:audit.append({'season':y,'league':league,'rows':0,'url':url,'status':'failed','error':str(e)[:180]})
    out.sort(key=lambda r:(r['date'],r['league'],r['home'],r['away']));return out,audit

def ew(vals:list[float],decay:float)->tuple[float|None,float]:
    if not vals:return None,0.
    vals=vals[-30:];num=den=0.
    for i,v in enumerate(vals):
      w=decay**(len(vals)-1-i);num+=w*v;den+=w
    return (num/den if den else None),den
def shrink(mean:float|None,neff:float,prior:float,prior_n:float)->float:
    if mean is None:return prior
    return (mean*neff+prior*prior_n)/(neff+prior_n)
def pnll(y:float,mu:float)->float:
    mu=max(1e-6,mu);return mu-y*math.log(mu)+math.lgamma(y+1)
def ptail(mu:float,line:float)->float:
    k=int(math.floor(line))+1;term=math.exp(-max(0.,mu));cdf=term
    for i in range(1,k):term*=mu/i;cdf+=term
    return max(0.,min(1.,1-cdf))
def blogloss(y:int,p:float)->float:
    p=max(1e-9,min(1-1e-9,p));return -(y*math.log(p)+(1-y)*math.log(1-p))

def replay(rows:list[dict[str,Any]],metric:str,params:tuple[float,float,float],score_seasons:set[int])->dict[str,Any]:
    decay,prior_n,blend=params
    state=defaultdict(lambda:{'hf':[],'ha':[],'af':[],'aa':[]});league=defaultdict(lambda:{'h':[],'a':[]})
    n=0;ll=base_ll=ae=base_ae=0.;lines=METRICS[metric][2];line_stats={str(x):[0.,0.,0] for x in lines}
    for r in rows:
      pair=r.get(metric);hv,av=pair if pair else (None,None)
      if hv is None or av is None:continue
      lk=r['league'];hs=state[(lk,r['home'])];as_=state[(lk,r['away'])]
      ph=sum(league[lk]['h'])/len(league[lk]['h']) if league[lk]['h'] else hv
      pa=sum(league[lk]['a'])/len(league[lk]['a']) if league[lk]['a'] else av
      haf,nh=ew(hs['hf'],decay);hada,nd=ew(as_['ha'],decay);aaf,na=ew(as_['af'],decay);hdaa,nhd=ew(hs['aa'],decay)
      ah=shrink(haf,nh,ph,prior_n);dh=shrink(hada,nd,ph,prior_n);aa=shrink(aaf,na,pa,prior_n);da=shrink(hdaa,nhd,pa,prior_n)
      mh=max(.03,blend*ah+(1-blend)*dh);ma=max(.03,blend*aa+(1-blend)*da)
      if r['season'] in score_seasons:
        n+=1;ll+=pnll(hv,mh)+pnll(av,ma);base_ll+=pnll(hv,ph)+pnll(av,pa);ae+=abs(hv-mh)+abs(av-ma);base_ae+=abs(hv-ph)+abs(av-pa)
        for line in lines:
          prob=ptail(mh+ma,line);y=int(hv+av>line);q=line_stats[str(line)];q[0]+=blogloss(y,prob);q[1]+=1;q[2]+=abs(y-prob)
      hs['hf'].append(hv);hs['aa'].append(av);as_['af'].append(av);as_['ha'].append(hv);league[lk]['h'].append(hv);league[lk]['a'].append(av)
    return {'n':n,'poissonNLLPerTeam':ll/max(1,2*n),'baselineNLLPerTeam':base_ll/max(1,2*n),'maePerTeam':ae/max(1,2*n),'baselineMaePerTeam':base_ae/max(1,2*n),'lines':{k:{'binaryLogloss':v[0]/max(1,v[1]),'maeCalibration':v[2]/max(1,v[1]),'n':int(v[1])} for k,v in line_stats.items()}}

def main()->int:
    OUT.mkdir(parents=True,exist_ok=True);rows,audit=load();selection={2023,2024};holdout={2025};models={}
    for metric in METRICS:
      best=None
      for par in GRID:
        z=replay(rows,metric,par,selection);key=z['poissonNLLPerTeam']
        if best is None or key<best[0]:best=(key,par,z)
      assert best is not None
      _,par,sel=best;ho=replay(rows,metric,par,holdout)
      models[metric]={'parameters':{'decay':par[0],'priorN':par[1],'attackBlend':par[2]},'selection':sel,'holdout':ho,'promotionEvidence':{'holdoutNLLDelta':ho['poissonNLLPerTeam']-ho['baselineNLLPerTeam'],'holdoutMaeDelta':ho['maePerTeam']-ho['baselineMaePerTeam']}}
      print(metric,par,'selection',sel['poissonNLLPerTeam'],'holdout',ho['poissonNLLPerTeam'],'baseline',ho['baselineNLLPerTeam'])
    payload={'schemaVersion':'HBT-EVENT-MODELS-1','version':'HBT-1.3R-EVENT-CAL','generatedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'source':'football-data.co.uk','sourcePolicy':'match statistics only; bookmaker odds ignored','seasons':SEASONS,'selectionSeasons':[2023,2024],'holdoutSeason':2025,'models':models,'sourceAudit':audit}
    OUTPUT.write_text(json.dumps(payload,separators=(',',':')),encoding='utf-8');print('wrote',OUTPUT,'rows',len(rows));return 0
if __name__=='__main__':raise SystemExit(main())
