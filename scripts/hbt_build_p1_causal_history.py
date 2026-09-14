#!/usr/bin/env python3
"""HBT-1.2R-R3 causal P1 history builder (research only).

Only observations from league fixtures dated strictly before the target match may
enter `features`. Target-round lineup/availability appears only in `auditLabels`
and is never eligible for training. HBT-1.1.2L-R1 is not modified.
"""
from __future__ import annotations
import argparse, datetime as dt, json, math, re, sys, time, unicodedata, urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any
import hbt_collect_players_espn as p

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'hbt_research_data'/'p1_causal_dataset.json'
OPEN='https://raw.githubusercontent.com/openfootball/football.json/master'
AVAPI='https://api.github.com/repos/withqwerty/availability-data/contents/raw'
AVRAW='https://raw.githubusercontent.com/withqwerty/availability-data/main/raw'
LEAGUES={'en.1':'GB1','es.1':'ES1','de.1':'L1','it.1':'IT1','fr.1':'FR1'}
IN_SQUAD={'starting','sub_in','bench'}; UNAVAILABLE={'injured','suspended'}
MAX_HIST=6; MIN_HIST=3
ALIASES={'internazionale milano':'internazionale','inter milan':'internazionale','bayern munchen':'bayern munich','borussia monchengladbach':'borussia gladbach','atletico de madrid':'atletico madrid','real sociedad de futbol':'real sociedad'}

def norm(s:str)->str:
    s=unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode().lower().replace('&',' and ')
    s=re.sub(r'\b(fc|cf|afc|ac|ssc|sv|sc|rcd|rc|club|calcio|futbol|fussball|de|la|the)\b',' ',s)
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',s)).strip()

def toks(s:str)->set[str]:
    k=ALIASES.get(norm(s),norm(s)); return {x for x in k.split() if x not in {'de','del','la','the','and'}}

def score_name(a:str,b:str)->float:
    aa,bb=toks(a),toks(b)
    if not aa or not bb:return 0.0
    if aa==bb:return 1.0
    return max(len(aa&bb)/max(1,len(aa|bb)),0.88 if aa<=bb or bb<=aa else 0.0)

def rnd(v:Any)->int|None:
    m=re.search(r'(\d+)',str(v or '')); return int(m.group(1)) if m else None

def ft(m:dict[str,Any])->tuple[int,int]|None:
    s=m.get('score'); s=(s.get('ft') or s.get('fulltime') or s.get('fullTime')) if isinstance(s,dict) else s
    try:return (int(s[0]),int(s[1])) if isinstance(s,list) and len(s)>=2 else None
    except Exception:return None

def season_slug(y:int)->str:return f'{y}-{(y+1)%100:02d}'
def pid(q:dict[str,Any])->str:return f"tm:{q['tmId']}" if q.get('tmId') not in (None,'') else 'name:'+norm(q.get('name') or '')
def starters(row:list[dict[str,Any]])->set[str]:return {str(x.get('id')) for x in row if x.get('status')=='starting' and x.get('id')}
def finite_diff(a:Any,b:Any)->float|None:
    try:
        a,b=float(a),float(b); return a-b if math.isfinite(a) and math.isfinite(b) else None
    except Exception:return None

def by_round(raw:dict[str,Any]|None,code:str)->dict[int,list[dict[str,Any]]]:
    if not raw:return {}
    comp=next((c for c in raw.get('competitions') or [] if isinstance(c,dict) and str(c.get('code') or '')==code),None)
    if not comp:return {}
    out=defaultdict(list)
    for q in comp.get('players') or []:
        if not isinstance(q,dict):continue
        base={'id':pid(q),'name':str(q.get('name') or ''),'pos':str(q.get('position') or '').upper()}
        for m in q.get('matches') or []:
            r=rnd(m.get('round')) if isinstance(m,dict) else None
            if r is not None:out[r].append({**base,'status':str(m.get('status') or '').lower(),'detail':str(m.get('detail') or '')[:500]})
    return dict(out)

def round_dates(matches:list[dict[str,Any]])->dict[str,dict[int,str]]:
    out=defaultdict(dict)
    for m in matches:
        r,d=rnd(m.get('round')),str(m.get('date') or '')
        if r is None or not d:continue
        for t in (str(m.get('team1') or ''),str(m.get('team2') or '')):
            if t:out[norm(t)][r]=d
    return dict(out)

def stability(hist:list[list[dict[str,Any]]])->float|None:
    if len(hist)<2:return None
    z=[]; prev=starters(hist[0])
    for row in hist[1:]:
        cur=starters(row)
        if len(prev)>=10 and len(cur)>=10:z.append(len(prev&cur)/11)
        prev=cur
    return sum(z)/len(z) if z else None

def snapshot(target_date:str,target_round:int,rows:dict[int,list[dict[str,Any]]],dates:dict[int,str])->dict[str,Any]|None:
    use=[r for r,d in dates.items() if d and d<target_date and r in rows and len(starters(rows[r]))>=10]
    use=sorted(use,key=lambda r:(dates[r],r))[-MAX_HIST:]
    if len(use)<MIN_HIST:return None
    hist=[rows[r] for r in use]; universe={}
    for row in hist:
        for q in row:
            if q.get('id'):universe[str(q['id'])]={'id':str(q['id']),'name':q.get('name') or '','pos':q.get('pos') or ''}
    info=[]
    for q in universe.values():
        sts=[]
        for row in hist:
            f=next((x for x in row if str(x.get('id'))==q['id']),None); sts.append(str(f.get('status') if f else 'not_in_squad'))
        imp,n=p.player_importance(sts); info.append({**q,'importance':imp,'priorN':n})
    ideal=p.select_xi(info)
    if len(ideal)<10:return None
    ids={x['id'] for x in ideal}; last=hist[-1]; prev=starters(last)
    pg=next((x for x in last if x.get('status')=='starting' and str(x.get('pos') or '').upper() in {'GK','G'}),None)
    eg=next((x for x in ideal if str(x.get('pos') or '').upper() in {'GK','G'}),None)
    cont=.85*p.clip(len(prev&ids)/11,0,1)+.15*(1.0 if pg and eg and str(pg.get('id'))==eg['id'] else 0.0)
    strength=sum(float(x.get('importance') or 0) for x in ideal) or 1.0
    lmap={str(x.get('id')):x for x in hist[-1] if x.get('id')}; pmap={str(x.get('id')):x for x in hist[-2] if x.get('id')}
    lag=[x for x in ideal if str((lmap.get(x['id']) or {}).get('status') or '') in UNAVAILABLE]
    per=[x for x in lag if str((pmap.get(x['id']) or {}).get('status') or '') in UNAVAILABLE]
    return {'priorMatches':len(hist),'priorRounds':use,'expectedXI':[x['name'] for x in ideal],'expectedXIIds':[x['id'] for x in ideal],
            'expectedContinuity':cont,'priorLineupStability':stability(hist),
            'laggedAvailabilityLoss':p.clip(sum(float(x.get('importance') or 0) for x in lag)/strength,0,1),'laggedUnavailableIdealN':len(lag),
            'persistentUnavailableLoss':p.clip(sum(float(x.get('importance') or 0) for x in per)/strength,0,1),'persistentUnavailableIdealN':len(per),
            'featureCutoff':{'strictlyBeforeKickoff':True,'latestSourceRound':use[-1],'latestSourceDate':dates[use[-1]],'targetRound':target_round,'targetDate':target_date}}

def labels(snap:dict[str,Any]|None,target:list[dict[str,Any]])->dict[str,Any]:
    if not snap:return {'available':False,'eligibleForTraining':False}
    actual=starters(target); exp=set(snap.get('expectedXIIds') or [])
    un=[x for x in target if x.get('status') in UNAVAILABLE and str(x.get('id')) in exp]
    return {'available':len(actual)>=10,'eligibleForTraining':False,'reason':'target-round status is reveal-only; archive is not timestamped pre-kickoff',
            'expectedXIStarterHitRate':len(actual&exp)/11 if len(actual)>=10 else None,'targetRoundUnavailableExpectedN':len(un),'targetRoundUnavailableExpected':[x.get('name') for x in un]}

class Archive:
    def __init__(self):self.dirs={};self.files={};self.audit=[]
    def directory(self,code:str,season:int):
        k=(code,season)
        if k not in self.dirs:
            try:
                z=p.http_json(f'{AVAPI}/{code}/{season}?ref=main',25,2);self.dirs[k]=z if isinstance(z,list) else []
                self.audit.append({'source':'availability-directory','league':code,'season':season,'status':'loaded','count':len(self.dirs[k])})
            except Exception as e:self.dirs[k]=[];self.audit.append({'source':'availability-directory','league':code,'season':season,'status':'failed','error':str(e)[:250]})
        return self.dirs[k]
    def team(self,code:str,season:int,name:str):
        k=(code,season,norm(name))
        if k in self.files:return self.files[k]
        cand=[]
        for r in self.directory(code,season):
            fn=str(r.get('name') or '') if isinstance(r,dict) else ''
            if r.get('type')=='file' and fn.endswith('.json'):cand.append((score_name(name,re.sub(r'\.json$','',fn)),fn))
        cand.sort(reverse=True)
        if not cand or cand[0][0]<.5 or (len(cand)>1 and cand[0][0]<.9 and cand[0][0]-cand[1][0]<.15):self.files[k]=None;return None
        try:
            raw=p.http_json(f'{AVRAW}/{code}/{season}/{urllib.parse.quote(cand[0][1])}',25,2)
            self.files[k]=raw if isinstance(raw,dict) and score_name(name,str(raw.get('club') or raw.get('tmSlug') or ''))>=.45 else None
        except Exception:self.files[k]=None
        return self.files[k]

def main(argv:list[str]|None=None)->int:
    ap=argparse.ArgumentParser();ap.add_argument('--season-start',type=int,default=2021);ap.add_argument('--season-end',type=int,default=2025);ap.add_argument('--leagues',default=','.join(LEAGUES));ap.add_argument('--out',type=Path,default=OUT)
    a=ap.parse_args(argv or sys.argv[1:]); leagues=[x.strip() for x in a.leagues.split(',') if x.strip()]
    if any(x not in LEAGUES for x in leagues):raise SystemExit('unsupported league')
    ar=Archive(); fixtures=[]; audit=[]
    for season in range(a.season_start,a.season_end+1):
        for league in leagues:
            try:
                z=p.http_json(f'{OPEN}/{season_slug(season)}/{league}.json',30,2);matches=z.get('matches') if isinstance(z,dict) else []
                audit.append({'source':'openfootball','league':league,'season':season,'status':'loaded','matches':len(matches)})
            except Exception as e:audit.append({'source':'openfootball','league':league,'season':season,'status':'failed','error':str(e)[:250]});continue
            dates=round_dates(matches); code=LEAGUES[league]
            for m in matches:
                r,d=rnd(m.get('round')),str(m.get('date') or '');h,aw=str(m.get('team1') or ''),str(m.get('team2') or '');sc=ft(m)
                if r is None or not d or not h or not aw or sc is None:continue
                hr,rr=ar.team(code,season,h),ar.team(code,season,aw); hb,ab=by_round(hr,code),by_round(rr,code)
                hs=snapshot(d,r,hb,dates.get(norm(h),{})) if hr else None; ass=snapshot(d,r,ab,dates.get(norm(aw),{})) if rr else None
                f=None
                if hs and ass:f={'expectedContinuityDiff':finite_diff(hs['expectedContinuity'],ass['expectedContinuity']),'priorLineupStabilityDiff':finite_diff(hs['priorLineupStability'],ass['priorLineupStability']),'laggedAvailabilityAdv':finite_diff(ass['laggedAvailabilityLoss'],hs['laggedAvailabilityLoss']),'persistentAvailabilityAdv':finite_diff(ass['persistentUnavailableLoss'],hs['persistentUnavailableLoss'])}
                hg,ag=sc; fixtures.append({'fixtureKey':f'{d}|{league}|{norm(h)}|{norm(aw)}','season':season,'league':league,'round':r,'date':d,'home':h,'away':aw,'result':{'hg':hg,'ag':ag,'class':'H' if hg>ag else ('D' if hg==ag else 'A')},'researchOnly':True,'frozenPredictiveVersion':'HBT-1.1.2L-R1','featureReadiness':'causal-p1-ready' if f else 'insufficient-history-or-identity','features':f,'homeDetail':hs,'awayDetail':ass,'auditLabels':{'home':labels(hs,hb.get(r,[])),'away':labels(ass,ab.get(r,[]))},'trainingPolicy':{'allowedFeatureObject':'features','forbiddenObjects':['auditLabels','result','target-round status'],'feedsBackIntoPrediction':False,'oddsUsed':False}})
    ready=sum(x.get('features') is not None for x in fixtures)
    payload={'schemaVersion':'HBT-P1-CAUSAL-1','researchVersion':'HBT-1.2R-R3-P1-Causal','generatedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'sourcePredictiveModel':'HBT-1.1.2L-R1','researchOnly':True,'newLearnedModelParameters':[],
             'policy':{'historicalReplayInvariant':'information known before match -> feature snapshot -> freeze -> reveal result','targetRoundLineupUsedAsFeature':False,'targetRoundAvailabilityUsedAsFeature':False,'strictFeatureCutoff':'fixture date strictly earlier than target date','retrospectiveTargetRoundAvailability':'audit-only; not timestamped pre-kickoff','promotionGate':'separate challenger backtest, freeze, then OOS validation before any HBT-1.1.2 change','oddsUsed':False,'feedsBackIntoPrediction':False},
             'featureFamilies':{'continuity':['expectedContinuityDiff','priorLineupStabilityDiff'],'laggedAvailability':['laggedAvailabilityAdv','persistentAvailabilityAdv']},'summary':{'fixtures':len(fixtures),'causalP1Ready':ready,'notReady':len(fixtures)-ready,'readyPct':ready/len(fixtures) if fixtures else 0},'sourceAudit':audit+ar.audit,'fixtures':fixtures}
    a.out.parent.mkdir(parents=True,exist_ok=True);p.write_json(a.out,payload);print(json.dumps(payload['summary'],indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
