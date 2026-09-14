#!/usr/bin/env python3
"""HBT L5 Big-Five historical value audit — research only.

Uses immutable frozen HBT OOS probabilities and historical Football-Data 2018/19
Bet365 1X2 prices. Odds never alter HBT probabilities.
"""
from __future__ import annotations
import base64, csv, gzip, io, json, math, random, re, unicodedata, urllib.request
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE_B64=ROOT/'research/l5/frozen_l1_2018_19_compact.json.gz.b64'
OUTDIR=ROOT/'research/l5/output'; OUTDIR.mkdir(parents=True,exist_ok=True)
LEAGUE_FILE={'en.1':'E0','es.1':'SP1','de.1':'D1','it.1':'I1','fr.1':'F1'}
URL=lambda code:f'https://www.football-data.co.uk/mmz4281/1819/{code}.csv'
Y_RESULT={0:'H',1:'D',2:'A'}
OUTCOMES=['H','D','A']

# Explicit canonical aliases only; no fuzzy guessing.
ALIASES={
# England
'manchester united':'man united','man united':'man united','manchester city':'man city','man city':'man city',
'newcastle united':'newcastle','newcastle':'newcastle','tottenham hotspur':'tottenham','tottenham':'tottenham',
'wolverhampton wanderers':'wolves','wolverhampton':'wolves','wolves':'wolves','afc bournemouth':'bournemouth','bournemouth':'bournemouth',
'brighton hove albion':'brighton','brighton':'brighton','west ham united':'west ham','west ham':'west ham',
'huddersfield town':'huddersfield','huddersfield':'huddersfield','leicester city':'leicester','leicester':'leicester',
'cardiff city':'cardiff','cardiff':'cardiff',
# Spain
'atletico madrid':'ath madrid','club atletico de madrid':'ath madrid','ath madrid':'ath madrid',
'athletic club':'ath bilbao','athletic bilbao':'ath bilbao','ath bilbao':'ath bilbao',
'real betis balompie':'betis','real betis':'betis','betis':'betis',
'real sociedad de futbol':'sociedad','real sociedad':'sociedad','sociedad':'sociedad',
'real club celta de vigo':'celta','rc celta de vigo':'celta','celta vigo':'celta','celta':'celta',
'deportivo alaves':'alaves','alaves':'alaves','sd eibar':'eibar','eibar':'eibar',
'girona fc':'girona','girona':'girona','sd huesca':'huesca','huesca':'huesca',
'cd leganes':'leganes','leganes':'leganes','levante ud':'levante','levante':'levante',
'rayo vallecano de madrid':'vallecano','rayo vallecano':'vallecano','vallecano':'vallecano',
'real valladolid':'valladolid','valladolid':'valladolid','rcd espanyol de barcelona':'espanol','espanyol':'espanol','espanol':'espanol',
'fc barcelona':'barcelona','barcelona':'barcelona','real madrid':'real madrid','real madrid club de futbol':'real madrid',
'villarreal':'villarreal','villarreal club de futbol':'villarreal','valencia':'valencia','valencia club de futbol':'valencia',
'sevilla':'sevilla','sevilla futbol club':'sevilla','getafe':'getafe','getafe club de futbol':'getafe',
# Germany
'borussia monchengladbach':'m gladbach','monchengladbach':'m gladbach','m gladbach':'m gladbach',
'bayern munchen':'bayern munich','bayern munich':'bayern munich','fc bayern munchen':'bayern munich',
'borussia dortmund':'dortmund','dortmund':'dortmund','rb leipzig':'rb leipzig',
'bayer 04 leverkusen':'leverkusen','bayer leverkusen':'leverkusen','leverkusen':'leverkusen',
'eintracht frankfurt':'ein frankfurt','ein frankfurt':'ein frankfurt',
'hertha bsc':'hertha','hertha berlin':'hertha','hertha':'hertha',
'1899 hoffenheim':'hoffenheim','tsg 1899 hoffenheim':'hoffenheim','hoffenheim':'hoffenheim',
'1 fc nurnberg':'nurnberg','nurnberg':'nurnberg','fortuna dusseldorf':'fortuna dusseldorf',
'hannover 96':'hannover','hannover':'hannover','sc freiburg':'freiburg','freiburg':'freiburg',
'fc augsburg':'augsburg','augsburg':'augsburg','vfb stuttgart':'stuttgart','stuttgart':'stuttgart',
'fc schalke 04':'schalke 04','schalke 04':'schalke 04','werder bremen':'werder bremen','mainz 05':'mainz','1 fsv mainz 05':'mainz',
'vfl wolfsburg':'wolfsburg','wolfsburg':'wolfsburg',
# Italy
'ac milan':'milan','milan':'milan','fc internazionale milano':'inter','inter milan':'inter','inter':'inter',
'juventus':'juventus','juventus turin':'juventus','ssc napoli':'napoli','napoli':'napoli',
'as roma':'roma','roma':'roma','ss lazio':'lazio','lazio':'lazio','acf fiorentina':'fiorentina','fiorentina':'fiorentina',
'atalanta bc':'atalanta','atalanta':'atalanta','torino':'torino','torino fc':'torino',
'uc sampdoria':'sampdoria','sampdoria':'sampdoria','genoa cfc':'genoa','genoa':'genoa',
'us sassuolo calcio':'sassuolo','sassuolo':'sassuolo','udinese calcio':'udinese','udinese':'udinese',
'cagliari calcio':'cagliari','cagliari':'cagliari','spal 2013':'spal','spal':'spal',
'bologna fc 1909':'bologna','bologna':'bologna','parma calcio 1913':'parma','parma':'parma',
'empoli fc':'empoli','empoli':'empoli','chievo verona':'chievo','chievo':'chievo',
'frosinone calcio':'frosinone','frosinone':'frosinone',
# France
'paris saint germain':'paris sg','paris saint germain fc':'paris sg','paris sg':'paris sg',
'olympique lyonnais':'lyon','lyon':'lyon','olympique de marseille':'marseille','marseille':'marseille',
'lille osc':'lille','lille':'lille','as monaco':'monaco','monaco':'monaco',
'as saint etienne':'st etienne','saint etienne':'st etienne','st etienne':'st etienne',
'ogc nice':'nice','nice':'nice','stade rennais':'rennes','stade rennais fc':'rennes','rennes':'rennes',
'montpellier hsc':'montpellier','montpellier':'montpellier','girondins bordeaux':'bordeaux','bordeaux':'bordeaux',
'fc nantes':'nantes','nantes':'nantes','rc strasbourg alsace':'strasbourg','strasbourg':'strasbourg',
'stade de reims':'reims','reims':'reims','nimes olympique':'nimes','nimes':'nimes',
'amiens sc':'amiens','amiens':'amiens','toulouse fc':'toulouse','toulouse':'toulouse',
'stade malherbe caen':'caen','sm caen':'caen','caen':'caen','dijon fco':'dijon','dijon':'dijon',
'angers sco':'angers','angers':'angers','ea guingamp':'guingamp','guingamp':'guingamp',
}

def key(s):
    s=unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().lower().replace('&',' ')
    s=re.sub(r'[^a-z0-9]+',' ',s).strip()
    toks=[t for t in s.split() if t not in {'fc','cf'}]
    s=' '.join(toks)
    return ALIASES.get(s,s)

def fd_date(v):
    parts=v.strip().split('/')
    if len(parts)!=3: return ''
    d,m,y=parts
    y=int(y); y=y+2000 if y<100 else y
    return f'{y:04d}-{int(m):02d}-{int(d):02d}'

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'HBT-L5-research/1.0'})
    with urllib.request.urlopen(req,timeout=30) as r:return r.read().decode('utf-8-sig',errors='replace')

def load_baseline():
    raw=base64.b64decode(BASE_B64.read_text().strip())
    return json.loads(gzip.decompress(raw).decode())

def load_odds():
    allrows={}; source_audit={}
    for league,code in LEAGUE_FILE.items():
        text=fetch(URL(code)); rows=list(csv.DictReader(io.StringIO(text)))
        accepted=0; missing_price=0
        for r in rows:
            if not r.get('Date') or not r.get('HomeTeam') or not r.get('AwayTeam'):continue
            try:o=[float(r['B365H']),float(r['B365D']),float(r['B365A'])]
            except (KeyError,TypeError,ValueError):missing_price+=1;continue
            if not all(math.isfinite(x) and x>1 for x in o):missing_price+=1;continue
            imp=[1/x for x in o]; z=sum(imp); q=[x/z for x in imp]
            k=(league,fd_date(r['Date']),key(r['HomeTeam']),key(r['AwayTeam']))
            allrows[k]={'league':league,'date':k[1],'home':r['HomeTeam'],'away':r['AwayTeam'],'o':o,'q':q,'ftr':r.get('FTR'),'overround':z-1}
            accepted+=1
        source_audit[league]={'url':URL(code),'csvRows':len(rows),'pricedRows':accepted,'missingPriceRows':missing_price}
    return allrows,source_audit

def join(base,odds):
    joined=[];missing=[];mismatch=[]
    for r in base:
        k=(r['l'],r['d'],key(r['h']),key(r['a']))
        o=odds.get(k)
        if not o:
            missing.append({'league':r['l'],'date':r['d'],'home':r['h'],'away':r['a'],'hk':key(r['h']),'ak':key(r['a'])});continue
        if o['ftr'] and o['ftr']!=Y_RESULT[int(r['y'])]:
            mismatch.append({'league':r['l'],'date':r['d'],'home':r['h'],'away':r['a'],'hbt':Y_RESULT[int(r['y'])],'source':o['ftr']})
        joined.append({'league':r['l'],'date':r['d'],'home':r['h'],'away':r['a'],'y':int(r['y']),'p':r['p'],**o})
    return joined,missing,mismatch

def metric(rows,fn):
    n=len(rows);ll=br=0.;acc=0
    for r in rows:
        p=fn(r);y=r['y'];ll-=math.log(max(1e-15,p[y]));br+=sum((p[i]-(1 if i==y else 0))**2 for i in range(3))/3;acc+=max(range(3),key=lambda i:p[i])==y
    return {'n':n,'logloss':ll/n if n else None,'brier':br/n if n else None,'accuracy':acc/n if n else None}

def pool(r,a):
    p,q=r['p'],r['q'];v=[(max(p[i],1e-15)**a)*(max(q[i],1e-15)**(1-a)) for i in range(3)];z=sum(v);return [x/z for x in v]

def value_policy(rows,fn,min_ev=.05):
    bets=[]
    for r in rows:
        p=fn(r);ev=[p[i]*r['o'][i]-1 for i in range(3)];idx=max(range(3),key=lambda i:ev[i])
        if ev[idx]<min_ev:continue
        profit=r['o'][idx]-1 if r['y']==idx else -1
        bets.append((r['date'],profit,r['y']==idx,r['o'][idx],ev[idx],idx,r['league']))
    n=len(bets);pr=sum(x[1] for x in bets)
    return {'bets':n,'wins':sum(x[2] for x in bets),'hitRate':sum(x[2] for x in bets)/n if n else None,'profitUnits':pr,'roi':pr/n if n else None,'avgOdds':sum(x[3] for x in bets)/n if n else None,'avgClaimedEV':sum(x[4] for x in bets)/n if n else None,'byLeague':{lg:{'bets':sum(1 for x in bets if x[6]==lg),'profitUnits':sum(x[1] for x in bets if x[6]==lg)} for lg in LEAGUE_FILE}}

def always_pick(rows):
    bets=[]
    for r in rows:
        i=max(range(3),key=lambda j:r['p'][j]);profit=r['o'][i]-1 if r['y']==i else -1;bets.append((profit,r['y']==i,r['league']))
    n=len(bets);pr=sum(x[0] for x in bets)
    return {'bets':n,'wins':sum(x[1] for x in bets),'hitRate':sum(x[1] for x in bets)/n if n else None,'profitUnits':pr,'roi':pr/n if n else None,'byLeague':{lg:{'bets':sum(1 for x in bets if x[2]==lg),'profitUnits':sum(x[0] for x in bets if x[2]==lg)} for lg in LEAGUE_FILE}}

def bootstrap_delta(rows,fa,fb,B=5000,seed=119):
    if not rows:return None
    by=defaultdict(list)
    for r in rows:
        pa,pb=fa(r),fb(r);y=r['y'];by[r['date']].append(-math.log(max(1e-15,pa[y]))+math.log(max(1e-15,pb[y])))
    blocks=list(by.values());obs=sum(map(sum,blocks))/sum(map(len,blocks));rng=random.Random(seed);vals=[]
    for _ in range(B):
        s=n=0
        for __ in range(len(blocks)):
            b=blocks[rng.randrange(len(blocks))];s+=sum(b);n+=len(b)
        vals.append(s/n)
    vals.sort();return {'deltaLogloss':obs,'ci95':[vals[int(.025*B)],vals[min(B-1,int(.975*B))]]}

def split(rows):
    return {'train':[r for r in rows if r['date']<'2019-01-01'],'validation':[r for r in rows if '2019-01-01'<=r['date']<'2019-03-01'],'final':[r for r in rows if r['date']>='2019-03-01']}

def main():
    base=load_baseline();odds,source=load_odds();joined,missing,mismatch=join(base,odds)
    coverage={'baseline':len(base),'joined':len(joined),'rate':len(joined)/len(base),'missing':len(missing),'mismatch':len(mismatch),'baselineByLeague':Counter(r['l'] for r in base),'joinedByLeague':Counter(r['league'] for r in joined)}
    if mismatch:raise SystemExit(f'Outcome mismatches: {mismatch[:5]}')
    if missing:
        # Fail loudly. Missing rows must be resolved rather than silently excluded.
        (OUTDIR/'hbt_l5_big5_missing.json').write_text(json.dumps(missing,indent=2,ensure_ascii=False)+'\n')
        print(json.dumps({'coverage':coverage,'sourceAudit':source,'missingFirst20':missing[:20]},indent=2,default=lambda x:dict(x)))
        raise SystemExit(f'Big-Five join incomplete: {len(missing)} rows')
    s=split(joined);grid=[i/20 for i in range(21)]
    train_grid=[]
    for a in grid:train_grid.append({'alphaHBT':a,**metric(s['train'],lambda r,a=a:pool(r,a))})
    train_grid.sort(key=lambda x:x['logloss']);alpha=train_grid[0]['alphaHBT'];blend=lambda r:pool(r,alpha)
    splits={}
    for name,rr in s.items():
        splits[name]={
          'n':len(rr),'hbt':metric(rr,lambda r:r['p']),'marketVigFree':metric(rr,lambda r:r['q']),'selectedBlend':metric(rr,blend),
          'hbtVsMarket':bootstrap_delta(rr,lambda r:r['p'],lambda r:r['q']),
          'rawHbt5pctValuePolicy':value_policy(rr,lambda r:r['p'],.05),'blend5pctValuePolicy':value_policy(rr,blend,.05),
          'alwaysBetHighestHbtProbability':always_pick(rr),
          'byLeague':{lg:{'n':len([r for r in rr if r['league']==lg]),'hbt':metric([r for r in rr if r['league']==lg],lambda r:r['p']),'marketVigFree':metric([r for r in rr if r['league']==lg],lambda r:r['q']),'hbtVsMarket':bootstrap_delta([r for r in rr if r['league']==lg],lambda r:r['p'],lambda r:r['q']),'rawHbt5pctValuePolicy':value_policy([r for r in rr if r['league']==lg],lambda r:r['p'],.05),'alwaysBetHighestHbtProbability':always_pick([r for r in rr if r['league']==lg])} for lg in LEAGUE_FILE}
        }
    result={'createdAt':datetime.now(timezone.utc).isoformat(),'researchOnly':True,'footballModelModified':False,'oddsFeedBackIntoProbability':False,'sourcePredictiveModel':'Frozen HBT-0.5P L1 OOS / HBT-1.1.2 parameter benchmark','oddsSource':{'provider':'Football-Data.co.uk','season':'2018/19','bookmaker':'Bet365','columns':['B365H','B365D','B365A'],'timingCaveat':'2018/19 pre-closing historical prices; no observation timestamp.'},'coverage':{**coverage,'baselineByLeague':dict(coverage['baselineByLeague']),'joinedByLeague':dict(coverage['joinedByLeague'])},'sourceAudit':source,'protocol':{'trainEnd':'2018-12-31','validation':'2019-01-01..2019-02-28','finalStart':'2019-03-01','primaryMinEV':.05,'flatStakeUnits':1,'oneBetMaxPerFixture':True,'accumulators':False},'blend':{'method':'geometric pool','alphaGrid':grid,'selectedAlphaHBTOnTrainOnly':alpha,'trainGrid':train_grid},'splits':splits}
    out=OUTDIR/'hbt_l5_big5_2018_19_value_audit.json';out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'coverage':result['coverage'],'selectedAlphaHBT':alpha,'final':splits['final'],'output':str(out)},indent=2,ensure_ascii=False))

if __name__=='__main__':main()
