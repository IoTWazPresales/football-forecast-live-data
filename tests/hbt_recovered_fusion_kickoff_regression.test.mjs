import test from 'node:test';
import assert from 'node:assert/strict';
import {predictShadow} from '../scripts/hbt_recovered_fusion_shadow.mjs';

// Fail closed before model inference: an invalid UTC kickoff cannot be used
// to select performance history or confirmed-XI observations.
const now=new Date('2026-11-22T12:00:00Z');
const teams=[
  {title:'Alpha FC',history:[]},
  {title:'Beta FC',history:[]},
];
const performance={
  generatedAt:'2026-11-20T12:00:00Z',
  leagues:{'Test League':{teams}},
};
const players={features:{},generatedAt:'2026-11-20T12:00:00Z'};
const pred=(date,time)=>({
  fixture:{league:'Test League',home:'Alpha FC',away:'Beta FC',date,time,eventId:'event-1'},
  structuralFeatures:{vec:Array(11).fill(0)},
});

test('recovered Fusion rejects malformed UTC fixture kickoffs before inference',()=>{
  for(const [date,time] of [
    ['2026-02-30','12:00'],
    ['2026-13-01','12:00'],
    ['2026-11-22','24:00'],
    ['2026-11-22','12:60'],
    ['2026-11-22','12:00Z'],
    ['2026-11-22','12:00+02:00'],
    ['2026-11-22','12:00:30'],
    ['2026-11-22','not-a-time'],
  ]){
    const result=predictShadow(pred(date,time),performance,players,{},now);
    assert.equal(result.status,'UNAVAILABLE',date+' '+time);
    assert.equal(result.reason,'FIXTURE_KICKOFF_UTC_UNVERIFIABLE',date+' '+time);
    assert.equal(result.scoreMarkets,undefined);
  }
});
