#!/usr/bin/env python3
"""Causal HBT-1.4 historical match-intelligence extractor (Big Five 2018-19).

Bookmaker odds are excluded. Target-match result/stats/minutes/substitutions are
state updates only AFTER the pre-kickoff feature snapshot is emitted. Starting-XI,
bench identity and named referee are treated as pre-kickoff-known information.
Historical actual/reanalysis weather is deliberately NOT substituted for a forecast.
"""
from __future__ import annotations
import concurrent.futures as cf, csv, datetime as dt, io, json, re, unicodedata, urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any
import hbt_collect_live_data as live

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'hbt_live_data'
OUTPUT=OUT/'hbt_1_4_historical_features_2018_19.json'; CACHE=OUT/'_hbt_1_4_hist_cache.json'
VERSION='HBT-1.4R-HISTORICAL-MATCH-INTEL-2018'; SEASON=2018
UNDERSTAT={'en.1':('EPL','E0'),'es.1':('La_liga','SP1'),'de.1':('Bundesliga','D1'),'it.1':('Serie_A','I1'),'fr.1':('Ligue_1','F1')}
EVENT={'shots':('HS','AS'),'shotsOnTarget':('HST','AST'),'corners':('HC','AC'),'yellowCards':('HY','AY'),'redCards':('HR','AR')}
UA='Mozilla/5.0 (compatible; HBT-1.4-Historical/1.0)'

def now(): return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def f(x):
    try: return None if x is None or str(x).strip()=='' else float(x)
    except: return None
def key(s):
    s=unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode().lower().replace('&',' and ')
    s=re.sub(r'\b(fc|cf|afc|ac|ssc|calcio|football|club|de|futbol|fussball|sv|vfb|vfl|as|ss|us)\b',' ',s); s=' '.join(re.sub(r'[^a-z0-9]+',' ',s).split())
    aliases={'internazionale milano':'inter','internazionale':'inter','inter milan':'inter','paris saint germain':'psg','paris sg':'psg','olympique marseille':'marseille','olympique lyonnais':'lyon','borussia monchengladbach':'monchengladbach','m gladbach':'monchengladbach','bayern munich':'bayern','bayern munchen':'bayern','tottenham hotspur':'tottenham','wolverhampton wanderers':'wolves','leicester city':'leicester','manchester united':'man united','manchester city':'man city','newcastle united':'newcastle','west ham united':'west ham','brighton and hove albion':'brighton','deportivo alaves':'alaves','real betis balompie':'betis','real betis':'betis','athletic club':'athletic bilbao'}
    return aliases.get(s,s)
def date(s):
    for fmt in ('%d/%m/%Y','%d/%m/%y','%Y-%m-%d'):
        try:return dt.datetime.strptime(str(s or '')[:10],fmt).date()
        except:pass
    return None
def ppda(x):
    if isinstance(x,dict):
        a,d=f(x.get('att')),f(x.get('def')); return a/d if a is not None and d not in (None,0) else None
    return f(x)
def ew(vals,decay=.86,limit=12):
    v=[float(x) for x in vals if x is not None][-limit:]
    if not v:return None
    num=den=0.0
    for i,x in enumerate(v):w=decay**(len(v)-1-i);num+=w*x;den+=w
    return num/den if den else None
def dif(a,b):return a-b if a is not None and b is not None else None
def gettxt(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/csv,*/*'});return urllib.request.urlopen(req,timeout=30).read().decode('utf-8-sig','replace')
def readcache():
    try:
        x=json.loads(CACHE.read_text());return x if isinstance(x,dict) else {}
    except:return {}
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,separators=(',',':'),ensure_ascii=False))
def usleague(name,season):return live.http_json(f'https://understat.com/getLeagueData/{name}/{season}',30,3)
def usmatch(mid,cache):
    old=cache.setdefault('matches',{}).get(str(mid))
    if isinstance(old,dict):return old
    try:r=live.http_json(f'https://understat.com/getMatchData/{mid}',25,3);cache['matches'][str(mid)]=r;return r
    except:return None

def load_us():
    matches=[]; teams={}; seeds={}
    for league,(name,_) in UNDERSTAT.items():
        raw=usleague(name,SEASON); tv=(raw.get('teams') or {}); tv=tv.values() if isinstance(tv,dict) else tv
        for t in tv:
            title=str((t or {}).get('title') or ''); hist=[]
            if not title:continue
            for x in (t or {}).get('history') or []:
                d=date(x.get('date'))
                if d:hist.append({'date':d.isoformat(),'npxG':f(x.get('npxG')),'npxGA':f(x.get('npxGA')),'deep':f(x.get('deep')),'deep_allowed':f(x.get('deep_allowed')),'ppda':ppda(x.get('ppda')),'ppda_allowed':ppda(x.get('ppda_allowed')),'scored':f(x.get('scored')),'missed':f(x.get('missed'))})
            teams[f'{league}|{key(title)}']=sorted(hist,key=lambda z:z['date'])
        for r in raw.get('dates') or []:
            if not r.get('isResult'):continue
            d=date(r.get('datetime') or r.get('date')); h=r.get('h') or {};a=r.get('a') or {}
            if d:matches.append({'league':league,'date':d.isoformat(),'id':str(r.get('id') or ''),'home':h.get('title') or h.get('name') or '','away':a.get('title') or a.get('name') or ''})
        prev=usleague(name,SEASON-1); pm={}
        for q in prev.get('players') or []:
            pid=str(q.get('id') or q.get('player_id') or ''); mins=f(q.get('time')) or 0
            if pid and mins>0:pm[pid]={'minutes':mins,'shots':f(q.get('shots')) or 0,'xG':f(q.get('xG')) or 0,'xA':f(q.get('xA')) or 0,'key_passes':f(q.get('key_passes')) or 0,'goals':f(q.get('goals')) or 0}
        seeds[league]=pm
    matches.sort(key=lambda r:(r['date'],r['league'],key(r['home']),key(r['away'])));return matches,teams,seeds

def roster(raw,side):
    src=((raw.get('rosters') or {}).get(side)) or {}; vals=src.values() if isinstance(src,dict) else src if isinstance(src,list) else []
    out=[]
    for q in vals:
        if not isinstance(q,dict):continue
        out.append({'id':str(q.get('player_id') or q.get('id') or ''),'name':str(q.get('player') or q.get('player_name') or q.get('name') or ''),'position':str(q.get('position') or ''),'time':f(q.get('time')) or 0,'xG':f(q.get('xG')) or 0,'xA':f(q.get('xA')) or 0,'shots':f(q.get('shots')) or 0,'key_passes':f(q.get('key_passes')) or 0,'goals':f(q.get('goals')) or 0})
    return out
def shots(raw,side):return [q for q in ((raw.get('shots') or {}).get(side) or []) if isinstance(q,dict)]
def shot_summary(raw,side):
    rows=shots(raw,side)
    def sx(names):return sum(f(q.get('xG')) or 0 for q in rows if str(q.get('situation') or '') in names)
    return {'setPieceXG':sx({'FromCorner','SetPiece','DirectFreekick'}),'cornerXG':sx({'FromCorner'}),'directFKXG':sx({'DirectFreekick'}),'openPlayXG':sx({'OpenPlay'})}
def shape(rows):
    d=m=a=g=0; st=[q for q in rows if q['position'].upper()!='SUB']
    for q in st:
        p=q['position'].upper()
        if p=='GK':g+=1
        elif p.startswith('D'):d+=1
        elif 'FW' in p or p in {'F','CF','ST'}:a+=1
        else:m+=1
    return {'gk':g,'def':d,'mid':m,'att':a,'known':len(st),'aggression':a+.45*m if len(st)>=10 else None}
def prior_rate(pid,state,seed):
    st=state.get(pid) or {}; sm=st.get('minutes',0); pr=seed.get(pid) or {}; pm=pr.get('minutes',0); pn=720.0
    def R(k):
        cur=90*st.get(k,0)/sm if sm>0 else None; old=90*pr.get(k,0)/pm if pm>0 else 0
        return old if cur is None else (cur*sm+old*pn)/(sm+pn)
    return {k:R(k) for k in ('shots','xG','xA','key_passes','goals')}
def xi_impact(rows,state,seed):
    st=[q for q in rows if q['position'].upper()!='SUB']; bench=[q for q in rows if q['position'].upper()=='SUB']
    def strength(arr):
        vals=[]
        for q in arr:
            r=prior_rate(q['id'],state,seed); vals.append(r['xG']+.55*r['xA']+.08*r['shots']+.03*r['key_passes'])
        return sum(vals),vals
    ss,_=strength(st);bs,bv=strength(bench);gk=next((q for q in st if q['position'].upper()=='GK'),None)
    return {'starterAttackIndex':ss,'benchAttackIndex':bs,'benchTop3AttackIndex':sum(sorted(bv,reverse=True)[:3]),'starterN':len(st),'benchN':len(bench),'goalkeeperId':(gk or {}).get('id'),'goalkeeperName':(gk or {}).get('name')}
def update_players(rows,state):
    for q in rows:
        if not q['id']:continue
        z=state.setdefault(q['id'],{'minutes':0,'shots':0,'xG':0,'xA':0,'key_passes':0,'goals':0})
        for k in z:z[k]+=float(q.get(k) or 0)

def sc(y):return f'{y%100:02d}{(y+1)%100:02d}'
def load_fd():
    out={};audit=[]
    for league,(_,div) in UNDERSTAT.items():
        arr=[]
        for sy in (SEASON-1,SEASON):
            url=f'https://www.football-data.co.uk/mmz4281/{sc(sy)}/{div}.csv'
            try:
                raw=list(csv.DictReader(io.StringIO(gettxt(url))));n=0
                for r in raw:
                    d=date(r.get('Date'));h=(r.get('HomeTeam') or '').strip();a=(r.get('AwayTeam') or '').strip()
                    if not d or not h or not a:continue
                    z={'date':d,'home':h,'away':a,'FTHG':f(r.get('FTHG')),'FTAG':f(r.get('FTAG')),'referee':(r.get('Referee') or '').strip()}
                    for fam,(hc,ac) in EVENT.items():z[fam]=(f(r.get(hc)),f(r.get(ac)))
                    arr.append(z);n+=1
                audit.append({'league':league,'season':sy,'status':'loaded','rows':n,'url':url})
            except Exception as e:audit.append({'league':league,'season':sy,'status':'failed','rows':0,'url':url,'error':str(e)[:160]})
        out[league]=sorted(arr,key=lambda r:(r['date'],key(r['home']),key(r['away'])))
    return out,audit
def fdmatch(h,a,d,rows):
    kh,ka=key(h),key(a);x=[r for r in rows if r['date']==d and key(r['home'])==kh and key(r['away'])==ka]
    if x:return x[0]
    best=None
    for r in [r for r in rows if r['date']==d]:
        A,B=set(kh.split()),set(key(r['home']).split());C,D=set(ka.split()),set(key(r['away']).split());score=(len(A&B)/max(1,len(A|B))+len(C&D)/max(1,len(C|D)))/2
        if best is None or score>best[0]:best=(score,r)
    return best[1] if best and best[0]>=.45 else None

def table(prior,h,a):
    pts=defaultdict(float);gp=defaultdict(int)
    for r in prior:
        H,A=key(r['home']),key(r['away']);hg,ag=r.get('FTHG'),r.get('FTAG')
        if hg is None or ag is None:continue
        gp[H]+=1;gp[A]+=1
        if hg>ag:pts[H]+=3
        elif hg<ag:pts[A]+=3
        else:pts[H]+=1;pts[A]+=1
    teams=sorted(set(gp),key=lambda t:(pts[t],pts[t]/max(1,gp[t])),reverse=True);rank={t:i+1 for i,t in enumerate(teams)};leader=pts[teams[0]] if teams else 0;rel=pts[teams[max(0,len(teams)-3)]] if teams else 0
    def S(n):k=key(n);return {'rank':rank.get(k),'points':pts.get(k,0),'games':gp.get(k,0),'ppg':pts.get(k,0)/max(1,gp.get(k,0)),'leaderGap':leader-pts.get(k,0),'relegationLineGap':pts.get(k,0)-rel}
    return {'home':S(h),'away':S(a),'teamsN':len(teams)}
def load(prior,team,target):
    k=key(team);ds=sorted(r['date'] for r in prior if key(r['home'])==k or key(r['away'])==k)
    if not ds:return {'known':False}
    recent=[d for d in ds if 0<(target-d).days<=21];short=sum((recent[i]-recent[i-1]).days<=4 for i in range(1,len(recent)))
    return {'known':True,'restDays':(target-ds[-1]).days,'matches7':sum(0<(target-d).days<=7 for d in ds),'matches14':sum(0<(target-d).days<=14 for d in ds),'matches21':len(recent),'shortTurnarounds21':short}
def refstate(prior,ref):
    if not ref:return {'known':False}
    allc=[];rc=[]
    for r in prior:
        y=r.get('yellowCards')
        if y and y[0] is not None and y[1] is not None:
            z=y[0]+y[1];allc.append(z)
            if key(r.get('referee',''))==key(ref):rc.append(z)
    if not allc:return {'known':False}
    lm=sum(allc)/len(allc);n=len(rc);m=sum(rc)/n if n else lm;shr=(m*n+lm*12)/(n+12)
    return {'known':bool(n),'name':ref,'priorMatches':n,'yellowCardsMean':m if n else None,'leagueYellowCardsMean':lm,'shrunkYellowCardsMean':shr,'uplift':shr-lm}
def events(prior,h,a):
    out={};hk,ak=key(h),key(a)
    for fam in EVENT:
        hf=[];ha=[];af=[];aa=[];lh=[];la=[]
        for r in prior:
            p=r.get(fam)
            if not p or p[0] is None or p[1] is None:continue
            hv,av=p;lh.append(hv);la.append(av)
            if key(r['home'])==hk:hf.append(hv);ha.append(av)
            if key(r['away'])==ak:af.append(av);aa.append(hv)
        ph=sum(lh)/len(lh) if lh else None;pa=sum(la)/len(la) if la else None;H,A=ew(hf,.94,30),ew(af,.94,30);AA,HA=ew(aa,.94,30),ew(ha,.94,30)
        hm=.5*H+.5*AA if H is not None and AA is not None else ph;am=.5*A+.5*HA if A is not None and HA is not None else pa
        out[fam]={'home':hm,'away':am,'total':hm+am if hm is not None and am is not None else None,'homeHistoryN':len(hf),'awayHistoryN':len(af)}
    return out

def profile(teams,league,team,target):
    hist=[x for x in teams.get(f'{league}|{key(team)}',[]) if x['date']<target]
    def M(k):return ew([x.get(k) for x in hist if x.get(k) is not None],.86,10)
    ng,nga,scd,mis=M('npxG'),M('npxGA'),M('scored'),M('missed')
    return {'n':len(hist),'npxG':ng,'npxGA':nga,'deep':M('deep'),'deepAllowed':M('deep_allowed'),'ppda':M('ppda'),'ppdaAllowed':M('ppda_allowed'),'finishingResidual':scd-ng if scd is not None and ng is not None else None,'shotStoppingResidual':nga-mis if nga is not None and mis is not None else None}
def prior_matches(matches,league,team,target,n=6):
    k=key(team);return [r for r in matches if r['league']==league and r['date']<target and (key(r['home'])==k or key(r['away'])==k)][-n:]
def setpieces(matches,league,team,target,cache):
    k=key(team);own=[];opp=[]
    for r in prior_matches(matches,league,team,target):
        raw=usmatch(r['id'],cache)
        if not raw:continue
        side='h' if key(r['home'])==k else 'a';other='a' if side=='h' else 'h';own.append(shot_summary(raw,side));opp.append(shot_summary(raw,other))
    def A(arr,k):return sum(x[k] for x in arr)/len(arr) if arr else None
    return {'n':len(own),'setPieceXGFor':A(own,'setPieceXG'),'setPieceXGAgainst':A(opp,'setPieceXG'),'cornerXGFor':A(own,'cornerXG'),'cornerXGAgainst':A(opp,'cornerXG'),'directFKXGFor':A(own,'directFKXG'),'openPlayXGFor':A(own,'openPlayXG')}

def main():
    OUT.mkdir(parents=True,exist_ok=True);cache=readcache();matches,teams,seeds=load_us();fd,audit=load_fd();raws={}
    def one(r):return r['id'],usmatch(r['id'],cache)
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        for i,(mid,raw) in enumerate(ex.map(one,matches)):
            if raw:raws[mid]=raw
            if i and i%200==0:print('match payloads',i,'/',len(matches),flush=True)
    players={l:defaultdict(dict) for l in UNDERSTAT};gks={l:defaultdict(lambda:{'n':0,'residual':0.0}) for l in UNDERSTAT};subs={l:defaultdict(lambda:{'n':0,'subMinutes':0.0,'subN':0,'subXG':0.0,'teamXG':0.0}) for l in UNDERSTAT};rows=[]
    for i,r in enumerate(matches):
        league=r['league'];target=date(r['date']);raw=raws.get(r['id']) or {};allprior=[x for x in fd.get(league,[]) if target and x['date']<target];seasonprior=[x for x in allprior if x['date']>=dt.date(SEASON,7,1)];fm=fdmatch(r['home'],r['away'],target,fd.get(league,[])) if target else None
        hp,ap=profile(teams,league,r['home'],r['date']),profile(teams,league,r['away'],r['date']);hs,aset=setpieces(matches,league,r['home'],r['date'],cache),setpieces(matches,league,r['away'],r['date'],cache)
        hr,ar=roster(raw,'h'),roster(raw,'a');hsh,ash=shape(hr),shape(ar);hi,ai=xi_impact(hr,players[league],seeds[league]),xi_impact(ar,players[league],seeds[league]);hg=gks[league].get(hi.get('goalkeeperId')) if hi.get('goalkeeperId') else None;ag=gks[league].get(ai.get('goalkeeperId')) if ai.get('goalkeeperId') else None;hb,ab=subs[league][key(r['home'])],subs[league][key(r['away'])];hw,aw=load(allprior,r['home'],target),load(allprior,r['away'],target)
        feat={'tactical':{'home':hp,'away':ap,'npxGAttackDiff':dif(hp.get('npxG'),ap.get('npxG')),'npxGADefenceDiff':dif(ap.get('npxGA'),hp.get('npxGA')),'deepAttackDiff':dif(hp.get('deep'),ap.get('deep')),'deepAllowedDefenceDiff':dif(ap.get('deepAllowed'),hp.get('deepAllowed')),'ppdaDiff':dif(hp.get('ppda'),ap.get('ppda')),'ppdaAllowedDiff':dif(hp.get('ppdaAllowed'),ap.get('ppdaAllowed')),'pressResistanceInteraction':hp['ppdaAllowed']-ap['ppda'] if hp.get('ppdaAllowed') is not None and ap.get('ppda') is not None else None},'shotStoppingGoalkeeper':{'homeTeamResidual':hp.get('shotStoppingResidual'),'awayTeamResidual':ap.get('shotStoppingResidual'),'homeGoalkeeperId':hi.get('goalkeeperId'),'awayGoalkeeperId':ai.get('goalkeeperId'),'homeGoalkeeperPriorN':(hg or {}).get('n',0),'awayGoalkeeperPriorN':(ag or {}).get('n',0),'homeGoalkeeperResidual':((hg or {}).get('residual',0)/(hg or {}).get('n',1) if (hg or {}).get('n',0) else None),'awayGoalkeeperResidual':((ag or {}).get('residual',0)/(ag or {}).get('n',1) if (ag or {}).get('n',0) else None)},'setPieces':{'home':hs,'away':aset,'setPieceBalanceDiff':dif(dif(hs.get('setPieceXGFor'),hs.get('setPieceXGAgainst')),dif(aset.get('setPieceXGFor'),aset.get('setPieceXGAgainst')))},'referee':refstate(allprior,(fm or {}).get('referee','')),'workload':{'home':hw,'away':aw,'restAdvDays':dif(hw.get('restDays'),aw.get('restDays')) if hw.get('known') and aw.get('known') else None,'load7Adv':dif(aw.get('matches7'),hw.get('matches7')) if hw.get('known') and aw.get('known') else None,'shortTurnAdv':dif(aw.get('shortTurnarounds21'),hw.get('shortTurnarounds21')) if hw.get('known') and aw.get('known') else None,'historicalScope':'league fixtures only'},'competitionState':table(seasonprior,r['home'],r['away']),'confirmedXI':{'homeShape':hsh,'awayShape':ash,'shapeAggressionDiff':dif(hsh.get('aggression'),ash.get('aggression')),'homeImpact':hi,'awayImpact':ai,'starterAttackIndexDiff':dif(hi.get('starterAttackIndex'),ai.get('starterAttackIndex')),'benchTop3AttackDiff':dif(hi.get('benchTop3AttackIndex'),ai.get('benchTop3AttackIndex')),'sourceKnown':bool(hsh.get('known',0)>=10 and ash.get('known',0)>=10)},'substitutionBehaviour':{'homePriorN':hb['n'],'awayPriorN':ab['n'],'homeAvgSubMinutes':hb['subMinutes']/hb['subN'] if hb['subN'] else None,'awayAvgSubMinutes':ab['subMinutes']/ab['subN'] if ab['subN'] else None,'homeSubXGShare':hb['subXG']/hb['teamXG'] if hb['teamXG'] else None,'awaySubXGShare':ab['subXG']/ab['teamXG'] if ab['teamXG'] else None},'eventExpectations':events(allprior,r['home'],r['away']),'weatherVenue':{'historicalForecastAvailable':False,'promotionEligible':False,'reason':'no point-in-time archived forecast source used; actual/reanalysis weather excluded'},'manager':{'historicalPointInTimeAvailable':False,'promotionEligible':False}}
        rows.append({'fixtureKey':f"{r['date']}|{league}|{key(r['home'])}|{key(r['away'])}",'date':r['date'],'league':league,'home':r['home'],'away':r['away'],'understatId':r['id'],'referee':(fm or {}).get('referee') or None,'features':feat})
        opph=sum(f(q.get('xG')) or 0 for q in shots(raw,'a'));oppa=sum(f(q.get('xG')) or 0 for q in shots(raw,'h'));gh=sum(str(q.get('result') or '')=='Goal' for q in shots(raw,'a'));ga=sum(str(q.get('result') or '')=='Goal' for q in shots(raw,'h'))
        if hi.get('goalkeeperId'):z=gks[league][hi['goalkeeperId']];z['n']+=1;z['residual']+=opph-gh
        if ai.get('goalkeeperId'):z=gks[league][ai['goalkeeperId']];z['n']+=1;z['residual']+=oppa-ga
        for tm,rr in ((r['home'],hr),(r['away'],ar)):
            z=subs[league][key(tm)];z['n']+=1
            for q in rr:
                if q['position'].upper()=='SUB' and q['time']>0:z['subN']+=1;z['subMinutes']+=q['time'];z['subXG']+=q['xG']
                z['teamXG']+=q['xG']
        update_players(hr,players[league]);update_players(ar,players[league])
        if i and i%250==0:print('feature snapshots',i,'/',len(matches),flush=True)
    payload={'schemaVersion':'HBT-MATCH-INTEL-HIST-1','version':VERSION,'generatedAt':now(),'season':SEASON,'policy':{'bookmakerOddsUsed':False,'targetOutcomeStatsUsedAsFeatures':False,'targetConfirmedXIIdentityAllowed':True,'weatherActualOrReanalysisUsed':False,'managerHindsightUsed':False,'failedStandaloneFamiliesRetainedForInteraction':True},'coverage':{'rows':len(rows),'confirmedXIRows':sum(bool(x['features']['confirmedXI']['sourceKnown']) for x in rows),'refereeKnown':sum(bool(x['features']['referee'].get('known')) for x in rows),'setPieceHomeN3':sum((x['features']['setPieces']['home'].get('n') or 0)>=3 for x in rows)},'sourceAudit':audit,'rows':rows}
    write(OUTPUT,payload);write(CACHE,cache);print(payload['coverage']);return 0 if len(rows)>1700 else 2
if __name__=='__main__':raise SystemExit(main())
