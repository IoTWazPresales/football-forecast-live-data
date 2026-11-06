#!/usr/bin/env node
/**
 * HBT read-only CI preflight: prove recovered frozen L0-to-Fusion projection,
 * with original frozen card restored even if projection fails.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {buildShadow} from './hbt_recovered_fusion_shadow.mjs';

const sha=(b)=>crypto.createHash('sha256').update(b).digest('hex');
const date=process.argv[process.argv.indexOf('--date')+1];
if(!date||!/^\d{4}-\d{2}-\d{2}$/.test(date))throw Error('Usage: --date YYYY-MM-DD');
const root=process.cwd(),file=path.join(root,'hbt_live_data','frozen_control_forecast_'+date+'.json');
const original=fs.readFileSync(file);
const old=JSON.parse(original);
if(old.targetDate!==date||!Array.isArray(old.predictions))throw Error('Invalid original frozen control');
const keyOf=p=>[p.fixture?.date,p.fixture?.league,p.fixture?.home,p.fixture?.away].join('|');
const originalVectors=new Map(old.predictions.map(p=>[keyOf(p),p.probs]));
const report={schemaVersion:'HBT-FUSION-PROJECTION-PREFLIGHT-1',date,originalSha256:sha(original)};
try {
  const run=spawnSync(process.execPath,['scripts/hbt_frozen_forecast_bridge.mjs','--date',date,'--with-structural-features'],{cwd:root,encoding:'utf8',timeout:150000});
  report.bridgeExitCode=run.status;report.bridgeStdout=(run.stdout||'').slice(-1600);report.bridgeStderr=(run.stderr||'').slice(-1600);
  if(run.status!==0)throw Error('Frozen projection failed: '+(run.stderr||run.stdout));
  const projected=JSON.parse(fs.readFileSync(file,'utf8'));
  if(projected.targetDate!==date||projected.predictions.length!==old.predictions.length)throw Error('Projection altered target/count');
  const projections=[];
  for(const p of projected.predictions) {
    const key=keyOf(p);
    if(!originalVectors.has(key)||JSON.stringify(originalVectors.get(key))!==JSON.stringify(p.probs))throw Error('L0 probability changed for '+key);
    const v=p.structuralFeatures?.vec;
    if(!Array.isArray(v)||v.length!==11||!v.every(Number.isFinite))throw Error('Causal structural vector unavailable: '+key);
    projections.push({fixture:key,structuralVectorLength:v.length});
  }
  report.projectedFixtures=projections;
  const shadow=buildShadow(date,root,new Date());
  report.shadowSummary=shadow.summary;
  report.shadowForecasts=shadow.predictions.map(p=>({fixture:p.fixture,status:p.status,mode:p.predictionMode||null,reason:p.reason||null,hasScoreModel:!!p.scoreMarkets,diagnostics:p.diagnostics||null}));
} catch(e) {
  report.error=String(e);process.exitCode=2;
} finally {
  fs.writeFileSync(file,original);
  report.originalPreserved=sha(fs.readFileSync(file))===report.originalSha256;
  const folder=path.join(root,'hbt_live_data','diagnostics');
  fs.mkdirSync(folder,{recursive:true});
  const output=path.join(folder,'hbt_fusion_projection_preflight_'+date+'.json');
  fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({output,error:report.error||null,projectedFixtures:report.projectedFixtures?.length||0,shadowSummary:report.shadowSummary||null,originalPreserved:report.originalPreserved},null,2));
}
