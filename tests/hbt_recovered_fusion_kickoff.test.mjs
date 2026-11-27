import test from 'node:test';
import assert from 'node:assert/strict';
import {predictShadow} from '../scripts/hbt_recovered_fusion_shadow.mjs';

const performance={
  generatedAt:'2026-11-01T00:00:00Z',
  leagues:{'eng.1':{teams:[
    {title:'Arsenal',history:[]},
    {title:'Chelsea',history:[]}
  ]}}
};
const now=new Date('2026-11-21T12:00:00Z');
const base={league:'eng.1',home:'Arsenal',away:'Chelsea',date:'2026-11-22',time:'15:00'};
for(const [date,time] of [
  ['2026-02-30','15:00'],
  ['2026-11-22','24:00'],
  ['2026-11-22','15:60'],
  ['2026-11-22','15:00+02:00'],
  ['2026-11-22','15:00:00']
]){
  test(`reject unverifiable kickoff ${date} ${time}`,()=>{
    const result=predictShadow({fixture:{...base,date,time},structuralFeatures:{vec:Array(11).fill(0)}},performance,{features:{}},{},now);
    assert.equal(result.status,'UNAVAILABLE');
    assert.equal(result.reason,'FIXTURE_KICKOFF_UTC_UNVERIFIABLE');
  });
}
