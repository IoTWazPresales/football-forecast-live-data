#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
const ROOT=path.resolve(import.meta.dirname,'..');
const chunks=[...Array.from({length:8},(_,i)=>path.join(ROOT,'runtime',`hbt_frozen_forecast_bridge_exact.b64.c${i+1}`)),path.join(ROOT,'runtime','hbt_frozen_forecast_bridge_exact.b64.part2')];
const src=zlib.gunzipSync(Buffer.from(chunks.map(p=>fs.readFileSync(p,'utf8').trim()).join(''),'base64')).toString('utf8');
const needles=['function readExactFrozenSnapshot','readExactFrozenSnapshot(','SNAPSHOT','snapshot_exact','frozen_l0_snapshot'];
for(const n of needles){const i=src.indexOf(n);if(i>=0){console.log(`--- ${n} @ ${i} ---`);console.log(src.slice(Math.max(0,i-1500),Math.min(src.length,i+5000)));}}
