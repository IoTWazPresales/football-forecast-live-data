#!/usr/bin/env node
/** Restore existing Fusion inference downstream of the immutable L0 control.
 * Outputs are research forecasts. No weights are trained or promoted here.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {setDeployment,perfTeamKey,livePerformanceFeatures,serPredict,
  serPoissonPredict,liveTempPred,liveBlendProb,l4ScoreDistribution,l4Markets} from '../runtime/hbt_fusion_inference_exact.mjs';

const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const aware=s=>typeof s==='string' && /(?:Z|[+-]\d\d:\d\d)$/.test(s) && Number.isFinite(Date.parse(s));
const vector=(p,n=3)=>Array.isArray(p)&&p.length===n&&p.every(Number.isFinite);
const probability=p=>vector(p)&&p.every(x=>x>=0&&x<=1)&&Math.abs(p.reduce((a,b)=>a+b,0)-1)<1e-9;

export function verifyRecovery(root=ROOT){
  const manifest=read(path.join(root,'runtime/hbt_fusion_recovery_manifest.json'));
  for(const [name,expected] of Object.entries(manifest.files)){
    if(path.basename(name)!==name)throw Error('Recovery path invalid');
    if(sha(fs.readFileSync(path.join(root,'runtime',name)))!==expected)throw Error(`Recovery hash mismatch: ${name}`);
  }
  const deployment=read(path.join(root,'runtime/hbt_frozen_fusion_deployment.json'));
  if(deployment.created!==manifest.deploymentCreated)throw Error('Deployment identity mismatch');
  function model(m,poisson=false){
    const n=m?.st?.mu?.length;
    if(!n||!vector(m.st.mu,n)||!vector(m.st.sd,n)||m.st.sd.some(x=>x<=0))throw Error('Invalid model scaler');
    if(poisson){if(!vector(m.w,n+1))throw Error('Invalid Poisson coefficients');}
    else{
      if(!Array.isArray(m.W)||m.W.length!==3||m.W.some(w=>!vector(w,n+1)))throw Error('Invalid classifier coefficients');
      if(m.featureIdx&&(!Array.isArray(m.featureIdx)||m.featureIdx.length!==n||m.featureIdx.some(x=>!Number.isInteger(x)||x<0)))throw Error('Invalid feature indexes');
      if(m.baseModel)model(m.baseModel);
    }
  }
  for(const k of ['l1','fullCore','preXiCore'])model(deployment.models[k]);
  for(const k of ['homePoisson','awayPoisson'])model(deployment.models[k],true);
  const cfg=deployment.modelParameters;
  for(const k of ['full','preXi']){
    if(!Number.isFinite(cfg[k]?.coreTemperature)||cfg[k].coreTemperature<=0||!Number.isFinite(cfg[k].finalTemperature)||cfg[k].finalTemperature<=0||!Number.isFinite(cfg[k].l4BlendWeight)||cfg[k].l4BlendWeight<0||cfg[k].l4BlendWeight>1)throw Error('Invalid stack parameters');
  }
  setDeployment(deployment);
  return {deployment,manifest};
}

export function predictShadow(pred,performance,players,deployment,now=new Date()){
  const fx=pred.fixture,src=performance.leagues?.[fx.league];
  if(!src)return {fixture:fx,status:'UNAVAILABLE',reason:'PERFORMANCE_LEAGUE_UNSUPPORTED'};
  if(!vector(pred.structuralFeatures?.vec,11))return {fixture:fx,status:'UNAVAILABLE',reason:'CAUSAL_STRUCTURAL_VECTOR_MISSING'};
  const pack={teams:src.teams||[],byKey:new Map((src.teams||[]).map(t=>[perfTeamKey(t.title),t])),sourceUrl:src.source||null,feedGeneratedAt:performance.generatedAt};
  const perf=livePerformanceFeatures(pack,fx,pred.structuralFeatures);
  if(!perf.ok)return {fixture:fx,status:'UNAVAILABLE',reason:perf.reason};
  const baseVec=[...pred.structuralFeatures.vec,...perf.extra];
  const l1=serPredict(deployment.models.l1,{vec:baseVec},deployment.modelParameters.l1Temperature);
  const lh=serPoissonPredict(deployment.models.homePoisson,perf.l4HomeVec),la=serPoissonPredict(deployment.models.awayPoisson,perf.l4AwayVec);
  if(!probability(l1)||![lh,la].every(x=>Number.isFinite(x)&&x>0))throw Error('Nonfinite recovered inference');
  const cfg=deployment.modelParameters,sm=l4Markets(l4ScoreDistribution(lh*cfg.l4Lock.goalScale,la*cfg.l4Lock.goalScale,cfg.l4Lock.dixonColesRho));
  // Match only this date and both identities; never reuse an adjacent day's XI.
  const matching=Object.entries(players.features||{}).filter(([key,r])=>key.split('|')[0]===fx.date&&perfTeamKey(r.home)===perfTeamKey(fx.home)&&perfTeamKey(r.away)===perfTeamKey(fx.away));
  const xi=matching.length===1?matching[0][1]:null;
  const xiAge=aware(xi?.fetchedAt)?(now-Date.parse(xi.fetchedAt))/60000:Infinity;
  const full=xi?.ok===true&&xiAge>=0&&xiAge<=30&&[xi.continuityDiff,xi.replacementQualityAdv].every(Number.isFinite);
  const row={vec:[...baseVec,full?xi.continuityDiff:0,full?xi.replacementQualityAdv:0,0,perf.stakesDiff]};
  const setting=full?cfg.full:cfg.preXi,core=liveTempPred(serPredict(full?deployment.models.fullCore:deployment.models.preXiCore,row,1),setting.coreTemperature);
  const probs=liveTempPred(liveBlendProb(core,sm.hda,setting.l4BlendWeight),setting.finalTemperature);
  if(!probability(probs)||!probability(sm.hda))throw Error('Invalid recovered probabilities');
  const age=aware(performance.generatedAt)?(now-Date.parse(performance.generatedAt))/60000:Infinity;
  const ko=Date.parse(`${fx.date}T${fx.time}:00Z`);
  return {fixture:fx,status:'RESEARCH_ONLY',predictionMode:full?'CONFIRMED-XI FUSION':'PRE-XI FUSION',probs,layerPredictions:{L0:pred.probs,L1:l1,L4:sm.hda,Fusion:probs},scoreMarkets:sm,
    inputFeatures:{structural:pred.structuralFeatures.vec,performance:perf.extra,context:row.vec.slice(15),homeScore:perf.l4HomeVec,awayScore:perf.l4AwayVec},
    diagnostics:{performanceFeedAgeMinutes:Number.isFinite(age)?age:null,performanceFeedCurrent:age>=0&&age<=30,confirmedXi:full,xiReason:full?null:xi?.reason||'confirmed XI unavailable',preKickoff:Number.isFinite(ko)&&ko>now},
    executionEligible:false,blockers:['RECOVERED_FUSION_VALUE_CALIBRATION_UNVALIDATED','RESEARCH_RUNTIME_NOT_PROMOTED'],stakeRand:0};
}

export function buildShadow(date,root=ROOT,now=new Date()){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(date))throw Error('Date invalid');
  const {deployment,manifest}=verifyRecovery(root),data=path.join(root,'hbt_live_data');
  const paths={control:path.join(data,`frozen_control_forecast_${date}.json`),performance:path.join(data,'performance.json'),players:path.join(data,'player_features.json'),deployment:path.join(root,'runtime/hbt_frozen_fusion_deployment.json')};
  const control=read(paths.control),performance=read(paths.performance),players=read(paths.players);
  if(control.targetDate!==date||control.bridge?.snapshotCreated!==manifest.liveL0Reference.snapshotCreated||!Number.isFinite(control.bridge.goldenMaxAbsError)||control.bridge.goldenMaxAbsError>1e-9)throw Error('Recovered L0 lineage/parity unproven');
  const predictions=control.predictions.map(p=>predictShadow(p,performance,players,deployment,now));
  return {schemaVersion:'HBT-RECOVERED-FUSION-SHADOW-1',targetDate:date,generatedAt:now.toISOString(),policy:{bookmakerOddsUsedAsFeature:false,retrainingPerformed:false,retuningPerformed:false,modelPromotionAllowed:false,executionAllowed:false,controlForecastUnchanged:true},
    sourceFiles:Object.fromEntries(Object.entries(paths).map(([k,p])=>[k,path.relative(root,p)])),sourceHashes:Object.fromEntries(Object.entries(paths).map(([k,p])=>[k,sha(fs.readFileSync(p))])),deploymentCreated:deployment.created,
    validation:deployment.validation,validationLimits:['2019 confirmation was reused; it is not a new untouched holdout','Historical raw model-versus-bookmaker EV failed its earlier value audit','Recovered inference is not current execution validation'],
    predictions,summary:{fixtures:predictions.length,scoreDistributions:predictions.filter(p=>p.scoreMarkets).length,futureScoreDistributions:predictions.filter(p=>p.scoreMarkets&&p.diagnostics.preKickoff).length,confirmedXiFusion:predictions.filter(p=>p.diagnostics?.confirmedXi).length,readyBets:0}};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  try{const date=process.argv[process.argv.indexOf('--date')+1];const out=buildShadow(date);fs.writeFileSync(path.join(ROOT,'hbt_live_data',`hbt_recovered_fusion_shadow_${date}.json`),JSON.stringify(out,null,2)+'\n');console.log(JSON.stringify(out.summary));}
  catch(e){console.error('Recovered Fusion shadow blocked:',e.message);process.exitCode=2;}
}
