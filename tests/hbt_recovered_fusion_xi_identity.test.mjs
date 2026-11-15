import test from 'node:test';
import assert from 'node:assert/strict';
import {confirmedXiIdentity} from '../scripts/hbt_recovered_fusion_shadow.mjs';

const fixture={league:'en.1',eventId:'401879242'};
test('confirmed XI requires exact competition identity',()=>{
 assert.equal(confirmedXiIdentity(fixture,{league:'en.1',eventId:'401879242'}),true);
 assert.equal(confirmedXiIdentity(fixture,{league:'es.1',eventId:'401879242'}),false);
 assert.equal(confirmedXiIdentity(fixture,{eventId:'401879242'}),false);
 assert.equal(confirmedXiIdentity({league:'en.1'},{league:'en.1',eventId:'401879242'}),true);
});
test('confirmed XI rejects conflicting provider event identity',()=>{
 assert.equal(confirmedXiIdentity(fixture,{league:'en.1',eventId:'401879243'}),false);
 assert.equal(confirmedXiIdentity(fixture,{league:'en.1'}),false);
 assert.equal(confirmedXiIdentity({league:'en.1',eventId:401879242},{league:'en.1',eventId:'401879242'}),true);
});
test('confirmed XI fails closed for malformed fixture and record',()=>{
 assert.equal(confirmedXiIdentity(null,{league:'en.1'}),false);
 assert.equal(confirmedXiIdentity({league:''},{league:''}),false);
 assert.equal(confirmedXiIdentity({league:'en.1'},null),false);
});
