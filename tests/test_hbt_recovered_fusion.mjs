import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {verifyRecovery,predictShadow} from '../scripts/hbt_recovered_fusion_shadow.mjs';
import {l4ScoreDistribution,l4Markets,serPredict,understatTeamHistory,perfTeamKey} from '../runtime/hbt_fusion_inference_exact.mjs';

test('persisted deployment is the saved pre-existing model, with explicit research governance',()=>{
  const {deployment,manifest}=verifyRecovery();
  assert.equal(deployment.created,'2026-09-12T11:15:44.195Z');
  assert.equal(manifest.policy.modelPromotionAllowed,false);
  assert.equal(manifest.trainingAudit.reused2019Confirmation,true);
});
test('tampered persisted weights fail recovery before inference',()=>{
  const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'hbt-fusion-test-'));
  try{
    fs.cpSync('runtime',path.join(tmp,'runtime'),{recursive:true});
    fs.appendFileSync(path.join(tmp,'runtime/hbt_frozen_fusion_deployment.json'),' ');
    assert.throws(()=>verifyRecovery(tmp),/hash mismatch/);
  }finally{fs.rmSync(tmp,{recursive:true});}
});
test('score distribution conserves probability and complementary BTTS/totals',()=>{
  const mat=l4ScoreDistribution(1.9,.8,-.05),sm=l4Markets(mat);
  assert.ok(Math.abs(mat.flat().reduce((a,b)=>a+b,0)-1)<1e-12);
  assert.ok(Math.abs(sm.bttsYes+sm.bttsNo-1)<1e-12);
  assert.ok(Math.abs(sm.over25+sm.under25-1)<1e-12);
  assert.ok(sm.over15>sm.over25&&sm.over25>sm.over35);
  const independent=l4Markets(l4ScoreDistribution(1.9,.8,0,25));
  assert.ok(Math.abs(independent.bttsYes-(1-Math.exp(-1.9))*(1-Math.exp(-.8)))<1e-12);
});
test('residual inference correctly composes the saved base and residual logits',()=>{
  const base={W:[[Math.log(2),0],[0,0],[0,0]],st:{mu:[0],sd:[1]},featureIdx:[0]};
  const m={W:[[0,0],[Math.log(2),0],[0,0]],st:{mu:[0],sd:[1]},featureIdx:[0],baseModel:base};
  assert.deepEqual(serPredict(m,{vec:[0]}).map(x=>Math.round(x*10)),[4,4,2]);
  assert.equal(serPredict(m,{vec:[NaN]}),null);
});
test('performance excludes same-day and future outcomes',()=>{
  const r={npxG:1,npxGA:1,deep:1,deep_allowed:1,scored:1,missed:1,pts:1};
  assert.deepEqual(understatTeamHistory({history:[{...r,date:'2026-10-09'},{...r,date:'2026-10-10'},{...r,date:'2026-10-11'}]},'2026-10-10').map(x=>x.date),['2026-10-09']);
});
test('unavailable structural vectors and unsupported leagues cannot invent goal probabilities',()=>{
  const {deployment}=verifyRecovery();
  const pred={fixture:{date:'2026-10-10',time:'19:00',league:'es.1',home:'Real Madrid',away:'Villarreal'}};
  assert.equal(predictShadow(pred,{leagues:{'es.1':{teams:[]}}},{},deployment).reason,'CAUSAL_STRUCTURAL_VECTOR_MISSING');
  assert.equal(predictShadow({...pred,fixture:{...pred.fixture,league:'nl.1'}},{leagues:{}},{},deployment).reason,'PERFORMANCE_LEAGUE_UNSUPPORTED');
});
test('future XI clocks and adjacent-day lineups are never treated as confirmed',()=>{
  const {deployment}=verifyRecovery(),now=new Date('2026-10-10T18:30:00Z');
  const pred={fixture:{date:'2026-10-10',time:'19:00',league:'es.1',home:'Real Madrid',away:'Villarreal'},structuralFeatures:{vec:Array(11).fill(0)},probs:[.4,.3,.3]};
  const history=['2026-10-01','2026-10-02','2026-10-03'].map(date=>({date,npxG:1,npxGA:1,deep:1,deep_allowed:1,scored:1,missed:1,pts:1,h_a:'h'}));
  const performance={generatedAt:'2026-10-10T18:25:00Z',leagues:{'es.1':{teams:[{title:'Real Madrid',history},{title:'Villarreal',history}]}}};
  for(const [date,time] of [['2026-10-10','2026-10-10T18:31:00Z'],['2026-10-09','2026-10-10T18:25:00Z']]){
    const players={features:{[`${date}|${perfTeamKey(pred.fixture.home)}|${perfTeamKey(pred.fixture.away)}`]:{ok:true,home:'Real Madrid',away:'Villarreal',fetchedAt:time,continuityDiff:.1,replacementQualityAdv:.2}}};
    const out=predictShadow(pred,performance,players,deployment,now);
    assert.equal(out.predictionMode,'PRE-XI FUSION');
    assert.equal(out.executionEligible,false);
    assert.equal(out.stakeRand,0);
  }
});
