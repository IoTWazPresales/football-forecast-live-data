import test from 'node:test';
import assert from 'node:assert/strict';
import {predictShadow} from '../scripts/hbt_recovered_fusion_shadow.mjs';

const fixture={date:'2026-11-07',time:'15:00',league:'en.1',home:'Alpha FC',away:'Beta FC'};
const prediction={fixture,structuralFeatures:{vec:Array(11).fill(0)}};
const teams=[{title:'Alpha FC',history:[]},{title:'Beta FC',history:[]}];
const performance=(entries=teams,generatedAt='2026-11-06T12:00:00Z')=>({generatedAt,leagues:{'en.1':{teams:entries}}});
const now=new Date('2026-11-06T13:00:00Z');

test('recovered Fusion rejects colliding normalized home identities',()=>{
 const result=predictShadow(prediction,performance([...teams,{title:'Alpha'}]),{}, {},now);
 assert.equal(result.status,'UNAVAILABLE');
 assert.equal(result.reason,'PERFORMANCE_TEAM_IDENTITY_AMBIGUOUS');
 assert.equal(result.diagnostics.homeMatches,2);
});
test('recovered Fusion rejects missing or same-team identities',()=>{
 const missing=predictShadow(prediction,performance([teams[0]]),{}, {},now);
 assert.equal(missing.reason,'PERFORMANCE_TEAM_IDENTITY_AMBIGUOUS');
 const same=predictShadow({...prediction,fixture:{...fixture,away:'Alpha'}},performance(),{}, {},now);
 assert.equal(same.reason,'PERFORMANCE_TEAM_IDENTITY_AMBIGUOUS');
});
test('recovered Fusion rejects performance generated after kickoff',()=>{
 const result=predictShadow(prediction,performance(teams,'2026-11-07T15:01:00Z'),{}, {},new Date('2026-11-07T16:00:00Z'));
 assert.equal(result.reason,'PERFORMANCE_FEED_AS_OF_UNVERIFIABLE');
});
test('recovered Fusion rejects future-dated and missing feed clocks',()=>{
 assert.equal(predictShadow(prediction,performance(teams,'2026-11-06T14:00:00Z'),{}, {},now).reason,'PERFORMANCE_FEED_AS_OF_UNVERIFIABLE');
 assert.equal(predictShadow(prediction,performance(teams,null),{}, {},now).reason,'PERFORMANCE_FEED_AS_OF_UNVERIFIABLE');
});
test('unambiguous pre-kickoff feed passes identity guard and reaches history gate',()=>{
 const result=predictShadow(prediction,performance(),{}, {},now);
 assert.equal(result.status,'UNAVAILABLE');
 assert.match(result.reason,/prior current-season performance matches/);
});
