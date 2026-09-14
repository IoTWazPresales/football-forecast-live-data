#!/usr/bin/env python3
"""HBT-1.3 live event-market runtime using the same source/model family as validation.

Runs the existing HBT-1.3 collector, then replaces event-market lambdas for
corners, yellow cards, team shots and shots-on-target with a causal replay over
Football-Data's previous + current Big-Five seasons. This fixes the ESPN schedule
coverage gap while keeping the live calculation source-compatible with the
historical model that passed holdout validation.

No bookmaker odds are consumed. Only matches dated before the target fixture are
used. Red cards remain rejected because their holdout NLL failed promotion.
"""
from __future__ import annotations

import csv, datetime as dt, io, json, math, re, unicodedata, urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

import hbt_collect_market_intelligence_v4_calibrated as base

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'hbt_live_data'
OUTPUT=OUT/'market_intelligence.json'
PARAMS=OUT/'event_model_params.json'
UA='Mozilla/5.0 (compatible; HBT-1.3-Live-Event/1.0)'
DIV={'en.1':'E0','es.1':'SP1','de.1':'D1','it.1':'I1','fr.1':'F1'}
COLS={
 'corners':('HC','AC'),
 'yellowCards':('HY','AY'),
 'shots':('HS','AS'),
 'shotsOnTarget':('HST','AST'),
 'redCards':('HR','AR'),
}


def season_code(y:int)->str:
    return f'{y%100:02d}{(y+1)%100:02d}'

def get_text(url:str)->str:
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/csv,*/*'})
    with urllib.request.urlopen(req,timeout=25) as r:
        return r.read().decode('utf-8-sig','replace')

def parse_date(s:str)->dt.date|None:
    for f in ('%d/%m/%Y','%d/%m/%y'):
        try:return dt.datetime.strptime((s or '').strip(),f).date()
        except Exception:pass
    return None

def fnum(x:Any)->float|None:
    try:
        if x is None or str(x).strip()=='':return None
        return float(x)
    except Exception:return None

def key(s:str)->str:
    s=unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode().lower()
    s=s.replace('&',' and ')
    s=re.sub(r'\b(fc|cf|afc|ac|ssc|calcio|football|club|de|futbol|fussball|sv|vfb|vfl|as|ss)\b',' ',s)
    s=re.sub(r'[^a-z0-9]+',' ',s)
    aliases={
      'inter milan':'inter','internazionale':'inter','internazionale milano':'inter',
      'real betis balompie':'betis','real betis':'betis',
      'paris saint germain':'paris sg','paris st germain':'paris sg',
      'man utd':'man united','manchester utd':'man united',
      'newcastle united':'newcastle','leeds united':'leeds',
      'brighton and hove albion':'brighton','wolves':'wolverhampton wanderers',
      'monchengladbach':'m gladbach','borussia monchengladbach':'m gladbach',
      'bayern munich':'bayern munich','bayern munchen':'bayern munich',
    }
    s=' '.join(s.split())
    return aliases.get(s,s)

def match_name(name:str,candidates:set[str])->str|None:
    k=key(name)
    if not k:return None
    direct=[c for c in candidates if key(c)==k]
    if direct:return direct[0]
    kt=set(k.split());best=None
    for c in candidates:
        ck=key(c);ct=set(ck.split())
        if not ct:continue
        if k in ck or ck in k:score=.92
        else:score=len(kt&ct)/max(1,len(kt|ct))
        if best is None or score>best[0]:best=(score,c)
    return best[1] if best and best[0]>=.50 else None

def ew(vals:list[float],decay:float)->tuple[float|None,float]:
    if not vals:return None,0.0
    vals=vals[-30:];num=den=0.0
    for i,v in enumerate(vals):
        w=decay**(len(vals)-1-i);num+=w*v;den+=w
    return (num/den if den else None),den

def shrink(mean:float|None,neff:float,prior:float,prior_n:float)->float:
    if mean is None:return prior
    return (mean*neff+prior*prior_n)/max(1e-9,neff+prior_n)

def load_league(league:str,target_year:int)->tuple[list[dict[str,Any]],list[dict[str,Any]]]:
    div=DIV[league];rows=[];audit=[]
    for y in (target_year-1,target_year):
        url=f'https://www.football-data.co.uk/mmz4281/{season_code(y)}/{div}.csv'
        try:
            raw=list(csv.DictReader(io.StringIO(get_text(url))));n=0
            for r in raw:
                d=parse_date(r.get('Date',''));h=(r.get('HomeTeam') or '').strip();a=(r.get('AwayTeam') or '').strip()
                if not d or not h or not a:continue
                z={'date':d,'home':h,'away':a}
                good=False
                for fam,(hc,ac) in COLS.items():
                    hv,av=fnum(r.get(hc)),fnum(r.get(ac));z[fam]=(hv,av);good=good or (hv is not None and av is not None)
                if good:rows.append(z);n+=1
            audit.append({'season':y,'league':league,'rows':n,'url':url,'status':'loaded'})
        except Exception as exc:
            audit.append({'season':y,'league':league,'rows':0,'url':url,'status':'failed','error':str(exc)[:160]})
    rows.sort(key=lambda r:(r['date'],r['home'],r['away']))
    return rows,audit

def fixture_event(rows:list[dict[str,Any]],home:str,away:str,target:dt.date,params:dict[str,Any])->dict[str,Any]:
    prior=[r for r in rows if r['date']<target]
    candidates={r['home'] for r in prior}|{r['away'] for r in prior}
    hn=match_name(home,candidates);an=match_name(away,candidates)
    out={'matchedHome':hn,'matchedAway':an,'priorRows':len(prior),'families':{}}
    if not hn or not an:return out
    for fam in ('corners','yellowCards','shots','shotsOnTarget','redCards'):
        model=((params.get('models') or {}).get(fam) or {});par=model.get('parameters') or {}
        decay=float(par.get('decay') or .94);pn=float(par.get('priorN') or 2.0);blend=float(par.get('attackBlend') or .5)
        lh=[];la=[];hhf=[];haa=[];aaf=[];aha=[]
        for r in prior:
            pair=r.get(fam);hv,av=pair if pair else (None,None)
            if hv is None or av is None:continue
            lh.append(float(hv));la.append(float(av))
            if r['home']==hn:hhf.append(float(hv));haa.append(float(av))
            if r['away']==an:aaf.append(float(av));aha.append(float(hv))
        if not lh or not la:continue
        ph=sum(lh)/len(lh);pa=sum(la)/len(la)
        mhf,nh=ew(hhf,decay);mhaa,nha=ew(haa,decay);maf,na=ew(aaf,decay);maha,nah=ew(aha,decay)
        ah=shrink(mhf,nh,ph,pn);dh=shrink(mhaa,nha,ph,pn)
        aa=shrink(maf,na,pa,pn);da=shrink(maha,nah,pa,pn)
        home_mu=max(.03,blend*ah+(1-blend)*da)
        away_mu=max(.03,blend*aa+(1-blend)*dh)
        delta=(model.get('promotionEvidence') or {}).get('holdoutNLLDelta')
        promoted=fam!='redCards' and delta is not None and float(delta)<0
        out['families'][fam]={
          'homeLambda':home_mu,'awayLambda':away_mu,'totalLambda':home_mu+away_mu,
          'history':{'homeForN':len(hhf),'homeAgainstN':len(haa),'awayForN':len(aaf),'awayAgainstN':len(aha),'leaguePriorN':len(lh)},
          'calibrationVersion':params.get('version'),'holdoutNLLDelta':delta,'validatedMarketModel':promoted,
          'source':'football-data previous+current season causal replay'
        }
    return out

def enrich()->None:
    data=json.load(open(OUTPUT,encoding='utf-8'));params=json.load(open(PARAMS,encoding='utf-8'))
    year=int(data.get('seasonStartYear') or 2026);cache={};audit=[]
    for league in DIV:
        rows,a=load_league(league,year);cache[league]=rows;audit.extend(a)
    health={'corners':0,'cards':0,'teamShots':0,'teamSOT':0}
    for row in (data.get('fixtures') or {}).values():
        league=str(row.get('league') or '');kick=str(row.get('kickoff') or '')
        try:target=dt.date.fromisoformat(kick[:10])
        except Exception:continue
        z=fixture_event(cache.get(league,[]),str(row.get('home') or ''),str(row.get('away') or ''),target,params)
        row['footballDataEventState']={k:v for k,v in z.items() if k!='families'}
        em=row.setdefault('eventMarkets',{});prom=[]
        for fam,v in (z.get('families') or {}).items():
            em[fam]=v
            if v.get('validatedMarketModel') and v.get('totalLambda') is not None:prom.append(fam)
        row['validatedEventFamilies']=prom
        rd=row.setdefault('readiness',{})
        rd['corners']='corners' in prom;rd['cards']='yellowCards' in prom;rd['teamShots']='shots' in prom;rd['teamSOT']='shotsOnTarget' in prom;rd['redCards']=False
        health['corners']+=int(rd['corners']);health['cards']+=int(rd['cards']);health['teamShots']+=int(rd['teamShots']);health['teamSOT']+=int(rd['teamSOT'])
    data['footballDataLiveAudit']=audit
    data.setdefault('policy',{})['eventRuntime']='validated HBT-1.3 Football-Data causal replay over previous+current season; target date excluded; odds unused'
    data.setdefault('health',{}).update({k+'Ready':v for k,v in health.items()})
    base.base.run.p.write_json(OUTPUT,data)

def main()->int:
    rc=base.main();enrich();return rc

if __name__=='__main__':raise SystemExit(main())
