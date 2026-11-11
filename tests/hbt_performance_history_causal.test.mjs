import test from 'node:test';
import assert from 'node:assert/strict';
import {performanceHistoryCausal} from '../scripts/hbt_recovered_fusion_shadow.mjs';

const teams = dates => [{history: dates.map(date => ({date}))}];

test('historical results strictly precede feed UTC date', () => {
  assert.equal(performanceHistoryCausal(teams(['2026-11-08']), '2026-11-10T12:00:00Z'), true);
  assert.equal(performanceHistoryCausal(teams(['2026-11-10']), '2026-11-10T12:00:00Z'), false);
  assert.equal(performanceHistoryCausal(teams(['2026-11-11']), '2026-11-10T12:00:00Z'), false);
});

test('UTC day is computed from offset-aware feed instant, not string prefix', () => {
  assert.equal(performanceHistoryCausal(teams(['2026-11-10']), '2026-11-11T00:30:00+02:00'), false);
  assert.equal(performanceHistoryCausal(teams(['2026-11-10']), '2026-11-10T23:30:00-02:00'), true);
});

test('malformed or absent history provenance fails closed', () => {
  assert.equal(performanceHistoryCausal([{history:[{date:'2026-02-30'}]}], '2026-11-10T12:00:00Z'), false);
  assert.equal(performanceHistoryCausal([{history:[{}]}], '2026-11-10T12:00:00Z'), false);
  assert.equal(performanceHistoryCausal([{history:[]}], 'invalid'), false);
});
