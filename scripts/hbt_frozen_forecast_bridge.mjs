#!/usr/bin/env node
/**
 * HBT frozen forecast bridge — exact frozen-weight runtime.
 *
 * The predictive coefficients are NEVER re-fit here. We hydrate the persisted
 * HBT-1.1.2L-R1 structural L0 model from runtime/hbt_frozen_runtime_bundle.json,
 * reconstruct pre-match state chronologically, prove parity against the immutable
 * 2026-09-15 golden export, then rebuild state up to the requested target date and
 * emit date-scoped forecasts.
 *
 * Bookmaker prices are never read and cannot affect football probabilities.
 */
import fs from 'node:fs';
import path from 'node:path';
import { performance } from 'node:perf_hooks';

const ROOT = path.resolve(import.meta.dirname, '..');
const DATA = path.join(ROOT, 'hbt_live_data');
const RUNTIME = path.join(ROOT, 'runtime', 'hbt_frozen_runtime_bundle.json');
const SCANNER = path.join(DATA, 'slate_scanner.json');
const HBT14 = path.join(DATA, 'hbt_1_4_match_intelligence.json');
const GOLDEN = path.join(DATA, 'frozen_control_forecast_2026-09-15.json');
const STATUS = path.join(DATA, 'forecast_bridge_status.json');
const VERSION = 'HBT-FROZEN-FORECAST-BRIDGE-1.2-EXACT-WEIGHTS';
const PARITY_AS_OF_EXCLUSIVE = '2026-09-11';
const PARITY_TOLERANCE = 1e-9;
const DOMESTIC_CODES = new Set(['en.1','es.1','de.1','it.1','fr.1','nl.1','pt.1','sco.1','tr.1','en.2','es.2','it.2','be.1','pl.1','ie.1']);
const CLUB_GENERIC = new Set(['club','clube','football','futbol','fussball','calcio','societa','sportiva','de','do','del','the']);
const LEAGUE_LABELS = [
  ['en.1',['english premier league','premier league']],
  ['es.1',['spanish laliga','laliga','la liga']],
  ['de.1',['german bundesliga','bundesliga']],
  ['it.1',['italian serie a','serie a']],
  ['fr.1',['french ligue 1','ligue 1']],
  ['nl.1',['eredivisie']],
  ['pt.1',['primeira liga']],
  ['sco.1',['scottish premiership']],
  ['tr.1',['super lig','süper lig']],
  ['uefa.cl',['uefa champions league','champions league']],
];
const UA = 'Mozilla/5.0 (compatible; HBT-Frozen-Forecast-Bridge/1.2)';
let DATA_ALIAS_MAP = new Map();
let SEASON_LEAGUE_MAP = new Map();
let identityAudit = {linked:0,unresolved:0,ambiguous:0,continentalNames:0};

function readJSON(file, fallback={}) { try { return JSON.parse(fs.readFileSync(file,'utf8')); } catch { return fallback; } }
function writeJSON(file, obj) { fs.mkdirSync(path.dirname(file),{recursive:true}); const tmp=file+'.tmp'; fs.writeFileSync(tmp,JSON.stringify(obj,null,2)+'\n'); fs.renameSync(tmp,file); }
function nowISO(){return new Date().toISOString();}
function softmax(z){const m=Math.max(...z),e=z.map(v=>Math.exp(v-m)),s=e.reduce((a,b)=>a+b,0);return e.map(v=>v/s);}
function avg(a){return a.length?a.reduce((x,y)=>x+y,0)/a.length:0;}
function clip(x,a,b){return Math.max(a,Math.min(b,x));}
function daysBetween(a,b){if(!a||!b)return 7;return Math.max(0,(new Date(b)-new Date(a))/86400000);}
function seasonYear(s){return +(String(s||'').slice(0,4))||0;}
function decayFactor(days,halfLife){return !halfLife||halfLife<=0?1:Math.pow(.5,Math.max(0,days)/halfLife);}
function scoreFT(s){if(Array.isArray(s))return s;if(s&&Array.isArray(s.ft))return s.ft;return null;}
function baseTeamKey(s){return String(s||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/&/g,' and ').replace(/\b(fc|cf|afc|ssc|ac|fk|sk|sv)\b/g,' ').replace(/[^a-z0-9]+/g,' ').trim().replace(/\s+/g,' ');}
function clubSignature(s){return baseTeamKey(s).split(' ').filter(t=>t&&!CLUB_GENERIC.has(t)).join(' ');}
function teamKey(s){const b=baseTeamKey(s);return DATA_ALIAS_MAP.get(b)||b;}
function normText(s){return String(s||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,' ').trim().replace(/\s+/g,' ');}
function fixtureKey(date,home,away){return `${String(date||'').slice(0,10)}|${baseTeamKey(home)}|${baseTeamKey(away)}`;}
function groupKey(m){return m.date+'T'+(m.time||'DATE_ONLY');}

function prepareIdentityRegistry(matches){
  DATA_ALIAS_MAP=new Map(); SEASON_LEAGUE_MAP=new Map();
  const domesticKeys=new Set(),sigMap=new Map(),allNames=new Map(),continentalBases=new Set();
  for(const m of matches){
    for(const nm of [m.home,m.away])allNames.set(baseTeamKey(nm),nm);
    if(DOMESTIC_CODES.has(m.league)){
      for(const nm of [m.home,m.away]){const b=baseTeamKey(nm),sig=clubSignature(nm);domesticKeys.add(b);if(!sigMap.has(sig))sigMap.set(sig,new Set());sigMap.get(sig).add(b);}
    } else { continentalBases.add(baseTeamKey(m.home)); continentalBases.add(baseTeamKey(m.away)); }
  }
  let linked=0,unresolved=0,ambiguous=0;
  for(const b of continentalBases){
    if(domesticKeys.has(b))continue;
    const nm=allNames.get(b)||b,sig=clubSignature(nm);let candidates=[...(sigMap.get(sig)||[])];
    if(candidates.length===0&&sig.length>=8)candidates=[...domesticKeys].filter(k=>{const ks=clubSignature(allNames.get(k)||k);return ks.length>=8&&(ks===sig||ks.includes(sig)||sig.includes(ks));});
    candidates=[...new Set(candidates)];
    if(candidates.length===1){DATA_ALIAS_MAP.set(b,candidates[0]);linked++;} else if(candidates.length>1)ambiguous++; else unresolved++;
  }
  for(const m of matches){
    if(!DOMESTIC_CODES.has(m.league))continue;
    if(!SEASON_LEAGUE_MAP.has(m.season))SEASON_LEAGUE_MAP.set(m.season,new Map());
    const sm=SEASON_LEAGUE_MAP.get(m.season);sm.set(teamKey(m.home),m.league);sm.set(teamKey(m.away),m.league);
  }
  identityAudit={linked,unresolved,ambiguous,continentalNames:continentalBases.size};
  return identityAudit;
}
function knownSeasonLeague(season,key){return SEASON_LEAGUE_MAP.get(season)?.get(key)||null;}

class TeamState{
  constructor(display=''){this.dev=0;this.league=null;this.hist=[];this.lastDate=null;this.display=display;this.ratingDate=null;this.everDomestic=false;this.lastDomesticSeason=null;}
  push(r){this.hist.push(r);if(this.hist.length>30)this.hist.shift();this.lastDate=r.date;if(r.display)this.display=r.display;}
}
function recent(st,n,venue=null){const a=st.hist.filter(x=>!venue||x.venue===venue).slice(-n);if(!a.length)return {pts:1.35,gf:1.35,ga:1.35,gd:0,sos:1500,n:0};return {pts:avg(a.map(x=>x.pts)),gf:avg(a.map(x=>x.gf)),ga:avg(a.map(x=>x.ga)),gd:avg(a.map(x=>x.gf-x.ga)),sos:avg(a.map(x=>x.oppElo)),n:a.length};}
function getLeagueState(leagues,code){if(!code)return null;if(!leagues.has(code))leagues.set(code,{rating:1500,lastDate:null});return leagues.get(code);}
function decayLeagueTo(leagues,code,date,halfLife){const s=getLeagueState(leagues,code);if(!s)return 1500;if(s.lastDate){const d=daysBetween(s.lastDate,date);s.rating=1500+(s.rating-1500)*decayFactor(d,halfLife);}s.lastDate=date;return s.rating;}
function decayClubTo(st,date,halfLife){if(st.ratingDate){const d=daysBetween(st.ratingDate,date);st.dev*=decayFactor(d,halfLife);}st.ratingDate=date;}
function effectiveElo(st,leagues,date,opts){decayClubTo(st,date,opts.clubHalfLife);return decayLeagueTo(leagues,st.league,date,opts.leagueHalfLife)+st.dev;}
function effectiveEloReadOnly(st,leagues,date,opts){const clubDays=st.ratingDate?daysBetween(st.ratingDate,date):0,dev=st.dev*decayFactor(clubDays,opts.clubHalfLife),ls=st.league?leagues.get(st.league):null;let lr=1500;if(ls){const ld=ls.lastDate?daysBetween(ls.lastDate,date):0;lr=1500+(ls.rating-1500)*decayFactor(ld,opts.leagueHalfLife);}return lr+dev;}
function assignDomesticLeague(st,code,season,opts){if(!code||!DOMESTIC_CODES.has(code))return;const sy=seasonYear(season),hy=seasonYear(opts.historyStart);if(!st.everDomestic){if(sy>hy)st.dev+=opts.newTeamOffset;st.everDomestic=true;}else if(st.lastDomesticSeason&&sy-seasonYear(st.lastDomesticSeason)>1){st.dev=.5*st.dev+.5*opts.newTeamOffset;}if(st.league&&st.league!==code)st.dev*=.55;st.league=code;st.lastDomesticSeason=season;}
function snapshot(match,states,leagues,opts,mutating=true){
  const hk=match.homeKey||teamKey(match.home),ak=match.awayKey||teamKey(match.away),H=states.get(hk),A=states.get(ak);if(!H||!A)return null;
  const h5=recent(H,5),a5=recent(A,5),h10=recent(H,10),a10=recent(A,10),hv=recent(H,5,'H'),av=recent(A,5,'A'),hr=clip(daysBetween(H.lastDate,match.date),2,14),ar=clip(daysBetween(A.lastDate,match.date),2,14);
  const hE=mutating?effectiveElo(H,leagues,match.date,opts):effectiveEloReadOnly(H,leagues,match.date,opts),aE=mutating?effectiveElo(A,leagues,match.date,opts):effectiveEloReadOnly(A,leagues,match.date,opts);
  const raw={eloDiff:(hE-aE)/200,form5:(h5.pts-a5.pts)/3,form10:(h10.pts-a10.pts)/3,gd5:(h5.gd-a5.gd)/2.5,gd10:(h10.gd-a10.gd)/2.5,attack5:(h5.gf-a5.gf)/2.5,defence5:(a5.ga-h5.ga)/2.5,venueForm:(hv.pts-av.pts)/3,venueGD:(hv.gd-av.gd)/2.5,sos5:(h5.sos-a5.sos)/200,restDiff:(hr-ar)/7};
  return {vec:[raw.eloDiff,raw.form5,raw.form10,raw.gd5,raw.gd10,raw.attack5,raw.defence5,raw.venueForm,raw.venueGD,raw.sos5,raw.restDiff],raw,homeElo:hE,awayElo:aE,homeGames:H.hist.length,awayGames:A.hist.length,homeLeague:H.league,awayLeague:A.league,homeLastDate:H.lastDate,awayLastDate:A.lastDate};
}
function hierarchicalUpdate(H,A,leagues,hg,ag,date,opts,snap){const hE=snap.homeElo,aE=snap.awayElo,expH=1/(1+Math.pow(10,-((hE+opts.homeAdv)-aE)/400)),actual=hg>ag?1:hg<ag?0:.5,margin=Math.min(1.7,1+0.14*Math.max(0,Math.abs(hg-ag)-1)),d=opts.K*margin*(actual-expH),cross=H.league&&A.league&&H.league!==A.league;if(cross){H.dev+=d*(1-opts.leagueShare);A.dev-=d*(1-opts.leagueShare);const hl=getLeagueState(leagues,H.league),al=getLeagueState(leagues,A.league);hl.rating+=d*opts.leagueShare;al.rating-=d*opts.leagueShare;}else{H.dev+=d;A.dev-=d;}H.ratingDate=date;A.ratingDate=date;return !!cross;}
function buildState(matches,opts){
  const use=matches.filter(m=>m.season>=opts.historyStart),states=new Map(),leagues=new Map();let crossLeagueLinks=0,i=0;
  while(i<use.length){
    const key=groupKey(use[i]),group=[];while(i<use.length&&groupKey(use[i])===key)group.push(use[i++]);const pending=[];
    for(const m of group){
      const hk=teamKey(m.home),ak=teamKey(m.away);if(!states.has(hk))states.set(hk,new TeamState(m.home));if(!states.has(ak))states.set(ak,new TeamState(m.away));const H=states.get(hk),A=states.get(ak);
      const hKnown=DOMESTIC_CODES.has(m.league)?m.league:knownSeasonLeague(m.season,hk),aKnown=DOMESTIC_CODES.has(m.league)?m.league:knownSeasonLeague(m.season,ak);if(hKnown)assignDomesticLeague(H,hKnown,m.season,opts);if(aKnown)assignDomesticLeague(A,aKnown,m.season,opts);
      const snap=snapshot({...m,homeKey:hk,awayKey:ak},states,leagues,opts,true);if(!snap)continue;pending.push({m,H,A,snap});
    }
    for(const {m,H,A,snap} of pending){const hp=m.hg>m.ag?3:m.hg===m.ag?1:0,ap=m.ag>m.hg?3:m.hg===m.ag?1:0;H.push({date:m.date,venue:'H',pts:hp,gf:m.hg,ga:m.ag,oppElo:snap.awayElo,display:m.home});A.push({date:m.date,venue:'A',pts:ap,gf:m.ag,ga:m.hg,oppElo:snap.homeElo,display:m.away});if(hierarchicalUpdate(H,A,leagues,m.hg,m.ag,m.date,opts,snap))crossLeagueLinks++;}
  }
  return {states,leagues,crossLeagueLinks};
}

function hydrateFrozenModel(spec){
  if(!spec||!Array.isArray(spec.W)||!spec.st||!Array.isArray(spec.st.mu)||!Array.isArray(spec.st.sd))throw new Error('persisted frozen model spec invalid');
  const W=spec.W.map(r=>r.map(Number)),idx=Array.isArray(spec.featureIdx)?spec.featureIdx.map(Number):null,mu=spec.st.mu.map(Number),sd=spec.st.sd.map(Number),baseModel=spec.baseModel?hydrateFrozenModel(spec.baseModel):null;
  if(W.length!==3)throw new Error('persisted frozen model class count invalid');
  return {W,featureIdx:idx,baseModel,predict(r,T=1){let x=idx?idx.map(i=>r.vec[i]):r.vec.slice();if(x.length!==mu.length)throw new Error('persisted standardizer dimension mismatch');x=x.map((v,j)=>(v-mu[j])/(sd[j]||1));x=[1,...x];if(baseModel){const bp=baseModel.predict(r,1),z=W.map((w,c)=>Math.log(Math.max(1e-12,bp[c]))+w.reduce((s,v,j)=>s+v*x[j],0));return softmax(z.map(v=>v/T));}return softmax(W.map(w=>w.reduce((s,v,j)=>s+v*x[j],0)/T));}};
}

async function fetchJSON(url,timeoutMs=25000){const ac=new AbortController(),t=setTimeout(()=>ac.abort(),timeoutMs);try{const r=await fetch(url,{headers:{'user-agent':UA,'accept':'application/json'},signal:ac.signal});if(!r.ok)throw new Error(`${r.status} ${r.statusText}`);return await r.json();}finally{clearTimeout(t);}}
async function fetchSeasonCompetition(season,code){const urls=[`https://cdn.jsdelivr.net/gh/openfootball/football.json@master/${season}/${code}.json`,`https://raw.githubusercontent.com/openfootball/football.json/master/${season}/${code}.json`];let last;for(const url of urls){try{return {json:await fetchJSON(url),provider:new URL(url).hostname};}catch(e){last=e;}}throw last||new Error('source unavailable');}
async function loadSources(seasons,codes,asOfExclusive){
  const all=[],sourceAudit=[];
  for(const season of seasons)for(const code of codes){try{const got=await fetchSeasonCompetition(season,code);let n=0;for(const m of got.json.matches||[]){const ft=scoreFT(m.score);if(!ft||ft.length<2||ft[0]===null||ft[1]===null)continue;const d=String(m.date||'').slice(0,10);if(!/^\d{4}-\d{2}-\d{2}$/.test(d)||d>=asOfExclusive)continue;all.push({date:d,time:m.time||'',round:m.round||'',home:m.team1,away:m.team2,hg:+ft[0],ag:+ft[1],league:code,season});n++;}sourceAudit.push({source:`${season}/${code}`,status:'loaded',matches:n,provider:got.provider});}catch(e){sourceAudit.push({source:`${season}/${code}`,status:'failed',matches:0,error:String(e.message||e)});}}
  all.sort((a,b)=>(a.date+(a.time||'')).localeCompare(b.date+(b.time||'')));prepareIdentityRegistry(all);const seen=new Set(),uniq=[];let dup=0;for(const m of all){const k=[m.date,m.time,m.league,teamKey(m.home),teamKey(m.away),m.hg,m.ag].join('|');if(seen.has(k)){dup++;continue;}seen.add(k);uniq.push(m);}return {matches:uniq,sourceAudit,duplicatesRemoved:dup,identityAudit:{...identityAudit}};
}

function fixtureLeague(row,hbtLeagueIndex){const date=String(row.kickoff||row.date||'').slice(0,10),k=fixtureKey(date,row.home,row.away),fromIntel=hbtLeagueIndex.get(k);if(fromIntel)return fromIntel;if(row.leagueHint)return String(row.leagueHint);const s=normText(row.competition||row.competitionSlug||'');for(const [code,labels] of LEAGUE_LABELS)if(labels.some(x=>s===normText(x)||s.includes(normText(x))))return code;return null;}
function stateResolve(states,name){const direct=teamKey(name);if(states.has(direct))return direct;const b=baseTeamKey(name);if(states.has(b))return b;return null;}
function predictFixture(fx,deploy,crossLeagueLinks){const {states,leagues,opts,model,baseModel,T}=deploy,hk=stateResolve(states,fx.home),ak=stateResolve(states,fx.away);if(!hk||!ak)return {ok:false,reason:'unresolved team identity'};const H=states.get(hk),A=states.get(ak),ageH=daysBetween(H.lastDate,fx.date),ageA=daysBetween(A.lastDate,fx.date),maxAge=Math.max(ageH,ageA),snap=snapshot({date:fx.date,time:fx.time||'',homeKey:hk,awayKey:ak,home:fx.home,away:fx.away},states,leagues,opts,false);if(!snap)return {ok:false,reason:'unresolved team identity'};const p=model.predict(snap,T),bp=baseModel.predict(snap,1),pick=p[0]>=p[2]?0:2,pickProb=p[pick],basePick=bp[pick],drawGap=pickProb-p[1],minGames=Math.min(snap.homeGames,snap.awayGames),gamesQ=clip(minGames/20,0,1),freshQ=Math.exp(-Math.max(0,maxAge)/90),agreeQ=clip(1-Math.abs(pickProb-basePick)/.18,0,1),crossLeague=(snap.homeLeague&&snap.awayLeague&&snap.homeLeague!==snap.awayLeague),bridgeQ=crossLeague?(opts.leagueShare>0&&crossLeagueLinks>0?1:.45):1,sourceQ=fx.sourceStatus==='loaded'?1:.8,quality=clip(.36*gamesQ+.28*freshQ+.20*agreeQ+.11*bridgeQ+.05*sourceQ,0,1);let tier='Avoid';if(pickProb>=.68&&quality>=.75&&drawGap>=.17)tier='A';else if(pickProb>=.58&&quality>=.62&&drawGap>=.10)tier='B';else if(pickProb>=.50&&quality>=.45&&drawGap>=.04)tier='C';return {ok:true,snap,probs:p,baseProbs:bp,pick,pickName:pick===0?fx.home:fx.away,pickProb,basePick,quality,agreeQ,drawGap,tier,rawTier:tier,crossLeague,maxAge,minGames};}
function vecMaxAbs(a,b){return Math.max(...a.map((x,i)=>Math.abs(x-b[i])));}

async function main(){
  const started=performance.now(),bundle=readJSON(RUNTIME),scanner=readJSON(SCANNER),golden=readJSON(GOLDEN),hbt14=readJSON(HBT14),targetDate=process.argv.includes('--date')?process.argv[process.argv.indexOf('--date')+1]:scanner.targetDate;
  const statusBase={schemaVersion:'HBT-FORECAST-BRIDGE-STATUS-1',version:VERSION,generatedAt:nowISO(),targetDate,policy:{predictiveModel:'HBT-1.1.2L-R1',bookmakerOddsUsed:false,bookmakerOddsUsedInSimulation:false,retrainingOrRetuningPerformed:false,modelChoiceSearchPerformed:false,goldenParityRequired:true,failClosed:true,testAImmutable:true,frozenWeightsHydrated:true,targetStateUpdatedThroughPreviousCompletedDay:true}};
  try{
    if(!targetDate||!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(targetDate))throw new Error('target date missing/invalid');
    if(bundle.schemaVersion!=='HBT-FROZEN-RUNTIME-BUNDLE-1')throw new Error('runtime bundle schema invalid');
    const lock=bundle.liveL0Reference?.modelChoiceLock,l1=bundle.deploymentSnapshot?.models?.l1,l0Spec=l1?.baseModel;if(!lock?.opts||!l0Spec?.baseModel)throw new Error('persisted frozen L0 model missing');
    const model=hydrateFrozenModel(l0Spec),baseModel=model.baseModel,T=Number(lock.T);
    if(!Number.isFinite(T))throw new Error('frozen L0 temperature missing');
    const seasons=bundle.reconstruction?.seasons||[],codes=bundle.reconstruction?.codes||[];if(!seasons.length||!codes.length)throw new Error('reconstruction source scope missing');

    const parityLoad=await loadSources(seasons,codes,PARITY_AS_OF_EXCLUSIVE),parityState=buildState(parityLoad.matches,{...lock.opts}),parityDeploy={...parityState,opts:{...lock.opts},model,baseModel,T};
    const goldenRows=(golden.predictions||[]).filter(r=>!r.coveragePack&&r.fixture?.league&&codes.includes(r.fixture.league)),parity=[];let maxErr=0;
    for(const g of goldenRows){const expected=(g.layerPredictions||{}).L0||((String(g.predictionMode||'').startsWith('L0'))?g.probs:null);if(!Array.isArray(expected)||expected.length!==3)continue;const p=predictFixture({date:g.fixture.date,time:g.fixture.time||'',home:g.fixture.home,away:g.fixture.away,league:g.fixture.league,sourceStatus:g.fixture.sourceStatus||'loaded'},parityDeploy,parityState.crossLeagueLinks);if(!p.ok){parity.push({fixture:`${g.fixture.home} vs ${g.fixture.away}`,ok:false,reason:p.reason});continue;}const err=vecMaxAbs(expected,p.probs);maxErr=Math.max(maxErr,err);parity.push({fixture:`${g.fixture.home} vs ${g.fixture.away}`,ok:true,expected,actual:p.probs,maxAbsError:err});}
    if(parity.length<5)throw new Error(`golden parity sample too small: ${parity.length}`);
    const unresolved=parity.filter(x=>!x.ok).length,pass=unresolved===0&&maxErr<=PARITY_TOLERANCE;
    if(!pass){writeJSON(STATUS,{...statusBase,status:'BLOCKED_GOLDEN_PARITY',reconstruction:{parityAsOfExclusive:PARITY_AS_OF_EXCLUSIVE,seasons,codes,matches:parityLoad.matches.length,duplicatesRemoved:parityLoad.duplicatesRemoved,sourceFailures:parityLoad.sourceAudit.filter(x=>x.status!=='loaded'),identityAudit:parityLoad.identityAudit,crossLeagueLinks:parityState.crossLeagueLinks},goldenParity:{pass:false,tolerance:PARITY_TOLERANCE,maxAbsError:maxErr,unresolved,fixtures:parity},runtimeMs:performance.now()-started});console.error('HBT exact bridge blocked: golden parity failed',maxErr);return 2;}

    const targetLoad=targetDate===PARITY_AS_OF_EXCLUSIVE?parityLoad:await loadSources(seasons,codes,targetDate),targetState=buildState(targetLoad.matches,{...lock.opts}),deploy={...targetState,opts:{...lock.opts},model,baseModel,T};
    const intelLeague=new Map();for(const row of Object.values(hbt14.fixtures||{})){const date=String(row.kickoff||row.date||'').slice(0,10);if(row.home&&row.away&&row.league)intelLeague.set(fixtureKey(date,row.home,row.away),String(row.league));}
    const predictions=[],excluded=[];
    for(const r of scanner.fixtures||[]){const date=String(r.kickoff||'').slice(0,10);if(date!==targetDate)continue;const league=fixtureLeague(r,intelLeague);if(!league||!codes.includes(league))continue;const fx={date,time:String(r.kickoff||'').slice(11,16),league,home:r.home,away:r.away,sourceStatus:(r.sourceFreshness?'loaded':'unknown')},p=predictFixture(fx,deploy,targetState.crossLeagueLinks);if(!p.ok){excluded.push({fixture:`${r.home} vs ${r.away}`,league,reason:p.reason});continue;}predictions.push({fixture:{date,time:fx.time,league,home:r.home,away:r.away,provider:r.source||null,sourceStatus:fx.sourceStatus},coverage:p.maxAge>75?`stale-ish ${Math.round(p.maxAge)}d`:'good',coveragePack:null,tier:p.tier,rawTier:p.rawTier,quality:p.quality,probs:p.probs,pick:p.pickName,pickProb:p.pickProb,predictionMode:'L0 FALLBACK',fusionEligible:false,layerPredictions:{L0:p.probs},intelligenceStatus:null,scoreMarkets:null});}
    const artifact={schemaVersion:'HBT-FROZEN-CONTROL-FORECAST-1',sourceFile:'persisted HBT-1.1.2 exact frozen-weight runtime',sourceExportedAt:nowISO(),sourceLabVersion:'HBT-1.1.2L-R1',sourceEngineVersion:'HBT-0.4a frozen L0 exact-weight deployment bridge',targetDate,policy:{prospectiveExport:true,bookmakerOddsUsed:false,bookmakerOddsUsedInSimulation:false,predictiveModelMutated:false,retrainingPerformed:false,retuningPerformed:false,generalFutureLiveFeed:false,scope:'Date-scoped forecasts emitted only after exact persisted-weight golden parity.',missingFixtureSemantics:'unknown/not forecast in this export; never infer a probability',goldenParityRequired:true,goldenParityTolerance:PARITY_TOLERANCE,targetStateAsOfExclusive:targetDate},bridge:{version:VERSION,weightsSource:'runtime/hbt_frozen_runtime_bundle.json deploymentSnapshot.models.l1.baseModel',parityAsOfExclusive:PARITY_AS_OF_EXCLUSIVE,goldenForecastDate:'2026-09-15',goldenMaxAbsError:maxErr,targetStateAsOfExclusive:targetDate,sourceMatches:targetLoad.matches.length,sourceFailures:targetLoad.sourceAudit.filter(x=>x.status!=='loaded'),identityAudit:targetLoad.identityAudit,crossLeagueLinks:targetState.crossLeagueLinks,excluded},predictions};
    const out=path.join(DATA,`frozen_control_forecast_${targetDate}.json`);writeJSON(out,artifact);writeJSON(STATUS,{...statusBase,status:'READY',output:path.basename(out),reconstruction:{parityAsOfExclusive:PARITY_AS_OF_EXCLUSIVE,targetStateAsOfExclusive:targetDate,seasons,codes,parityMatches:parityLoad.matches.length,targetMatches:targetLoad.matches.length,sourceFailures:targetLoad.sourceAudit.filter(x=>x.status!=='loaded'),identityAudit:targetLoad.identityAudit,crossLeagueLinks:targetState.crossLeagueLinks},runtimeModel:{hydratedPersistedWeights:true,source:'deploymentSnapshot.models.l1.baseModel',temperature:T},goldenParity:{pass:true,tolerance:PARITY_TOLERANCE,maxAbsError:maxErr,unresolved:0,fixtures:parity},target:{discovered:(scanner.fixtures||[]).filter(x=>String(x.kickoff||'').slice(0,10)===targetDate).length,predictions:predictions.length,excluded},runtimeMs:performance.now()-started});
    console.log('HBT exact frozen bridge READY',{targetDate,predictions:predictions.length,maxErr,targetMatches:targetLoad.matches.length,sourceFailures:targetLoad.sourceAudit.filter(x=>x.status!=='loaded').length,runtimeMs:Math.round(performance.now()-started)});return 0;
  }catch(e){writeJSON(STATUS,{...statusBase,status:'BLOCKED_ERROR',reason:String(e.message||e),runtimeMs:performance.now()-started});console.error('HBT exact bridge blocked:',e);return 2;}
}

process.exitCode=await main();
