#!/usr/bin/env python3
"""HBT-1.4 live match-intelligence collector.

Runs the validated HBT-1.3 collectors first, then adds a single match-intelligence
snapshot. This file does NOT use bookmaker odds. It preserves missing values as
unknown and distinguishes PRE_XI_PROVISIONAL from CONFIRMED_XI_READY.

Weather is a live pre-kickoff forecast/context source only until a causal historical
forecast archive exists. Formation/travel/manager remain collected even where their
standalone historical promotion failed, so full-stack interaction tests can retain them.
"""
from __future__ import annotations
import csv, datetime as dt, io, json, math, re, time, unicodedata, urllib.parse, urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

import hbt_collect_market_intelligence_v4_final as hbt13
import hbt_collect_players_espn as espn

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'hbt_live_data'
MARKET=OUT/'market_intelligence.json'; PREXI=OUT/'pre_xi_context.json'; PLAYERS=OUT/'player_features.json'; OUTPUT=OUT/'hbt_1_4_match_intelligence.json'; CACHE=OUT/'_hbt_1_4_live_cache.json'
VERSION='HBT-1.4R-MATCH-INTELLIGENCE-LIVE'
LEAGUES={'en.1':('EPL','eng.1','E0'),'es.1':('La_liga','esp.1','SP1'),'de.1':('Bundesliga','ger.1','D1'),'it.1':('Serie_A','ita.1','I1'),'fr.1':('Ligue_1','fra.1','F1')}
UA='Mozilla/5.0 (compatible; HBT-1.4-Live/1.0)'

def now():return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def f(x):
    try:return None if x is None or str(x).strip()=='' else float(x)
    except:return None
def parse_dt(x):
    try:return dt.datetime.fromisoformat(str(x or '').replace('Z','+00:00'))
    except:return None
def key(s):
    s=unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode().lower().replace('&',' and ')
    generic={'fc','cf','afc','ac','ssc','sc','rc','sd','cd','ud','acf','ogc','osc','hsc','sco','ea','fsv','tsg','bsc','uc','us','ss','as','sv','vfb','vfl','club','clube','football','futbol','fussball','calcio','societa','sportiva','de','do','del','the','stade','olympique','girondins'}
    k=' '.join(t for t in re.sub(r'[^a-z0-9]+',' ',s).split() if t not in generic and not t.isdigit())
    aliases={'internazionale milano':'inter','internazionale':'inter','inter milan':'inter','paris saint germain':'psg','paris sg':'psg','lyonnais':'lyon','rennais':'rennes','strasbourg alsace':'strasbourg','deportivo alaves':'alaves','borussia monchengladbach':'monchengladbach','m gladbach':'monchengladbach','bayern munich':'bayern','bayern munchen':'bayern','tottenham hotspur':'tottenham','wolverhampton wanderers':'wolves','leicester city':'leicester','manchester united':'man united','manchester city':'man city','newcastle united':'newcastle','west ham united':'west ham','brighton and hove albion':'brighton','real betis balompie':'betis','real betis':'betis','hellas verona':'verona','chievo verona':'chievo','koln':'cologne','rasenballsport leipzig':'leipzig','rb leipzig':'leipzig','1899 hoffenheim':'hoffenheim'}
    return aliases.get(k,k)
def read(p,default):
    try:return json.load(open(p,encoding='utf-8'))
    except:return default
def write(p,x):espn.write_json(p,x)
def ew(vals,decay=.86,n=10):
    vals=[float(x) for x in vals if x is not None][-n:]
    if not vals:return None
    a=b=0.0
    for i,x in enumerate(vals):w=decay**(len(vals)-1-i);a+=w*x;b+=w
    return a/b if b else None
def dif(a,b):return a-b if a is not None and b is not None else None
def http(url,timeout=20):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json,text/csv,*/*'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return r.read()
def cache_read():return read(CACHE,{'understatMatches':{},'weather':{},'geocode':{}})

def us_pack(name,year):return espn.http_json(f'https://understat.com/getLeagueData/{name}/{year}',30,3)
def us_match(mid,cache):
    old=cache.setdefault('understatMatches',{}).get(str(mid))
    if isinstance(old,dict):return old
    try:r=espn.http_json(f'https://understat.com/getMatchData/{mid}',20,2);cache['understatMatches'][str(mid)]=r;return r
    except:return None
def ppda(x):
    if isinstance(x,dict):
        a,d=f(x.get('att')),f(x.get('def'));return a/d if a is not None and d not in (None,0) else None
    return f(x)
def team_hist(pack):
    out={}
    teams=pack.get('teams') or {};vals=teams.values() if isinstance(teams,dict) else teams
    for t in vals:
        title=str((t or {}).get('title') or '');rows=[]
        for x in (t or {}).get('history') or []:
            day=str(x.get('date') or '')[:10]
            if day:rows.append({'date':day,'npxG':f(x.get('npxG')),'npxGA':f(x.get('npxGA')),'deep':f(x.get('deep')),'deepAllowed':f(x.get('deep_allowed')),'ppda':ppda(x.get('ppda')),'ppdaAllowed':ppda(x.get('ppda_allowed')),'scored':f(x.get('scored')),'missed':f(x.get('missed'))})
        if title:out[key(title)]=rows
    return out
def team_profile(rows,kickoff):
    day=kickoff.date().isoformat() if kickoff else '9999-12-31';h=[x for x in rows if x['date']<day]
    def M(k):return ew([x[k] for x in h if x.get(k) is not None])
    ng,nga,sc,mi=M('npxG'),M('npxGA'),M('scored'),M('missed')
    return {'n':len(h),'npxG':ng,'npxGA':nga,'deep':M('deep'),'deepAllowed':M('deepAllowed'),'ppda':M('ppda'),'ppdaAllowed':M('ppdaAllowed'),'finishingResidual':sc-ng if sc is not None and ng is not None else None,'shotStoppingResidual':nga-mi if nga is not None and mi is not None else None}
def match_list(pack):
    out=[]
    for r in pack.get('dates') or []:
        h=r.get('h') or {};a=r.get('a') or {};day=str(r.get('datetime') or r.get('date') or '')[:10]
        if r.get('isResult') and r.get('id') and day:out.append({'id':str(r['id']),'date':day,'home':h.get('title') or h.get('name') or '','away':a.get('title') or a.get('name') or ''})
    return sorted(out,key=lambda z:z['date'])
def shots(raw,side):return [x for x in ((raw.get('shots') or {}).get(side) or []) if isinstance(x,dict)]
def roster(raw,side):
    src=((raw.get('rosters') or {}).get(side)) or {};vals=src.values() if isinstance(src,dict) else src if isinstance(src,list) else []
    out=[]
    for q in vals:
        if not isinstance(q,dict):continue
        out.append({'id':str(q.get('player_id') or q.get('id') or ''),'name':str(q.get('player') or q.get('player_name') or q.get('name') or ''),'position':str(q.get('position') or ''),'time':f(q.get('time')) or 0,'xG':f(q.get('xG')) or 0,'xA':f(q.get('xA')) or 0,'shots':f(q.get('shots')) or 0,'key_passes':f(q.get('key_passes')) or 0})
    return out
def shot_summary(raw,side):
    rr=shots(raw,side)
    def S(names):return sum(f(q.get('xG')) or 0 for q in rr if str(q.get('situation') or '') in names)
    return {'setPieceXG':S({'FromCorner','SetPiece','DirectFreekick'}),'cornerXG':S({'FromCorner'}),'directFKXG':S({'DirectFreekick'}),'openPlayXG':S({'OpenPlay'})}
def prior_matches(rows,team,kickoff,n=6):
    k=key(team);day=kickoff.date().isoformat() if kickoff else '9999-12-31';return [r for r in rows if r['date']<day and (key(r['home'])==k or key(r['away'])==k)][-n:]
def detailed_context(rows,team,kickoff,cache,current_gk_name=None):
    k=key(team);own=[];opp=[];submins=[];subxg=txg=0.0;gkr=[]
    for r in prior_matches(rows,team,kickoff,8):
        raw=us_match(r['id'],cache)
        if not raw:continue
        side='h' if key(r['home'])==k else 'a';other='a' if side=='h' else 'h';own.append(shot_summary(raw,side));opp.append(shot_summary(raw,other));rr=roster(raw,side)
        for q in rr:
            txg+=q['xG']
            if q['position'].upper()=='SUB' and q['time']>0:submins.append(q['time']);subxg+=q['xG']
        if current_gk_name:
            starter=next((q for q in rr if q['position'].upper()!='SUB' and ('GK' in q['position'].upper() or 'GOAL' in q['position'].upper())),None)
            if starter and key(starter['name'])==key(current_gk_name):
                oxg=sum(f(q.get('xG')) or 0 for q in shots(raw,other));goals=sum(str(q.get('result') or '')=='Goal' for q in shots(raw,other));gkr.append(oxg-goals)
    def A(arr,n):return sum(x[n] for x in arr)/len(arr) if arr else None
    return {'priorMatchN':len(own),'setPieceXGFor':A(own,'setPieceXG'),'setPieceXGAgainst':A(opp,'setPieceXG'),'cornerXGFor':A(own,'cornerXG'),'cornerXGAgainst':A(opp,'cornerXG'),'directFKXGFor':A(own,'directFKXG'),'avgSubMinutes':sum(submins)/len(submins) if submins else None,'subXGShare':subxg/txg if txg else None,'goalkeeperPriorN':len(gkr),'goalkeeperResidual':sum(gkr)/len(gkr) if gkr else None}

def player_maps(pack,prev):
    def build(raw):
        z={}
        for q in raw.get('players') or []:
            nm=str(q.get('player_name') or q.get('player') or q.get('name') or '');mins=f(q.get('time')) or 0
            if nm and mins>0:z[key(nm)]={'name':nm,'minutes':mins,'shot90':90*(f(q.get('shots')) or 0)/mins,'xg90':90*(f(q.get('xG')) or 0)/mins,'xa90':90*(f(q.get('xA')) or 0)/mins,'kp90':90*(f(q.get('key_passes')) or 0)/mins}
        return z
    return build(pack),build(prev)
def attack_index(names,cur,prev):
    vals=[];matched=[]
    for name in names:
        z=cur.get(key(name));old=prev.get(key(name))
        if z and z['minutes']>=180:use=z
        elif z and old:
            w=z['minutes']/(z['minutes']+720);use={k:(w*z[k]+(1-w)*old[k]) for k in ('shot90','xg90','xa90','kp90')}
        else:use=z or old
        if use:
            vals.append(use['xg90']+.55*use['xa90']+.08*use['shot90']+.03*use['kp90']);matched.append(name)
    return {'value':sum(vals) if vals else None,'matchedN':len(vals),'names':matched}

def fd_code(y):return f'{y%100:02d}{(y+1)%100:02d}'
def fd_rows(div,year):
    out=[]
    for sy in (year-1,year):
        try:
            raw=csv.DictReader(io.StringIO(http(f'https://www.football-data.co.uk/mmz4281/{fd_code(sy)}/{div}.csv').decode('utf-8-sig','replace')))
            for r in raw:
                try:d=dt.datetime.strptime((r.get('Date') or ''),'%d/%m/%Y').date()
                except:
                    try:d=dt.datetime.strptime((r.get('Date') or ''),'%d/%m/%y').date()
                    except:continue
                h,a=(r.get('HomeTeam') or '').strip(),(r.get('AwayTeam') or '').strip();hg,ag=f(r.get('FTHG')),f(r.get('FTAG'))
                if h and a:out.append({'date':d,'home':h,'away':a,'hg':hg,'ag':ag,'referee':(r.get('Referee') or '').strip(),'yc':(f(r.get('HY')),f(r.get('AY')))})
        except:pass
    return sorted(out,key=lambda r:r['date'])
def table_state(rows,target,h,a,year):
    prior=[r for r in rows if r['date']<target.date() and r['date']>=dt.date(year,7,1)];pts=defaultdict(float);gp=defaultdict(int)
    for r in prior:
        if r['hg'] is None or r['ag'] is None:continue
        H,A=key(r['home']),key(r['away']);gp[H]+=1;gp[A]+=1
        if r['hg']>r['ag']:pts[H]+=3
        elif r['hg']<r['ag']:pts[A]+=3
        else:pts[H]+=1;pts[A]+=1
    teams=sorted(set(gp),key=lambda t:(pts[t],pts[t]/max(1,gp[t])),reverse=True);rank={t:i+1 for i,t in enumerate(teams)};lead=pts[teams[0]] if teams else 0;rel=pts[teams[max(0,len(teams)-3)]] if teams else 0
    def S(n):k=key(n);return {'rank':rank.get(k),'points':pts.get(k,0),'games':gp.get(k,0),'ppg':pts.get(k,0)/max(1,gp.get(k,0)),'leaderGap':lead-pts.get(k,0),'relegationLineGap':pts.get(k,0)-rel}
    return {'home':S(h),'away':S(a),'teamsN':len(teams)}
def ref_state(rows,target,ref):
    if not ref:return {'known':False,'reason':'assigned referee unavailable'}
    prior=[r for r in rows if r['date']<target.date()];allc=[];mine=[]
    for r in prior:
        y=r['yc']
        if y[0] is not None and y[1] is not None:
            z=y[0]+y[1];allc.append(z)
            if key(r['referee'])==key(ref):mine.append(z)
    if not allc:return {'known':False,'name':ref,'reason':'historical card source unavailable'}
    lm=sum(allc)/len(allc);n=len(mine);m=sum(mine)/n if n else lm;shr=(m*n+lm*12)/(n+12)
    return {'known':bool(n),'name':ref,'priorMatches':n,'yellowCardsMean':m if n else None,'leagueYellowCardsMean':lm,'shrunkYellowCardsMean':shr,'uplift':shr-lm}

def geocode(city,country,cache):
    if not city:return None
    ck=f'{city}|{country or ""}';old=cache.setdefault('geocode',{}).get(ck)
    if old:return old
    try:
        q=urllib.parse.urlencode({'name':city,'count':10,'language':'en','format':'json'});raw=json.loads(http('https://geocoding-api.open-meteo.com/v1/search?'+q).decode());cand=raw.get('results') or []
        if country:
            c=next((x for x in cand if str(x.get('country') or '').lower()==str(country).lower()),None) or (cand[0] if cand else None)
        else:c=cand[0] if cand else None
        if c:old={'lat':c.get('latitude'),'lon':c.get('longitude'),'elevationM':c.get('elevation'),'resolvedName':c.get('name'),'country':c.get('country')};cache['geocode'][ck]=old;return old
    except:return None
    return None
def weather(venue,kickoff,cache):
    if not venue or not kickoff:return {'available':False,'reason':'venue/kickoff unavailable'}
    if kickoff < dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=30):return {'available':False,'reason':'kickoff already passed; live forecast not backfilled with actual weather'}
    geo=geocode(venue.get('city'),venue.get('country'),cache)
    if not geo or geo.get('lat') is None:return {'available':False,'reason':'venue city geocode unavailable'}
    ck=f"{geo['lat']:.4f}|{geo['lon']:.4f}|{kickoff.isoformat()[:13]}";old=cache.setdefault('weather',{}).get(ck)
    if old and time.time()-old.get('cachedAt',0)<1800:return old['data']
    try:
        q=urllib.parse.urlencode({'latitude':geo['lat'],'longitude':geo['lon'],'hourly':'temperature_2m,precipitation_probability,precipitation,wind_speed_10m,wind_gusts_10m,weather_code','timezone':'UTC','forecast_days':7});raw=json.loads(http('https://api.open-meteo.com/v1/forecast?'+q).decode());hour=kickoff.replace(minute=0,second=0,microsecond=0).isoformat(timespec='minutes').replace('+00:00','');times=(raw.get('hourly') or {}).get('time') or []
        ix=min(range(len(times)),key=lambda i:abs((dt.datetime.fromisoformat(times[i]).replace(tzinfo=dt.timezone.utc)-kickoff).total_seconds())) if times else None
        if ix is None:return {'available':False,'reason':'forecast hour unavailable'}
        H=raw['hourly'];data={'available':True,'source':'Open-Meteo forecast','forecastIssuedAt':now(),'venueCity':venue.get('city'),'elevationM':geo.get('elevationM'),'temperatureC':H['temperature_2m'][ix],'precipitationProbability':H['precipitation_probability'][ix],'precipitationMm':H['precipitation'][ix],'windKmh':H['wind_speed_10m'][ix],'gustKmh':H['wind_gusts_10m'][ix],'weatherCode':H['weather_code'][ix],'promotionEligible':False,'reason':'live forecast retained; no causal historical forecast archive yet'};cache['weather'][ck]={'cachedAt':time.time(),'data':data};return data
    except Exception as e:return {'available':False,'reason':'forecast fetch failed: '+str(e)[:120]}

def lookup(rows,date_s,home,away):
    if not isinstance(rows,dict):return None
    kdate=str(date_s or '')[:10];hk,ak=key(home),key(away)
    for r in rows.values():
        if str(r.get('kickoff') or r.get('date') or '')[:10]==kdate and key(r.get('home'))==hk and key(r.get('away'))==ak:return r
    return None

def main():
    rc=hbt13.main();market=read(MARKET,{});pre=read(PREXI,{});pf=read(PLAYERS,{});cache=cache_read();year=int(market.get('seasonStartYear') or dt.datetime.now().year);packs={};prevpacks={};fd={}
    for league,(us,_,div) in LEAGUES.items():
        try:packs[league]=us_pack(us,year);prevpacks[league]=us_pack(us,year-1)
        except:packs[league]={};prevpacks[league]={}
        fd[league]=fd_rows(div,year)
    out={};health=defaultdict(int);espn_cache=espn.read_cache()
    for fid,row in (market.get('fixtures') or {}).items():
        league=row.get('league');kick=parse_dt(row.get('kickoff'));home,away=row.get('home'),row.get('away');pack=packs.get(league) or {};hist=team_hist(pack);matches=match_list(pack);cur,old=player_maps(pack,prevpacks.get(league) or {})
        pctx=lookup(pre.get('fixtures') or {},row.get('kickoff'),home,away);prow=lookup(pf.get('features') or {},row.get('kickoff'),home,away)
        event={'id':str(row.get('eventId') or ''),'date':row.get('kickoff'),'league':league,'espnLeague':LEAGUES.get(league,('', '', ''))[1],'homeId':str((row.get('homeDetail') or {}).get('teamId') or ''),'awayId':str((row.get('awayDetail') or {}).get('teamId') or ''),'home':home,'away':away}
        summary=espn.get_summary(event,espn_cache,force=True) if event['id'] and event['espnLeague'] else None;confirmed=bool(summary and summary.get('confirmed'));hstart=[x['name'] for x in (summary or {}).get('home',[]) if x.get('status')=='starting'];astart=[x['name'] for x in (summary or {}).get('away',[]) if x.get('status')=='starting'];hbench=[x['name'] for x in (summary or {}).get('home',[]) if x.get('status')!='starting'];abench=[x['name'] for x in (summary or {}).get('away',[]) if x.get('status')!='starting']
        hsnap=((pctx or {}).get('homeDetail') or {}).get('snapshot') or {};asnap=((pctx or {}).get('awayDetail') or {}).get('snapshot') or {};hxi=hstart if confirmed else hsnap.get('expectedXI') or [];axi=astart if confirmed else asnap.get('expectedXI') or []
        hgk=next((x['name'] for x in (summary or {}).get('home',[]) if x.get('status')=='starting' and x.get('pos')=='GK'),None);agk=next((x['name'] for x in (summary or {}).get('away',[]) if x.get('status')=='starting' and x.get('pos')=='GK'),None)
        hp,ap=team_profile(hist.get(key(home),[]),kick),team_profile(hist.get(key(away),[]),kick);hd,ad=detailed_context(matches,home,kick,cache,hgk),detailed_context(matches,away,kick,cache,agk);hi,ai=attack_index(hxi,cur,old),attack_index(axi,cur,old);hb,ab=attack_index(hbench,cur,old),attack_index(abench,cur,old)
        table=table_state(fd.get(league,[]),kick,home,away,year) if kick else {};ref=ref_state(fd.get(league,[]),kick,row.get('referee')) if kick else {'known':False};w=weather(row.get('venue'),kick,cache);travel={'home':((row.get('homeDetail') or {}).get('travel')),'away':((row.get('awayDetail') or {}).get('travel'))};work=((pctx or {}).get('extendedContext') or {}).get('workload');manager=((pctx or {}).get('extendedContext') or {}).get('manager');availability=(pctx or {}).get('features')
        state='CONFIRMED_XI_READY' if confirmed else 'PRE_XI_PROVISIONAL';health[state]+=1
        out[fid]={'eventId':row.get('eventId'),'league':league,'home':home,'away':away,'kickoff':row.get('kickoff'),'readinessState':state,'officialXI':{'confirmed':confirmed,'homeStarters':hstart,'awayStarters':astart,'homeBench':hbench,'awayBench':abench,'source':'ESPN summary'},'availabilityContinuity':{'features':availability,'sourceState':(pctx or {}).get('intelligenceReadiness'),'featureReadiness':(pctx or {}).get('featureReadiness')},'tactical':{'home':hp,'away':ap,'npxGAttackDiff':dif(hp.get('npxG'),ap.get('npxG')),'npxGADefenceDiff':dif(ap.get('npxGA'),hp.get('npxGA')),'deepAttackDiff':dif(hp.get('deep'),ap.get('deep')),'deepAllowedDefenceDiff':dif(ap.get('deepAllowed'),hp.get('deepAllowed')),'ppdaDiff':dif(hp.get('ppda'),ap.get('ppda')),'ppdaAllowedDiff':dif(hp.get('ppdaAllowed'),ap.get('ppdaAllowed'))},'playerTeamImpact':{'mode':'CONFIRMED_XI' if confirmed else 'EXPECTED_XI','homeStarterAttack':hi,'awayStarterAttack':ai,'starterAttackIndexDiff':dif(hi.get('value'),ai.get('value')),'homeBenchAttack':hb if confirmed else None,'awayBenchAttack':ab if confirmed else None,'benchAttackIndexDiff':dif(hb.get('value'),ab.get('value')) if confirmed else None},'shotStoppingGoalkeeper':{'homeTeamResidual':hp.get('shotStoppingResidual'),'awayTeamResidual':ap.get('shotStoppingResidual'),'homeGoalkeeper':hgk,'awayGoalkeeper':agk,'homeGoalkeeperPriorN':hd.get('goalkeeperPriorN'),'awayGoalkeeperPriorN':ad.get('goalkeeperPriorN'),'homeGoalkeeperResidual':hd.get('goalkeeperResidual'),'awayGoalkeeperResidual':ad.get('goalkeeperResidual')},'setPieces':{'home':hd,'away':ad,'setPieceBalanceDiff':dif(dif(hd.get('setPieceXGFor'),hd.get('setPieceXGAgainst')),dif(ad.get('setPieceXGFor'),ad.get('setPieceXGAgainst')))},'referee':ref,'weatherVenue':w,'workload':work,'travel':travel,'competitionState':table,'manager':manager,'formation':{'home':((row.get('homeDetail') or {}).get('formation')),'away':((row.get('awayDetail') or {}).get('formation'))},'substitutionBehaviour':{'homeAvgSubMinutes':hd.get('avgSubMinutes'),'awayAvgSubMinutes':ad.get('avgSubMinutes'),'homeSubXGShare':hd.get('subXGShare'),'awaySubXGShare':ad.get('subXGShare')},'eventMarkets':row.get('eventMarkets'),'validatedEventFamilies':row.get('validatedEventFamilies'),'playerProps':{'actionGate':'CONFIRMED_XI only','marketRows':{'home':(row.get('homeDetail') or {}).get('players') if confirmed else [],'away':(row.get('awayDetail') or {}).get('players') if confirmed else []}},'policy':{'bookmakerOddsUsed':False,'weatherPredictiveWeight':0,'formationTravelRetainedForInteraction':True,'missingIsZero':False}}
    payload={'schemaVersion':'HBT-MATCH-INTEL-LIVE-1','version':VERSION,'generatedAt':now(),'sourcePredictiveModel':'HBT-1.1.2L-R1 frozen until HBT-1.4 challenger validation','policy':{'bookmakerOddsUsed':False,'allExistingHBT13OutputsPreserved':True,'expectedXI':'provisional','confirmedXI':'final rerun state','failedStandaloneFamiliesRetained':True,'missingIsZero':False},'health':dict(health),'fixtures':out};write(OUTPUT,payload);write(CACHE,cache);espn.write_json(espn.CACHE_PATH,espn_cache);print('HBT-1.4 live intelligence',payload['health']);return rc
if __name__=='__main__':raise SystemExit(main())
