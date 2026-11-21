import test from 'node:test';
import assert from 'node:assert/strict';
import {fixtureKey,originalFixtureProbabilities,validateProjectedFixtures} from '../scripts/hbt_fusion_projection_identity.mjs';

const fixture=(home,probs=[0.5,0.3,0.2])=>({
  fixture:{date:'2026-11-20',league:'es.1',home,away:'Away',},
  probs,structuralFeatures:{vec:Array(11).fill(0)}
});
test('unique original fixture identities preserve L0 probability and structural vector',()=>{
  const original=originalFixtureProbabilities([fixture('Home'),fixture('Other')]);
  assert.equal(validateProjectedFixtures(original,[fixture('Other'),fixture('Home')]).length,2);
});
test('original duplicate and incomplete fixture identities fail closed',()=>{
  assert.throws(()=>originalFixtureProbabilities([fixture('Home'),fixture('Home')]),/Duplicate frozen/);
  assert.throws(()=>originalFixtureProbabilities([{fixture:{date:'2026-11-20'}}]),/Missing or ambiguous/);
  assert.throws(()=>fixtureKey(fixture('Home|Away')),/Missing or ambiguous/);
});
test('projected duplicate identities cannot mask a missing fixture',()=>{
  const original=originalFixtureProbabilities([fixture('Home'),fixture('Other')]);
  assert.throws(()=>validateProjectedFixtures(original,[fixture('Home'),fixture('Home')]),/Duplicate projected/);
  assert.throws(()=>validateProjectedFixtures(original,[fixture('Home')]),/target\/count/);
  assert.throws(()=>validateProjectedFixtures(original,[fixture('Home'),fixture('Unknown')]),/L0 probability changed/);
});
test('projection cannot alter frozen probabilities or invent missing structural features',()=>{
  const original=originalFixtureProbabilities([fixture('Home')]);
  assert.throws(()=>validateProjectedFixtures(original,[fixture('Home',[0.4,0.4,0.2])]),/L0 probability changed/);
  assert.throws(()=>validateProjectedFixtures(original,[{...fixture('Home'),structuralFeatures:{vec:Array(10).fill(0)}}]),/Causal structural vector/);
});

test('invalid frozen L0 probabilities cannot pass unchanged through projection parity',()=>{
  for(const probs of [null,[0.5,0.5],[0.5,0.3,NaN],[0.5,0.3,Infinity],[-0.1,0.6,0.5],[0.6,0.3,0.3],['0.5',0.3,0.2]]){
    assert.throws(()=>originalFixtureProbabilities([fixture('Home',probs)]),/Invalid frozen L0 probabilities/);
  }
});
