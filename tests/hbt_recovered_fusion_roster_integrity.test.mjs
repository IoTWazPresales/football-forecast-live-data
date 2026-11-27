import test from 'node:test';
import assert from 'node:assert/strict';
import {predictShadow} from '../scripts/hbt_recovered_fusion_shadow.mjs';

const fixture={league:'eng.1',home:'Arsenal',away:'Chelsea',date:'2026-11-24',time:'15:00',eventId:'test-event'};
const prediction={fixture,structuralFeatures:{vec:Array(11).fill(0)}};
const now=new Date('2026-11-23T12:00:00Z');

test('malformed performance rosters fail per fixture without inference or slate crash',()=>{
  for(const teams of [undefined,null,{},'Arsenal', [{title:'Arsenal'},null], [{title:'Arsenal'},{title:42}], [{title:'Arsenal'},{}]]){
    const performance={generatedAt:'2026-11-22T12:00:00Z',leagues:{'eng.1':{teams}}};
    const out=predictShadow(prediction,performance,{features:{}},{},now);
    assert.equal(out.status,'UNAVAILABLE');
    assert.equal(out.reason,'PERFORMANCE_TEAM_ROSTER_UNVERIFIABLE');
    assert.equal(out.scoreMarkets,undefined);
    assert.equal(out.probs,undefined);
  }
});

test('well-formed roster proceeds past roster gate to causal feed validation',()=>{
  const performance={generatedAt:'2026-11-25T12:00:00Z',leagues:{'eng.1':{teams:[{title:'Arsenal',history:[]},{title:'Chelsea',history:[]}]}}};
  const out=predictShadow(prediction,performance,{features:{}},{},now);
  assert.equal(out.reason,'PERFORMANCE_FEED_AS_OF_UNVERIFIABLE');
});
