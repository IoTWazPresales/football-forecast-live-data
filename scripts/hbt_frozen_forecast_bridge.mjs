#!/usr/bin/env node
/**
 * HBT frozen forecast bridge.
 *
 * Reconstructs the frozen HBT-0.4a L0 deployment with the exact locked
 * configuration used by HBT-1.1.2L-R1, proves numerical parity against the
 * immutable 2026-09-15 golden forecast artifact, and only then emits a
 * date-scoped prospective forecast artifact for the discovered slate.
 *
 * This is deployment reconstruction, not training/model selection:
 * - structural hyperparameters, residual L2 and temperature are frozen;
 * - bookmaker prices are never read;
 * - no tuning/search/calibration is performed;
 * - current-day results are excluded from state reconstruction;
 * - any parity failure blocks current forecast export.
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
const VERSION = 'HBT-FROZEN-FORECAST-BRIDGE-1.1';
const CONTEXT_IDX = [1,2,3,4,5,6,7,8,9,10];
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
const UA = 'Mozilla/5.0 (compatible; HBT-Frozen-Forecast-Bridge/1.1)';
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
    const nm=allNames.get(b)||b,sig=clubSignature(nm); let candidates=[...(sigMap.get(sig)||[])];
    if(candidates.length===0&&sig.length>=8)candidates=[...domesticKeys].filter(k=>{const ks=clubSignature(allNames.get(k)||k);return ks.length>=8&&(ks===sig||ks.includes(sig)||sig.includes(ks));});
    candidates=[...new Set(candidates)];
    if(candidates.length===1){DATA_ALIAS_MAP.set(b,candidates[0]);linked++;} else if(candidates.length>1)ambiguous++; else unresolved++;
  }
  for(const m of matches){
    if(!DOMESTIC_CODES.has(m.league))continue;
    if(!SEASON_LEAGUE_MAP.has(m.season))SEASON_LEAGUE_MAP.set(m.season,new Map());
    const sm=SEASON_LEAGUE_MAP.get(m.season);sm.set(teamKey(m.home),m.league);sm.set(teamKey(m.away),m.league);
  }
  identityAudit={linked,unresolved,ambiguous,continentalNames:continentalBases.size};return identityAudit;
}
function knownSeasonLeague(season,key){return SEASON_LEAGUE_MAP.get(season)?.get(key)||null;}

class TeamState{constructor(display=''){this.dev=0;this.league=null;this.hist=[];this.lastDate=null;this.display=display;this.ratingDate=null;this.everDomestic=false;this.lastDomesticSeason=null;} push(r){this.hist.push(r);if(this.hist.length>30)this.hist.shift();this.lastDate=r.date;if(r.display)this.display=r.display;}}
function recent(st,n,venue=null){const a=st.hist.filter(x=>!venue||x.venue===venue).slice(-n);if(!a.length)return {pts:1.35,gf:1.35,ga:1.35,gd:0,sos:1500,n:0};return {pts:avg(a.map(x=>x.pts)),gf:avg(a.map(x=>x.gf)),ga:avg(a.map(x=>x.ga)),gd:avg(a.map(x=>x.gf-x.ga)),sos:avg(a.map(x=>x.oppElo)),n:a.length};}
function getLeagueState(leagues,code){if(!code)return null;if(!leagues.has(code))leagues.set(code,{rating:1500,lastDate:null});return leagues.get(code);}
function decayLeagueTo(leagues,code,date,halfLife){const s=getLeagueState(leagues,code);if(!s)return 1500;if(s.lastDate){const d=daysBetween(s.lastDate,date);s.rating=1500+(s.rating-1500)*decayFactor(d,halfLife);}s.lastDate=date;return s.rating;}
function decayClubTo(st,date,halfLife){if(st.ratingDate){const d=daysBetween(st.ratingDate,date);st.dev*=decayFactor(d,halfLife);}st.ratingDate=date;}
function effectiveElo(st,leagues,date,opts){decayClubTo(st,date,opts.clubHalfLife);return decayLeagueTo(leagues,st.league,date,opts.leagueHalfLife)+st.dev;}
function effectiveEloReadOnly(st,leagues,date,opts){const clubDays=st.ratingDate?daysBetween(st.ratingDate,date):0,dev=st.dev*decayFactor(clubDays,opts.clubHalfLife),ls=st.league?leagues.get(st.league):null;let lr=1500;if(ls){const ld=ls.lastDate?daysBetween(ls.lastDate,date):0;lr=1500+(ls.rating-1500)*decayFactor(ld,opts.leagueHalfLife);}return lr+dev;}
function assignDomesticLeague(st,code,season,opts){if(!code||!DOMESTIC_CODES.has(code))return;const sy=seasonYear(season),hy=seasonYear(opts.historyStart);if(!st.everDomestic){if(sy>hy)st.dev+=opts.newTeamOffset;st.everDomestic=true;}else if(st.lastDomesticSeason&&sy-seasonYear(st.lastDomesticSeason)>1){st.dev=.5*st.dev+.5*opts.newTeamOffset;}if(st.league&&st.league!==code)st.dev*=.55;st.league=code;st.lastDomesticSeason=season;}
function snapshot(match,states,leagues,opts){
  const hk=match.homeKey||teamKey(match.home),ak=match.awayKey||teamKey(match.away),H=states.get(hk)||new TeamState(match.home),A=states.get(ak)||new TeamState(match.away),h5=recent(H,5),a5=recent(A,5),h10=recent(H,10),a10=recent(A,10),hv=recent(H,5,'H'),av=recent(A,5,'A'),hr=clip(daysBetween(H.lastDate,match.date),2,14),ar=clip(daysBetween(A.lastDate,match.date),2,14),hE=effectiveElo(H,leagues,match.date,opts),aE=effectiveElo(A,leagues,match.date,opts);
  const raw={eloDiff:(hE-aE)/200,form5:(h5.pts-a5.pts)/3,form10:(h10.pts-a10.pts)/3,gd5:(h5.gd-a5.gd)/2.5,gd10:(h10.gd-a10.gd)/2.5,attack5:(h5.gf-a5.gf)/2.5,defence5:(a5.ga-h5.ga)/2.5,venueForm:(hv.pts-av.pts)/3,venueGD:(hv.gd-av.gd)/2.5,sos5:(h5.sos-a5.sos)/200,restDiff:(hr-ar)/7};
  return {vec:[raw.eloDiff,raw.form5,raw.form10,raw.gd5,raw.gd10,raw.attack5,raw.defence5,raw.venueForm,raw.venueGD,raw.sos5,raw.restDiff],raw,homeElo:hE,awayElo:aE,homeGames:H.hist.length,awayGames:A.hist.length,homeLeague:H.league,awayLeague:A.league,homeLastDate:H.lastDate,awayLastDate:A.lastDate};
}
function forecastSnapshot(match,states,leagues,opts){
  const hk=match.homeKey||teamKey(match.home),ak=match.awayKey||teamKey(match.away),H=states.get(hk),A=states.get(ak);if(!H||!A)return null;
  const h5=recent(H,5),a5=recent(A,5),h10=recent(H,10),a10=recent(A,10),hv=recent(H,5,'H'),av=recent(A,5,'A'),hr=clip(daysBetween(H.lastDate,match.date),2,14),ar=clip(daysBetween(A.lastDate,match.date),2,14),hE=effectiveEloReadOnly(H,leagues,match.date,opts),aE=effectiveEloReadOnly(A,leagues,match.date,opts);
  const raw={eloDiff:(hE-aE)/200,form5:(h5.pts-a5.pts)/3,form10:(h10.pts-a10.pts)/3,gd5:(h5.gd-a5.gd)/2.5,gd10:(h10.gd-a10.gd)/2.5,attack5:(h5.gf-a5.gf)/2.5,defence5:(a5.ga-h5.ga)/2.5,venueForm:(hv.pts-av.pts)/3,venueGD:(hv.gd-av.gd)/2.5,sos5:(h5.sos-a5.sos)/200,restDiff:(hr-ar)/7};
  return {vec:[raw.eloDiff,raw.form5,raw.form10,raw.gd5,raw.gd10,raw.attack5,raw.defence5,raw.venueForm,raw.venueGD,raw.sos5,raw.restDiff],raw,homeElo:hE,awayElo:aE,homeGames:H.hist.length,awayGames:A.hist.length,homeLeague:H.league,awayLeague:A.league,homeLastDate:H.lastDate,awayLastDate:A.lastDate};
}
function hierarchicalUpdate(H,A,leagues,hg,ag,date,opts,snap){const hE=snap.homeElo,aE=snap.awayElo,expH=1/(1+Math.pow(10,-((hE+opts.homeAdv)-aE)/400)),actual=hg>ag?1:hg<ag?0:.5,margin=Math.min(1.7,1+0.14*Math.max(0,Math.abs(hg-ag)-1)),d=opts.K*margin*(actual-expH),cross=H.league&&A.league&&H.league!==A.league;if(cross){H.dev+=d*(1-opts.leagueShare);A.dev-=d*(1-opts.leagueShare);const hl=getLeagueState(leagues,H.league),al=getLeagueState(leagues,A.league);hl.rating+=d*opts.leagueShare;al.rating-=d*opts.leagueShare;}else{H.dev+=d;A.dev-=d;}H.ratingDate=date;A.ratingDate=date;return !!cross;}
function buildExamples(matches,opts){const use=matches.filter(m=>m.season>=opts.historyStart),states=new Map(),leagues=new Map(),rows=[];let groupCount=0,crossLeagueLinks=0,i=0;while(i<use.length){const key=groupKey(use[i]),group=[];while(i<use.length&&groupKey(use[i])===key)group.push(use[i++]);groupCount++;const pending=[];for(const m of group){const hk=teamKey(m.home),ak=teamKey(m.away);if(!states.has(hk))states.set(hk,new TeamState(m.home));if(!states.has(ak))states.set(ak,new TeamState(m.away));const H=states.get(hk),A=states.get(ak),hKnown=DOMESTIC_CODES.has(m.league)?m.league:knownSeasonLeague(m.season,hk),aKnown=DOMESTIC_CODES.has(m.league)?m.league:knownSeasonLeague(m.season,ak);if(hKnown)assignDomesticLeague(H,hKnown,m.season,opts);if(aKnown)assignDomesticLeague(A,aKnown,m.season,opts);const snap=snapshot({...m,homeKey:hk,awayKey:ak},states,leagues,opts),y=m.hg>m.ag?0:m.hg===m.ag?1:2;rows.push({...m,y,...snap,group:key});pending.push({m,H,A,snap});}for(const {m,H,A,snap} of pending){const hp=m.hg>m.ag?3:m.hg===m.ag?1:0,ap=m.ag>m.hg?3:m.hg===m.ag?1:0;H.push({date:m.date,venue:'H',pts:hp,gf:m.hg,ga:m.ag,oppElo:snap.awayElo,display:m.home});A.push({date:m.date,venue:'A',pts:ap,gf:m.ag,ga:m.hg,oppElo:snap.homeElo,display:m.away});if(hierarchicalUpdate(H,A,leagues,m.hg,m.ag,m.date,opts,snap))crossLeagueLinks++;}}return {rows,states,leagues,groupCount,crossLeagueLinks};}
function typedDesign(rows,featureIdx=null){if(!rows.length)throw new Error('Cannot fit optimizer on zero rows.');const idx=featureIdx?featureIdx.slice():rows[0].vec.map((_,i)=>i),p=idx.length,d=p+1,n=rows.length,mu=Array(p).fill(0),sd=Array(p).fill(0);for(const r of rows)for(let j=0;j<p;j++)mu[j]+=r.vec[idx[j]]/n;for(const r of rows)for(let j=0;j<p;j++){const q=r.vec[idx[j]]-mu[j];sd[j]+=q*q/n;}for(let j=0;j<p;j++)sd[j]=Math.sqrt(sd[j])||1;const X=new Float64Array(n*d),y=new Uint8Array(n);for(let i=0;i<n;i++){const o=i*d;X[o]=1;y[i]=rows[i].y;for(let j=0;j<p;j++)X[o+j+1]=(rows[i].vec[idx[j]]-mu[j])/sd[j];}const st={mu,sd,apply:x=>x.map((v,j)=>(v-mu[j])/sd[j])};return {X,y,st,idx,p,d,n};}
function typedLoss(X,y,W,d,n,l2,baseLogP=null){let loss=0;for(let i=0;i<n;i++){const o=i*d;let z0=baseLogP?baseLogP[i*3]:0,z1=baseLogP?baseLogP[i*3+1]:0,z2=baseLogP?baseLogP[i*3+2]:0;for(let j=0;j<d;j++){const x=X[o+j];z0+=W[j]*x;z1+=W[d+j]*x;z2+=W[2*d+j]*x;}const m=Math.max(z0,z1,z2),e0=Math.exp(z0-m),e1=Math.exp(z1-m),e2=Math.exp(z2-m),den=e0+e1+e2,p=y[i]===0?e0/den:y[i]===1?e1/den:e2/den;loss-=Math.log(Math.max(1e-12,p));}let pen=0;for(let c=0;c<3;c++)for(let j=1;j<d;j++){const w=W[c*d+j];pen+=w*w;}return loss/n+.5*l2*pen;}
function fitSoftmax(rows,featureIdx=null,maxIters=600,lr=.06,l2=.003){const D=typedDesign(rows,featureIdx),{X,y,st,d,n}=D,W=new Float64Array(3*d),G=new Float64Array(3*d);let prev=Infinity,stable=0,iter=0,loss=Infinity,lastGrad=Infinity;for(iter=0;iter<maxIters;iter++){G.fill(0);for(let i=0;i<n;i++){const o=i*d;let z0=0,z1=0,z2=0;for(let j=0;j<d;j++){const x=X[o+j];z0+=W[j]*x;z1+=W[d+j]*x;z2+=W[2*d+j]*x;}const m=Math.max(z0,z1,z2),e0=Math.exp(z0-m),e1=Math.exp(z1-m),e2=Math.exp(z2-m),den=e0+e1+e2,yy=y[i],er0=e0/den-(yy===0?1:0),er1=e1/den-(yy===1?1:0),er2=e2/den-(yy===2?1:0);for(let j=0;j<d;j++){const x=X[o+j];G[j]+=er0*x;G[d+j]+=er1*x;G[2*d+j]+=er2*x;}}let gs=0;for(let c=0;c<3;c++)for(let j=0;j<d;j++){const k=c*d+j,g=G[k]/n+(j?l2*W[k]:0);gs+=g*g;W[k]-=lr*g;}lastGrad=Math.sqrt(gs);if(iter%10===0||iter===maxIters-1){loss=typedLoss(X,y,W,d,n,l2);if(!Number.isFinite(loss))throw new Error('Softmax optimizer produced non-finite loss.');const imp=prev-loss;if(imp>=0&&imp<1e-7)stable++;else stable=0;prev=loss;if(stable>=5)break;}}const nested=[Array.from(W.slice(0,d)),Array.from(W.slice(d,2*d)),Array.from(W.slice(2*d,3*d))],idx=featureIdx?featureIdx.slice():null;return {W:nested,st,featureIdx:idx,iterations:iter+1,trainLoss:loss,gradNorm:lastGrad,converged:stable>=5,predict(r,T=1){let x=idx?idx.map(i=>r.vec[i]):r.vec.slice();x=st.apply(x);x=[1,...x];return softmax(nested.map(w=>w.reduce((sum,v,j)=>sum+v*x[j],0)/T));}};}
function fitResidualOnce(rows,baseModel,featureIdx=CONTEXT_IDX,maxIters=900,lr=.03,l2=.1){const D=typedDesign(rows,featureIdx),{X,y,st,d,n}=D,W=new Float64Array(3*d),G=new Float64Array(3*d),baseLogP=new Float64Array(n*3);for(let i=0;i<n;i++){const bp=baseModel.predict(rows[i],1);baseLogP[i*3]=Math.log(Math.max(1e-12,bp[0]));baseLogP[i*3+1]=Math.log(Math.max(1e-12,bp[1]));baseLogP[i*3+2]=Math.log(Math.max(1e-12,bp[2]));}let prev=Infinity,stable=0,iter=0,loss=Infinity,lastGrad=Infinity;for(iter=0;iter<maxIters;iter++){G.fill(0);for(let i=0;i<n;i++){const o=i*d,b=i*3;let z0=baseLogP[b],z1=baseLogP[b+1],z2=baseLogP[b+2];for(let j=0;j<d;j++){const x=X[o+j];z0+=W[j]*x;z1+=W[d+j]*x;z2+=W[2*d+j]*x;}const m=Math.max(z0,z1,z2),e0=Math.exp(z0-m),e1=Math.exp(z1-m),e2=Math.exp(z2-m),den=e0+e1+e2,yy=y[i],er0=e0/den-(yy===0?1:0),er1=e1/den-(yy===1?1:0),er2=e2/den-(yy===2?1:0);for(let j=0;j<d;j++){const x=X[o+j];G[j]+=er0*x;G[d+j]+=er1*x;G[2*d+j]+=er2*x;}}let gs=0;for(let c=0;c<3;c++)for(let j=0;j<d;j++){const k=c*d+j,g=G[k]/n+(j?l2*W[k]:0);gs+=g*g;W[k]-=lr*g;}lastGrad=Math.sqrt(gs);if(iter%10===0||iter===maxIters-1){loss=typedLoss(X,y,W,d,n,l2,baseLogP);if(!Number.isFinite(loss))throw new Error('Residual optimizer produced non-finite loss.');const imp=Math.abs(prev-loss);if(imp<5e-7||lastGrad<2e-5)stable++;else stable=0;prev=loss;if(stable>=4)break;}}const nested=[Array.from(W.slice(0,d)),Array.from(W.slice(d,2*d)),Array.from(W.slice(2*d,3*d))],idx=featureIdx.slice();return {W:nested,st,featureIdx:idx,baseModel,iterations:iter+1,trainLoss:loss,gradNorm:lastGrad,converged:stable>=4,predict(r,T=1){let x=idx.map(i=>r.vec[i]);x=st.apply(x);x=[1,...x];const bp=baseModel.predict(r,1),z=nested.map((w,c)=>Math.log(Math.max(1e-12,bp[c]))+w.reduce((sum,v,j)=>sum+v*x[j],0));return softmax(z.map(v=>v/T));}};}
function fitResidual(rows,baseModel,featureIdx=CONTEXT_IDX,maxIters=900,lr=.03,l2=.1){const attempts=[{max:maxIters,lr},{max:Math.max(maxIters,1400),lr:lr*.5},{max:Math.max(maxIters,2200),lr:lr*.25}];let best=null,total=0;for(const a of attempts){const r=fitResidualOnce(rows,baseModel,featureIdx,a.max,a.lr,l2);total+=r.iterations;if(!best||r.trainLoss<best.trainLoss)best=r;if(r.converged){r.retryIterations=total;return r;}}best.retryIterations=total;return best;}

async function fetchJSON(url, timeoutMs=25000){const ac=new AbortController(),t=setTimeout(()=>ac.abort(),timeoutMs);try{const r=await fetch(url,{headers:{'user-agent':UA,'accept':'application/json'},signal:ac.signal});if(!r.ok)throw new Error(`${r.status} ${r.statusText}`);return await r.json();}finally{clearTimeout(t);}}
async function fetchSeasonCompetition(season,code){const urls=[`https://cdn.jsdelivr.net/gh/openfootball/football.json@master/${season}/${code}.json`,`https://raw.githubusercontent.com/openfootball/football.json/master/${season}/${code}.json`];let last;for(const url of urls){try{return {json:await fetchJSON(url),provider:new URL(url).hostname};}catch(e){last=e;}}throw last||new Error('source unavailable');}
async function loadSources(seasons,codes,asOfExclusive){const all=[],sourceAudit=[];for(const season of seasons){for(const code of codes){try{const got=await fetchSeasonCompetition(season,code);let n=0;for(const m of got.json.matches||[]){const ft=scoreFT(m.score);if(!ft||ft.length<2||ft[0]===null||ft[1]===null)continue;const d=String(m.date||'').slice(0,10);if(!/^\d{4}-\d{2}-\d{2}$/.test(d)||d>=asOfExclusive)continue;all.push({date:d,time:m.time||'',round:m.round||'',home:m.team1,away:m.team2,hg:+ft[0],ag:+ft[1],league:code,season});n++;}sourceAudit.push({source:`${season}/${code}`,status:'loaded',matches:n,provider:got.provider});}catch(e){sourceAudit.push({source:`${season}/${code}`,status:'failed',matches:0,error:String(e.message||e)});}}}
  all.sort((a,b)=>(a.date+(a.time||'')).localeCompare(b.date+(b.time||'')));prepareIdentityRegistry(all);const seen=new Set(),uniq=[];let dup=0;for(const m of all){const k=[m.date,m.time,m.league,teamKey(m.home),teamKey(m.away),m.hg,m.ag].join('|');if(seen.has(k)){dup++;continue;}seen.add(k);uniq.push(m);}return {matches:uniq,sourceAudit,duplicatesRemoved:dup};}

function fixtureLeague(row,hbtLeagueIndex){const date=String(row.kickoff||row.date||'').slice(0,10),k=fixtureKey(date,row.home,row.away),fromIntel=hbtLeagueIndex.get(k);if(fromIntel)return fromIntel;if(row.leagueHint)return String(row.leagueHint);const s=normText(row.competition||row.competitionSlug||'');for(const [code,labels] of LEAGUE_LABELS)if(labels.some(x=>s===normText(x)||s.includes(normText(x))))return code;return null;}
function stateResolve(states,name){const direct=teamKey(name);if(states.has(direct))return direct;const b=baseTeamKey(name);if(states.has(b))return b;return null;}
function predictL0Fixture(fx,deploy,crossLeagueLinks){const {states,leagues,opts,model,baseModel,T}=deploy,hk=stateResolve(states,fx.home),ak=stateResolve(states,fx.away);if(!hk||!ak)return {ok:false,reason:'unresolved team identity'};const H=states.get(hk),A=states.get(ak),ageH=daysBetween(H.lastDate,fx.date),ageA=daysBetween(A.lastDate,fx.date),maxAge=Math.max(ageH,ageA),snap=forecastSnapshot({date:fx.date,time:fx.time||'',homeKey:hk,awayKey:ak,home:fx.home,away:fx.away},states,leagues,opts);if(!snap)return {ok:false,reason:'unresolved team identity'};const p=model.predict(snap,T),bp=baseModel.predict(snap,1),pick=p[0]>=p[2]?0:2,pickProb=p[pick],basePick=bp[pick],drawGap=pickProb-p[1],minGames=Math.min(snap.homeGames,snap.awayGames),gamesQ=clip(minGames/20,0,1),freshQ=Math.exp(-Math.max(0,maxAge)/90),agreeQ=clip(1-Math.abs(pickProb-basePick)/.18,0,1),crossLeague=(snap.homeLeague&&snap.awayLeague&&snap.homeLeague!==snap.awayLeague),bridgeQ=crossLeague?(opts.leagueShare>0&&crossLeagueLinks>0?1:.45):1,sourceQ=fx.sourceStatus==='loaded'?1:.8,quality=clip(.36*gamesQ+.28*freshQ+.20*agreeQ+.11*bridgeQ+.05*sourceQ,0,1);let tier='Avoid';if(pickProb>=.68&&quality>=.75&&drawGap>=.17)tier='A';else if(pickProb>=.58&&quality>=.62&&drawGap>=.10)tier='B';else if(pickProb>=.50&&quality>=.45&&drawGap>=.04)tier='C';return {ok:true,snap,probs:p,baseProbs:bp,pick,pickName:pick===0?fx.home:fx.away,pickProb,basePick,quality,agreeQ,drawGap,tier,rawTier:tier,crossLeague,maxAge,minGames};}
function vecMaxAbs(a,b){return Math.max(...a.map((x,i)=>Math.abs(x-b[i])));}

async function main(){
  const started=performance.now(),bundle=readJSON(RUNTIME),scanner=readJSON(SCANNER),golden=readJSON(GOLDEN),hbt14=readJSON(HBT14);
  const targetDate=process.argv.includes('--date')?process.argv[process.argv.indexOf('--date')+1]:scanner.targetDate;
  const statusBase={schemaVersion:'HBT-FORECAST-BRIDGE-STATUS-1',version:VERSION,generatedAt:nowISO(),targetDate,policy:{predictiveModel:'HBT-1.1.2L-R1',bookmakerOddsUsed:false,bookmakerOddsUsedInSimulation:false,retrainingOrRetuningPerformed:false,modelChoiceSearchPerformed:false,goldenParityRequired:true,failClosed:true,testAImmutable:true}};
  try{
    if(!targetDate||!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(targetDate))throw new Error('target date missing/invalid');
    if(bundle.schemaVersion!=='HBT-FROZEN-RUNTIME-BUNDLE-1')throw new Error('runtime bundle schema invalid');
    const lock=bundle.liveL0Reference?.modelChoiceLock;if(!lock?.opts||!Number.isFinite(lock.residL2)||!Number.isFinite(lock.T))throw new Error('frozen L0 lock missing');
    const asOfExclusive='2026-09-11';
    const seasons=bundle.reconstruction?.seasons||[],codes=bundle.reconstruction?.codes||[];
    if(!seasons.length||!codes.length)throw new Error('reconstruction source scope missing');
    const loaded=await loadSources(seasons,codes,asOfExclusive);
    const sourceFailures=loaded.sourceAudit.filter(x=>x.status!=='loaded');
    const built=buildExamples(loaded.matches,{...lock.opts});
    const rows=built.rows;if(rows.length<2000)throw new Error(`reconstruction row count too small: ${rows.length}`);
    const baseModel=fitSoftmax(rows,[0],750,.055,.003),model=fitResidual(rows,baseModel,CONTEXT_IDX,950,.03,lock.residL2);
    if(!baseModel.converged||!model.converged)throw new Error('deployment reconstruction optimizer did not converge');
    const deploy={states:built.states,leagues:built.leagues,opts:{...lock.opts},baseModel,model,T:lock.T};

    const goldenRows=(golden.predictions||[]).filter(r=>!r.coveragePack && r.fixture?.league && codes.includes(r.fixture.league));
    const parity=[];let maxErr=0;
    for(const g of goldenRows){const expected=(g.layerPredictions||{}).L0||((String(g.predictionMode||'').startsWith('L0'))?g.probs:null);if(!Array.isArray(expected)||expected.length!==3)continue;const p=predictL0Fixture({date:g.fixture.date,time:g.fixture.time||'',home:g.fixture.home,away:g.fixture.away,league:g.fixture.league,sourceStatus:g.fixture.sourceStatus||'loaded'},deploy,built.crossLeagueLinks);if(!p.ok){parity.push({fixture:`${g.fixture.home} vs ${g.fixture.away}`,ok:false,reason:p.reason});continue;}const err=vecMaxAbs(expected,p.probs);maxErr=Math.max(maxErr,err);parity.push({fixture:`${g.fixture.home} vs ${g.fixture.away}`,ok:true,expected,actual:p.probs,maxAbsError:err});}
    if(parity.length<5)throw new Error(`golden parity sample too small: ${parity.length}`);
    const unresolvedParity=parity.filter(x=>!x.ok).length;
    const tolerance=1e-9,parityPass=unresolvedParity===0&&maxErr<=tolerance;
    if(!parityPass){writeJSON(STATUS,{...statusBase,status:'BLOCKED_GOLDEN_PARITY',reconstruction:{asOfExclusive,seasons,codes,matches:loaded.matches.length,rows:rows.length,duplicatesRemoved:loaded.duplicatesRemoved,sourceFailures,identityAudit,crossLeagueLinks:built.crossLeagueLinks},goldenParity:{pass:false,tolerance,maxAbsError:maxErr,unresolved:unresolvedParity,fixtures:parity},runtimeMs:performance.now()-started});console.error('HBT bridge blocked: golden parity failed',maxErr);return 2;}

    const intelLeague=new Map();for(const row of Object.values(hbt14.fixtures||{})){const date=String(row.kickoff||row.date||'').slice(0,10);if(row.home&&row.away&&row.league)intelLeague.set(fixtureKey(date,row.home,row.away),String(row.league));}
    const predictions=[],excluded=[];
    for(const r of scanner.fixtures||[]){const date=String(r.kickoff||'').slice(0,10);if(date!==targetDate)continue;const league=fixtureLeague(r,intelLeague);if(!league||!codes.includes(league))continue;
      const fx={date,time:String(r.kickoff||'').slice(11,16),league,home:r.home,away:r.away,sourceStatus:(r.sourceFreshness?'loaded':'unknown')};
      const p=predictL0Fixture(fx,deploy,built.crossLeagueLinks);if(!p.ok){excluded.push({fixture:`${r.home} vs ${r.away}`,league,reason:p.reason});continue;}
      predictions.push({fixture:{date,time:fx.time,league,home:r.home,away:r.away,provider:r.source||null,sourceStatus:fx.sourceStatus},coverage:p.maxAge>75?`stale-ish ${Math.round(p.maxAge)}d`:'good',coveragePack:null,tier:p.tier,rawTier:p.rawTier,quality:p.quality,probs:p.probs,pick:p.pickName,pickProb:p.pickProb,predictionMode:'L0 FALLBACK',fusionEligible:false,layerPredictions:{L0:p.probs},intelligenceStatus:null,scoreMarkets:null});
    }
    const artifact={schemaVersion:'HBT-FROZEN-CONTROL-FORECAST-1',sourceFile:'automatic frozen deployment reconstruction',sourceExportedAt:nowISO(),sourceLabVersion:'HBT-1.1.2L-R1',sourceEngineVersion:'HBT-0.4a frozen L0 deployment bridge',targetDate,policy:{prospectiveExport:true,bookmakerOddsUsed:false,bookmakerOddsUsedInSimulation:false,predictiveModelMutated:false,retrainingPerformed:false,retuningPerformed:false,generalFutureLiveFeed:false,scope:'Date-scoped forecasts emitted only after exact frozen-runtime golden parity.',missingFixtureSemantics:'unknown/not forecast in this export; never infer a probability',goldenParityRequired:true,goldenParityTolerance:tolerance},bridge:{version:VERSION,reconstructionAsOfExclusive:asOfExclusive,goldenForecastDate:'2026-09-15',goldenMaxAbsError:maxErr,sourceMatches:loaded.matches.length,modelRows:rows.length,sourceFailures,identityAudit,crossLeagueLinks:built.crossLeagueLinks,excluded},predictions};
    const out=path.join(DATA,`frozen_control_forecast_${targetDate}.json`);writeJSON(out,artifact);writeJSON(STATUS,{...statusBase,status:'READY',output:path.basename(out),reconstruction:{asOfExclusive,seasons,codes,matches:loaded.matches.length,rows:rows.length,duplicatesRemoved:loaded.duplicatesRemoved,sourceFailures,identityAudit,crossLeagueLinks:built.crossLeagueLinks},optimizers:{baseConverged:baseModel.converged,baseIterations:baseModel.iterations,residualConverged:model.converged,residualIterations:model.iterations},goldenParity:{pass:true,tolerance,maxAbsError:maxErr,unresolved:0,fixtures:parity},target:{discovered:(scanner.fixtures||[]).filter(x=>String(x.kickoff||'').slice(0,10)===targetDate).length,predictions:predictions.length,excluded},runtimeMs:performance.now()-started});
    console.log('HBT frozen bridge READY',{targetDate,predictions:predictions.length,maxErr,rows:rows.length,sourceFailures:sourceFailures.length,runtimeMs:Math.round(performance.now()-started)});return 0;
  }catch(e){writeJSON(STATUS,{...statusBase,status:'BLOCKED_ERROR',reason:String(e.message||e),runtimeMs:performance.now()-started});console.error('HBT bridge blocked:',e);return 2;}
}

process.exitCode=await main();
