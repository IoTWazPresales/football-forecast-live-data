import test from 'node:test';
import assert from 'node:assert/strict';
import {confirmedXiFeedCausal} from '../scripts/hbt_recovered_fusion_shadow.mjs';

const kickoff=Date.parse('2026-11-07T15:00:00Z');
const now=Date.parse('2026-11-07T14:50:00Z');
const record={fetchedAt:'2026-11-07T14:40:00Z'};
const players={generatedAt:'2026-11-07T14:45:00Z'};

test('confirmed XI requires independently causal record and snapshot clocks',()=>{
  assert.equal(confirmedXiFeedCausal(players,record,kickoff,now),true);
});
test('rejects player snapshot generated after kickoff or after evaluation',()=>{
  assert.equal(confirmedXiFeedCausal({generatedAt:'2026-11-07T15:01:00Z'},record,kickoff,Date.parse('2026-11-07T16:00:00Z')),false);
  assert.equal(confirmedXiFeedCausal({generatedAt:'2026-11-07T14:51:00Z'},record,kickoff,now),false);
});
test('rejects event record later than the feed snapshot',()=>{
  assert.equal(confirmedXiFeedCausal({generatedAt:'2026-11-07T14:30:00Z'},record,kickoff,now),false);
});
test('rejects missing, malformed and timezone-naive feed provenance',()=>{
  for(const generatedAt of [null,undefined,'2026-11-07T14:45:00','invalid'])
    assert.equal(confirmedXiFeedCausal({generatedAt},record,kickoff,now),false);
  assert.equal(confirmedXiFeedCausal(players,{fetchedAt:'2026-11-07T14:40:00'},kickoff,now),false);
  assert.equal(confirmedXiFeedCausal(players,record,NaN,now),false);
});
