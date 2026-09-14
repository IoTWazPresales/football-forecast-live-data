#!/usr/bin/env python3
"""Audit whether frozen HBT adds predictive information beyond 1X2 market prices.

Research-only L5 analysis. Bookmaker probabilities NEVER feed the football model.
They are used only after frozen HBT probabilities exist.
"""
from __future__ import annotations
import csv, io, json, math, random, re, unicodedata, urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASELINE=ROOT/'research/l5/epl_2018_19_frozen_l1_all.csv'
OUTDIR=ROOT/'research/l5/output'; OUTDIR.mkdir(parents=True,exist_ok=True)
ODDS_URL='https://raw.githubusercontent.com/obameyan/QoreSDK-Premire-League/master/data/PremierLeague/2018-19.csv'
Y_TO_RESULT={0:'H',1:'D',2:'A'}
ALIASES={
'manchester united':'man united','man united':'man united','manchester city':'man city','man city':'man city',
'newcastle united':'newcastle','newcastle':'newcastle','tottenham hotspur':'tottenham','tottenham':'tottenham',
'wolverhampton wanderers':'wolves','wolverhampton':'wolves','wolves':'wolves','afc bournemouth':'bournemouth','bournemouth':'bournemouth',
'brighton hove albion':'brighton','brighton':'brighton','west ham united':'west ham','west ham':'west ham',
'huddersfield town':'huddersfield','huddersfield':'huddersfield','leicester city':'leicester','leicester':'leicester',
'cardiff city':'cardiff','cardiff':'cardiff'}

def key(s):
 s=unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().lower().replace('&',' ')
 s=re.sub(r'[^a-z0-9]+',' ',s).strip(); s=' '.join(t for t in s.split() if t not in {'fc','cf'})
 return ALIASES.get(s,s)

def fd_date(s):
 d,m,y=s.strip().split('/'); return f'{int(y):04d}-{int(m):02d}-{int(d):02d}'

def fetch(url):
 req=urllib.request.Request(url,headers={'User-Agent':'HBT-L5-research/1.0'})
 with urllib.request.urlopen(req,timeout=30) as r:return r.read().decode('utf-8-sig')

def load():
 with BASELINE.open(newline='',encoding='utf-8') as f:b=list(csv.DictReader(f))
 base=[]
 for r in b:base.append({'date':r['date'],'home':r['home'],'away':r['away'],'hk':key(r['home']),'ak':key(r['away']),'y':int(r['y']),'p':[float(r['pH']),float(r['pD']),float(r['pA'])]})
 odds={}
 for r in csv.DictReader(io.StringIO(fetch(ODDS_URL))):
  try:o=[float(r['B365H']),float(r['B365D']),float(r['B365A'])]
  except (KeyError,ValueError,TypeError):continue
  if not all(math.isfinite(x) and x>1 for x in o):continue
  imp=[1/x for x in o]; z=sum(imp); q=[x/z for x in imp]
  odds[(fd_date(r['Date']),key(r['HomeTeam']),key(r['AwayTeam']))]={'o':o,'q':q,'ftr':r.get('FTR'),'home':r['HomeTeam'],'away':r['AwayTeam']}
 joined=[];missing=[];mismatch=[]
 for r in base:
  x=odds.get((r['date'],r['hk'],r['ak']))
  if not x: missing.append(r);continue
  if x['ftr']!=Y_TO_RESULT[r['y']]:mismatch.append((r,x))
  joined.append({**r,**x})
 if missing or mismatch:raise SystemExit(f'join audit failed missing={len(missing)} mismatch={len(mismatch)} firstMissing={missing[:3]}')
 return joined

def met(rows,pkey):
 n=len(rows);ll=br=0.;correct=0
 for r in rows:
  p=r[pkey] if isinstance(pkey,str) else pkey(r); y=r['y']
  ll-=math.log(max(1e-15,p[y]));br+=sum((p[i]-(1 if i==y else 0))**2 for i in range(3))/3
  correct+=max(range(3),key=lambda i:p[i])==y
 return {'n':n,'logloss':ll/n,'brier':br/n,'accuracy':correct/n}

def pool(p,q,a):
 # geometric/logarithmic pool; a=0 market only, a=1 HBT only
 v=[(max(1e-15,p[i])**a)*(max(1e-15,q[i])**(1-a)) for i in range(3)];z=sum(v);return [x/z for x in v]

def paired_ll(rows,fn_a,fn_b,B=5000,seed=117):
 by=defaultdict(list)
 for r in rows:
  pa,pb=fn_a(r),fn_b(r);y=r['y'];by[r['date']].append(-math.log(max(1e-15,pa[y]))+math.log(max(1e-15,pb[y])))
 blocks=list(by.values());obs=sum(sum(x) for x in blocks)/sum(len(x) for x in blocks)
 rng=random.Random(seed);vals=[]
 for _ in range(B):
  s=n=0
  for __ in range(len(blocks)):
   b=blocks[rng.randrange(len(blocks))];s+=sum(b);n+=len(b)
  vals.append(s/n)
 vals.sort();return {'deltaLogloss':obs,'ci95':[vals[int(.025*B)],vals[min(B-1,int(.975*B))]],'bootstrap':'date-block'}

def roi_policy(rows,probfn,min_ev=.05):
 bets=[]
 for r in rows:
  p=probfn(r);ev=[p[i]*r['o'][i]-1 for i in range(3)];i=max(range(3),key=lambda j:ev[j])
  if ev[i]<min_ev:continue
  profit=r['o'][i]-1 if r['y']==i else -1
  bets.append((r['date'],profit,r['y']==i,r['o'][i],ev[i],i))
 n=len(bets);pr=sum(x[1] for x in bets)
 return {'bets':n,'wins':sum(x[2] for x in bets),'hitRate':sum(x[2] for x in bets)/n if n else None,'profitUnits':pr,'roi':pr/n if n else None,'avgOdds':sum(x[3] for x in bets)/n if n else None,'avgModelEV':sum(x[4] for x in bets)/n if n else None}

def main():
 rows=load();train=[r for r in rows if r['date']<'2019-01-01'];val=[r for r in rows if '2019-01-01'<=r['date']<'2019-03-01'];test=[r for r in rows if r['date']>='2019-03-01']
 grid=[i/20 for i in range(21)]
 train_scores=[]
 for a in grid:
  mm=met(train,lambda r,a=a:pool(r['p'],r['q'],a));train_scores.append({'alphaHBT':a,**mm})
 train_scores.sort(key=lambda x:x['logloss']);selected=train_scores[0]['alphaHBT']
 fn=lambda r:pool(r['p'],r['q'],selected)
 splits={}
 for name,rr in [('train',train),('validation',val),('final',test)]:
  splits[name]={
   'hbt':met(rr,'p'),'marketVigFree':met(rr,'q'),'selectedBlend':met(rr,fn),
   'hbtVsMarket':paired_ll(rr,lambda r:r['p'],lambda r:r['q']),
   'blendVsMarket':paired_ll(rr,fn,lambda r:r['q']),
   'rawHbt5pctValuePolicy':roi_policy(rr,lambda r:r['p'],.05),
   'blend5pctValuePolicy':roi_policy(rr,fn,.05)}
 result={
  'createdAt':datetime.now(timezone.utc).isoformat(),'researchOnly':True,'footballModelModified':False,'oddsFeedBackIntoProbability':False,
  'sourcePredictiveModel':'Frozen HBT-0.5P L1 parameters / HBT-1.1.2 benchmark',
  'oddsSource':{'mirror':ODDS_URL,'columns':['B365H','B365D','B365A'],'timingCaveat':'Historical pre-match/pre-closing benchmark without observation timestamp.'},
  'cohort':{'joined':len(rows),'train':len(train),'validation':len(val),'final':len(test),'trainEnd':'2018-12-31','validation':'2019-01-01..2019-02-28','finalStart':'2019-03-01'},
  'blend':{'method':'geometric probability pool: p ~ HBT^alpha * market^(1-alpha)','alphaGrid':grid,'selectedOnTrainOnly':selected,'trainGrid':train_scores},
  'splits':splits}
 out=OUTDIR/'hbt_l5_epl_market_signal_audit.json';out.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'selectedAlphaHBT':selected,'cohort':result['cohort'],'splits':splits,'output':str(out)},indent=2))

if __name__=='__main__':main()
