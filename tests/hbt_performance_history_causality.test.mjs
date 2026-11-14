import test from 'node:test';
import assert from 'node:assert/strict';
import {performanceHistoryCausal,causalLeagueHistory} from '../scripts/hbt_recovered_fusion_shadow.mjs';

const row=date=>({date});
test('completed history strictly before feed UTC day is permitted',()=>{
  assert.equal(performanceHistoryCausal([{history:[row('2026-11-01'),row('2026-11-06')]}],'2026-11-07T12:00:00Z'),true);
});
test('same-day date-only history is rejected without final-whistle evidence',()=>{
  assert.equal(performanceHistoryCausal([{history:[row('2026-11-07')]}],'2026-11-07T23:59:00Z'),false);
});
test('future match history cannot enter a past feed snapshot',()=>{
  assert.equal(performanceHistoryCausal([{history:[row('2026-11-08')]}],'2026-11-07T12:00:00Z'),false);
});
test('missing and malformed dates fail closed',()=>{
  for(const date of ['',null,'not-a-date','2026-99-99'])assert.equal(performanceHistoryCausal([{history:[row(date)]}],'2026-11-07T12:00:00Z'),false);
});
test('missing history provenance fails closed',()=>{
  assert.equal(performanceHistoryCausal([{}],'2026-11-07T12:00:00Z'),false);
  assert.equal(performanceHistoryCausal([{history:[]}],'not-a-timestamp'),false);
});

test('league scoring environment excludes unrelated clubs results after feed generation',()=>{
  const input=[{title:'Home',history:[row('2026-11-05')]},
    {title:'Other',history:[row('2026-11-05'),row('2026-11-07'),row('2026-11-08')]}];
  const filtered=causalLeagueHistory(input,'2026-11-07T12:00:00Z');
  assert.deepEqual(filtered[1].history,[row('2026-11-05')]);
  assert.deepEqual(input[1].history,[row('2026-11-05'),row('2026-11-07'),row('2026-11-08')]);
});
test('league history excludes invalid dates and fails closed on invalid feed timestamp',()=>{
  const input=[{title:'Other',history:[row('2026-02-30'),row('invalid'),row('2026-11-01')]}];
  assert.deepEqual(causalLeagueHistory(input,'2026-11-07T12:00:00+02:00')[0].history,[row('2026-11-01')]);
  assert.deepEqual(causalLeagueHistory(input,'invalid'),[]);
});
