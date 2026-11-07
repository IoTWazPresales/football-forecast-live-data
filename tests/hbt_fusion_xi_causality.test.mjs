import test from 'node:test';
import assert from 'node:assert/strict';
import {confirmedXiCausal} from '../scripts/hbt_recovered_fusion_shadow.mjs';

const kickoff=Date.parse('2026-11-07T18:00:00Z');
const now=Date.parse('2026-11-07T19:00:00Z');

test('pre-kickoff XI is causally eligible',()=>{
  assert.equal(confirmedXiCausal('2026-11-07T17:45:00Z',kickoff,now),true);
});
test('post-kickoff XI is rejected even on historical replay',()=>{
  assert.equal(confirmedXiCausal('2026-11-07T18:01:00Z',kickoff,now),false);
});
test('future XI relative to observation is rejected',()=>{
  assert.equal(confirmedXiCausal('2026-11-07T17:45:00Z',kickoff,Date.parse('2026-11-07T17:40:00Z')),false);
});
test('ambiguous timestamps and invalid clocks fail closed',()=>{
  for(const stamp of [null,'2026-11-07T17:45:00','not-a-date']){
    assert.equal(confirmedXiCausal(stamp,kickoff,now),false);
  }
  assert.equal(confirmedXiCausal('2026-11-07T17:45:00Z',NaN,now),false);
});
