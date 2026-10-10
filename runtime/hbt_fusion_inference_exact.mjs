// Exact function bodies recovered from Forecast Lab R4. No training or tuning.
const PERF_ALIAS_MAP=new Map([
 ['internazionale milano','inter'],['internazionale','inter'],['inter milan','inter'],
 ['rasenballsport leipzig','leipzig'],['rb leipzig','leipzig'],
 ['bayern munchen','bayern'],['bayern munich','bayern'],
 ['borussia monchengladbach','monchengladbach'],['borussia m gladbach','monchengladbach'],['m gladbach','monchengladbach'],
 ['lyonnais','lyon'],['marseille','marseille'],['rennais','rennes'],['strasbourg alsace','strasbourg'],
 ['deportivo alaves','alaves'],['hellas verona','verona'],['chievo verona','chievo'],
 ['hamburger','hamburg'],['koln','cologne'],['cologne','cologne'],['tottenham hotspur','tottenham'],
 ['coventry city','coventry'],['brighton and hove albion','brighton'],
 ['es troyes','troyes'],['racing lens','lens'],['brestois','brest'],
 ['leeds united','leeds'],['real betis balompie','real betis'],
 ['rayo vallecano madrid','rayo vallecano'],['rcd espanyol barcelona','espanyol'],
 ['ca osasuna','osasuna'],['real racing santander','racing santander']
]);
const L1_WINDOW=5,L1_MIN_HISTORY=3,L1_SHRINK_PRIOR=5,L1_MAX_AGE_DAYS=180,L4_MAX_GOALS=10;
let FUSION_DEPLOY=null;
function softmax(z){let m=Math.max(...z),e=z.map(v=>Math.exp(v-m)),s=e.reduce((a,b)=>a+b,0);return e.map(v=>v/s)}
function baseTeamKey(s){
 return String(s||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'')
   .replace(/&/g,' and ').replace(/\b(fc|cf|afc|ssc|ac|fk|sk|sv)\b/g,' ')
   .replace(/[^a-z0-9]+/g,' ').trim().replace(/\s+/g,' ');
}
function avg(a){return a.length?a.reduce((x,y)=>x+y,0)/a.length:0}
function clip(x,a,b){return Math.max(a,Math.min(b,x))}
function daysBetween(a,b){if(!a||!b)return 7;return Math.max(0,(new Date(b)-new Date(a))/86400000)}
function perfTeamKey(s){
 let toks=baseTeamKey(s).split(' '),generic=new Set(['club','clube','football','futbol','fussball','calcio','societa','sportiva','de','do','del','the','as','ss','us','rc','sc','sd','cd','ud','bc','bsc','tsg','fsv','acf','uc','ea','sco','osc','hsc','ogc','stade','olympique','girondins']);
 toks=toks.filter(t=>t&&!generic.has(t)&&!/^\d+$/.test(t));let k=toks.join(' ');return PERF_ALIAS_MAP.get(k)||k;
}
function l1AvgHist(hist,n=L1_WINDOW){const a=hist.slice(-n);if(!a.length)return null;return {n:a.length,npxG:avg(a.map(x=>x.npxG)),npxGA:avg(a.map(x=>x.npxGA)),deepBal:avg(a.map(x=>x.deep-x.deepAllowed)),finish:avg(a.map(x=>x.scored-x.npxG)),prevent:avg(a.map(x=>x.npxGA-x.missed))}}
function l3ExpectedGames(league){return league==='de.1'?34:38}
function l3TablePressure(table,key,league){
 const rec=table.get(key);if(!rec||rec.gp<8||table.size<10)return 0;
 const arr=[...table.entries()].map(([k,v])=>({k,...v,gd:v.gf-v.ga})).sort((a,b)=>b.pts-a.pts||b.gd-a.gd||b.gf-a.gf);
 const pos=arr.findIndex(x=>x.k===key);if(pos<0)return 0;
 const exp=l3ExpectedGames(league),progress=clip(rec.gp/exp,0,1);if(progress<.40)return 0;
 const top4=arr[Math.min(3,arr.length-1)],safe=arr[Math.max(0,arr.length-4)],drop=arr[Math.max(0,arr.length-3)],leader=arr[0];
 const relBoundary=(safe.pts+drop.pts)/2,gTop=Math.abs(rec.pts-top4.pts),gRel=Math.abs(rec.pts-relBoundary),gTitle=Math.abs(rec.pts-leader.pts);
 return progress*progress*(Math.exp(-gTop/5)+Math.exp(-gRel/5)+.4*Math.exp(-gTitle/5));
}
function l4PoisPmf(k,l){let p=Math.exp(-l);for(let i=1;i<=k;i++)p*=l/i;return p}
function l4ScoreDistribution(lh,la,rho=0,maxGoals=L4_MAX_GOALS){const mat=Array.from({length:maxGoals+1},()=>Array(maxGoals+1).fill(0));let z=0;for(let h=0;h<=maxGoals;h++)for(let a=0;a<=maxGoals;a++){let tau=1;if(h===0&&a===0)tau=1-lh*la*rho;else if(h===0&&a===1)tau=1+lh*rho;else if(h===1&&a===0)tau=1+la*rho;else if(h===1&&a===1)tau=1-rho;tau=Math.max(.02,tau);const p=l4PoisPmf(h,lh)*l4PoisPmf(a,la)*tau;mat[h][a]=p;z+=p}for(let h=0;h<=maxGoals;h++)for(let a=0;a<=maxGoals;a++)mat[h][a]/=z;return mat}
function l4Markets(mat){let H=0,D=0,A=0,o15=0,o25=0,o35=0,btts=0,h05=0,a05=0,h15=0,a15=0,best={h:0,a:0,p:0};for(let h=0;h<mat.length;h++)for(let a=0;a<mat[h].length;a++){const p=mat[h][a],t=h+a;if(h>a)H+=p;else if(h===a)D+=p;else A+=p;if(t>=2)o15+=p;if(t>=3)o25+=p;if(t>=4)o35+=p;if(h>0&&a>0)btts+=p;if(h>=1)h05+=p;if(a>=1)a05+=p;if(h>=2)h15+=p;if(a>=2)a15+=p;if(p>best.p)best={h,a,p}}return {hda:[H,D,A],oneX:H+D,x2:D+A,twelve:H+A,over15:o15,under15:1-o15,over25:o25,under25:1-o25,over35:o35,under35:1-o35,bttsYes:btts,bttsNo:1-btts,homeOver05:h05,awayOver05:a05,homeOver15:h15,awayOver15:a15,mostLikelyScore:best}}
function serPredict(m,r,T=1){if(!m||!m.W||!m.st)return null;let x=(m.featureIdx?m.featureIdx.map(i=>r.vec[i]):r.vec.slice());if(!x.every(Number.isFinite))return null;x=x.map((v,j)=>(v-m.st.mu[j])/Math.max(1e-9,m.st.sd[j]));x=[1,...x];let z=m.W.map(w=>w.reduce((sum,v,j)=>sum+v*x[j],0));if(m.baseModel){const bp=serPredict(m.baseModel,r,1);if(!bp)return null;z=z.map((v,i)=>v+Math.log(Math.max(1e-12,bp[i])))}return softmax(z.map(v=>v/T))}
function serPoissonPredict(m,vec){if(!m||!m.w||!m.st||!Array.isArray(vec)||!vec.every(Number.isFinite))return null;const x=[1,...vec.map((v,j)=>(v-m.st.mu[j])/Math.max(1e-9,m.st.sd[j]))];return Math.exp(clip(m.w.reduce((z,w,j)=>z+w*x[j],0),-3.5,3.2))}
function liveTempPred(p,T){if(!p)return null;return softmax(p.map(v=>Math.log(Math.max(1e-12,v))/T))}
function liveBlendProb(a,b,w){if(!a||!b)return null;return softmax(a.map((v,i)=>(1-w)*Math.log(Math.max(1e-12,v))+w*Math.log(Math.max(1e-12,b[i]))))}
function understatTeamHistory(team,cutDate){return (team?.history||[]).map(x=>({date:String(x.date||'').slice(0,10),npxG:+x.npxG,npxGA:+x.npxGA,deep:+x.deep,deepAllowed:+x.deep_allowed,scored:+x.scored,missed:+x.missed,pts:+x.pts,h_a:x.h_a})).filter(x=>x.date&&x.date<cutDate&&[x.npxG,x.npxGA,x.deep,x.deepAllowed,x.scored,x.missed,x.pts].every(Number.isFinite)).sort((a,b)=>a.date.localeCompare(b.date))}
function liveTablePressureFromPack(pack,key,cutDate,league){const table=new Map();for(const t of pack.teams){const h=understatTeamHistory(t,cutDate),k=perfTeamKey(t.title);if(!k||!h.length)continue;table.set(k,{pts:h.reduce((s,x)=>s+x.pts,0),gf:h.reduce((s,x)=>s+x.scored,0),ga:h.reduce((s,x)=>s+x.missed,0),gp:h.length})}return l3TablePressure(table,key,league)}
function livePerformanceFeatures(pack,fx,structSnap){const H=pack.byKey.get(perfTeamKey(fx.home)),A=pack.byKey.get(perfTeamKey(fx.away));if(!H||!A)return {ok:false,reason:'static performance team identity unresolved'};const hh=understatTeamHistory(H,fx.date),ah=understatTeamHistory(A,fx.date),h=l1AvgHist(hh),a=l1AvgHist(ah);if(!h||!a||h.n<L1_MIN_HISTORY||a.n<L1_MIN_HISTORY)return {ok:false,reason:'fewer than '+L1_MIN_HISTORY+' prior current-season performance matches'};const hLast=hh.at(-1)?.date,aLast=ah.at(-1)?.date;if(daysBetween(hLast,fx.date)>L1_MAX_AGE_DAYS||daysBetween(aLast,fx.date)>L1_MAX_AGE_DAYS)return {ok:false,reason:'current performance state stale'};const rh=h.n/(h.n+L1_SHRINK_PRIOR),ra=a.n/(a.n+L1_SHRINK_PRIOR),hResidual=rh*.5*(h.finish+h.prevent),aResidual=ra*.5*(a.finish+a.prevent),l1Raw={npxGAttackDiff:h.npxG-a.npxG,npxGADefenceDiff:a.npxGA-h.npxGA,deepBalanceDiff:h.deepBal-a.deepBal,finishingConcessionResidualDiff:hResidual-aResidual},extra=[l1Raw.npxGAttackDiff,l1Raw.npxGADefenceDiff,l1Raw.deepBalanceDiff,l1Raw.finishingConcessionResidualDiff];
 const env=[];for(const t of pack.teams)for(const x of understatTeamHistory(t,fx.date))if(x.h_a==='h')env.push({date:x.date,hg:x.scored,ag:x.missed});env.sort((x,y)=>x.date.localeCompare(y.date));const prior=env.slice(-240),envN=prior.length;
 // Early-season L4 must not disappear merely because the current league has <40 completed matches.
 // Use the already-trained Poisson feature scaler's historical mean as the causal league-scoring prior,
 // then shrink the current-season sample toward that prior with the old 40-match stability threshold as
 // a pseudo-count. No future results and no bookmaker information enter this bootstrap.
 const priorHomeEnv=Math.exp(Number(FUSION_DEPLOY?.models?.homePoisson?.st?.mu?.[4]??Math.log(1.45))),priorAwayEnv=Math.exp(Number(FUSION_DEPLOY?.models?.awayPoisson?.st?.mu?.[4]??Math.log(1.15))),envPriorWeight=40,sampleHomeEnv=envN?avg(prior.map(x=>x.hg)):priorHomeEnv,sampleAwayEnv=envN?avg(prior.map(x=>x.ag)):priorAwayEnv,homeEnv=Math.max(.35,(envPriorWeight*priorHomeEnv+envN*sampleHomeEnv)/(envPriorWeight+envN)),awayEnv=Math.max(.25,(envPriorWeight*priorAwayEnv+envN*sampleAwayEnv)/(envPriorWeight+envN)),homeFinish=rh*h.finish,awayFinish=ra*a.finish,homePrevent=rh*h.prevent,awayPrevent=ra*a.prevent,anchor=Number(structSnap?.vec?.[0]);const l4HomeVec=[Math.log(Math.max(.12,h.npxG)),Math.log(Math.max(.12,a.npxGA)),homeFinish,-awayPrevent,Math.log(homeEnv),anchor],l4AwayVec=[Math.log(Math.max(.12,a.npxG)),Math.log(Math.max(.12,h.npxGA)),awayFinish,-homePrevent,Math.log(awayEnv),-anchor];const hk=perfTeamKey(fx.home),ak=perfTeamKey(fx.away),stakesDiff=liveTablePressureFromPack(pack,hk,fx.date,fx.league)-liveTablePressureFromPack(pack,ak,fx.date,fx.league);return {ok:true,extra,l1Raw,l4HomeVec,l4AwayVec,stakesDiff,hLast,aLast,source:'static normalized Understat feed',sourceVia:pack.sourceUrl,feedGeneratedAt:pack.feedGeneratedAt,l4Raw:{homeNpxG:h.npxG,awayNpxG:a.npxG,homeNpxGA:h.npxGA,awayNpxGA:a.npxGA,homeFinish,awayFinish,homePrevent,awayPrevent,homeEnv,awayEnv,scoringEnvSampleMatches:envN,scoringEnvPriorWeight:envPriorWeight,scoringEnvPriorHome:priorHomeEnv,scoringEnvPriorAway:priorAwayEnv,structuralAnchor:anchor}}}
function livePlayerFixtureKey(fx){return `${fx.date}|${perfTeamKey(fx.home)}|${perfTeamKey(fx.away)}`}
async function livePlayerFeatures(fx,signal=null){
 const data=await loadStaticLiveData(signal),features=data.players?.features||{},key=livePlayerFixtureKey(fx);let row=features[key]||null;
 if(!row){const suffix=`|${perfTeamKey(fx.home)}|${perfTeamKey(fx.away)}`,keys=Object.keys(features).filter(k=>k.endsWith(suffix));if(keys.length===1)row=features[keys[0]]}
 if(!row)return {ok:false,reason:'fixture absent from static confirmed-XI feed'};
 if(!row.ok)return {ok:false,reason:row.reason||'confirmed XI not published',eventId:row.eventId||null,feedGeneratedAt:data.manifest.generatedAt};
 const ts=Date.parse(row.fetchedAt||data.manifest.generatedAt),age=Number.isFinite(ts)?(Date.now()-ts)/60000:Infinity,maxAge=+(data.manifest?.freshness?.confirmedXiMaxAgeMinutes||30);if(age>maxAge)return {ok:false,reason:`confirmed-XI feed stale (${age.toFixed(0)} min)`,eventId:row.eventId||null,feedGeneratedAt:data.manifest.generatedAt};
 return {ok:true,eventId:row.eventId,continuityDiff:+row.continuityDiff,replacementQualityAdv:+row.replacementQualityAdv,home:row.homeSnapshot||null,away:row.awaySnapshot||null,source:'static normalized ESPN collector',feedGeneratedAt:data.manifest.generatedAt};
}


export function setDeployment(d){FUSION_DEPLOY=d;}
export { softmax,baseTeamKey,avg,clip,daysBetween,perfTeamKey,l1AvgHist,l3ExpectedGames,l3TablePressure,l4PoisPmf,l4ScoreDistribution,l4Markets,serPredict,serPoissonPredict,liveTempPred,liveBlendProb,understatTeamHistory,liveTablePressureFromPack,livePerformanceFeatures };
