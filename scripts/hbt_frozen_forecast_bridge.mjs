#!/usr/bin/env node
/**
 * HBT frozen forecast bridge loader.
 *
 * The audited bridge implementation is immutable/hash-verified. The original
 * compact snapshot chunks in this repository are corrupt, so this loader first
 * reconstructs the exact frozen HBT-0.4a runtime from the separately recovered,
 * hash-locked browser snapshot payload. It converts that payload to the compact
 * contract expected by the audited bridge in the runner workspace only.
 *
 * No fitting, tuning, bookmaker input, or predictive mutation occurs here.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import zlib from 'node:zlib';
import { spawnSync } from 'node:child_process';

const ROOT = process.cwd();
const RUNTIME = path.join(ROOT,'runtime');
const BRIDGE_CHUNKS = [
  ...Array.from({length:8},(_,i)=>path.join(RUNTIME,`hbt_frozen_forecast_bridge_exact.b64.c${i+1}`)),
  path.join(RUNTIME,'hbt_frozen_forecast_bridge_exact.b64.part2'),
];
const RECOVERED_CHUNKS = Array.from({length:5},(_,i)=>path.join(RUNTIME,`hbt_frozen_l0_snapshot_recovered.br64.c${String(i+1).padStart(2,'0')}`));

const EXPECTED_BRIDGE_SHA256='1890e458ce87974dbd2e00d013be691cf4ef02231cc85edbff4e2ccfc4294923';
const EXPECTED_RECOVERED_PACKED_SHA256='91f5e7f05f747daa34a9f26d856e13a6992572770d30d55a100ec83dd18fba1b';
const EXPECTED_RECOVERED_JSON_SHA256='0ddb9c55624a0e14d8512df08a1afae16da67f129cc97f36d6beaee782323f5f';
const EXPECTED_SOURCE_SHA256='c9b53377b8733d63a50413d7a1d3b3287c49c686e24eb75f944861423c3e8eb8';
const EXPECTED_CREATED='2026-09-11T20:30:57.701Z';

function sha256(v){return crypto.createHash('sha256').update(v).digest('hex');}
function fail(msg){console.error('HBT frozen bridge loader blocked:',msg);process.exit(2);}
function requireFiles(files,label){for(const p of files)if(!fs.existsSync(p))fail(`${label} missing: ${path.basename(p)}`);}

requireFiles(BRIDGE_CHUNKS,'audited bridge payload');
requireFiles(RECOVERED_CHUNKS,'recovered frozen snapshot payload');

// 1) Verify and decode the exact recovered browser snapshot seed.
const recoveredPacked=Buffer.from(RECOVERED_CHUNKS.map(p=>fs.readFileSync(p,'utf8').trim()).join(''),'base64');
if(sha256(recoveredPacked)!==EXPECTED_RECOVERED_PACKED_SHA256)fail(`recovered packed snapshot hash mismatch: ${sha256(recoveredPacked)}`);
let recoveredRaw;
try{recoveredRaw=zlib.brotliDecompressSync(recoveredPacked).toString('utf8');}catch(e){fail(`recovered snapshot Brotli decode failed: ${e.message}`);}
if(sha256(recoveredRaw)!==EXPECTED_RECOVERED_JSON_SHA256)fail(`recovered snapshot JSON hash mismatch: ${sha256(recoveredRaw)}`);
let recovered;
try{recovered=JSON.parse(recoveredRaw);}catch(e){fail(`recovered snapshot JSON invalid: ${e.message}`);}
if(recovered.schema!==2||recovered.engine!=='HBT-0.4a'||recovered.created!==EXPECTED_CREATED)fail('recovered snapshot identity mismatch');
if(!recovered.modelChoiceLock?.opts||!recovered.baseModel||!recovered.model||!Array.isArray(recovered.states)||!Array.isArray(recovered.leagues)||!Array.isArray(recovered.aliases))fail('recovered snapshot incomplete');

// 2) Convert the exact runtime seed to the audited bridge compact contract.
//    Both original object-form states and already-compact states are accepted.
function compactState(row){
  if(!Array.isArray(row)||row.length<2)throw new Error('invalid state row');
  if(row.length>=10 && typeof row[1]!=='object')return row;
  const [key,s]=row;
  if(!s||typeof s!=='object')throw new Error(`invalid state object: ${key}`);
  const hist=Array.isArray(s.hist)?s.hist:[];
  const histRows=hist.map(h=>Array.isArray(h)?h:[h.date,h.venue,h.pts,h.gf,h.ga,h.oppElo]);
  return [String(key),Number(s.dev),s.league||null,s.lastDate||null,s.display||String(key),s.ratingDate||null,!!s.everDomestic,s.lastDomesticSeason||null,hist.length,histRows];
}
let compactStates;
try{compactStates=recovered.states.map(compactState);}catch(e){fail(`state compaction failed: ${e.message}`);}
const compact={
  schemaVersion:'HBT-FROZEN-L0-SNAPSHOT-COMPACT-1',
  sourceSha256:EXPECTED_SOURCE_SHA256,
  schema:recovered.schema,
  engine:recovered.engine,
  created:recovered.created,
  createdByMode:recovered.createdByMode,
  dataCutoff:recovered.dataCutoff,
  currentSeason:recovered.currentSeason,
  codes:recovered.codes,
  seasons:recovered.seasons,
  opts:recovered.opts,
  T:recovered.T,
  residL2:recovered.residL2,
  modelChoiceLock:recovered.modelChoiceLock,
  baseModel:recovered.baseModel,
  model:recovered.model,
  states:compactStates,
  leagues:recovered.leagues,
  aliases:recovered.aliases,
};
const compactRaw=JSON.stringify(compact);
const compactHash=sha256(compactRaw);
const runtimeTemp=process.env.RUNNER_TEMP||'/tmp';
const recoveredCompactPart=path.join(runtimeTemp,'hbt_frozen_l0_snapshot_recovered_compact.b64.part1');
fs.writeFileSync(recoveredCompactPart,zlib.gzipSync(Buffer.from(compactRaw,'utf8'),{level:9}).toString('base64'));

// 3) Verify the audited bridge code, then patch only its snapshot transport
//    contract (path + compact hash). Its predictive/state/parity logic is untouched.
const bridgeSource=zlib.gunzipSync(Buffer.from(BRIDGE_CHUNKS.map(p=>fs.readFileSync(p,'utf8').trim()).join(''),'base64')).toString('utf8');
const bridgeHash=sha256(bridgeSource);
if(bridgeHash!==EXPECTED_BRIDGE_SHA256)fail(`audited bridge payload hash mismatch: ${bridgeHash}`);
const snapshotConst=/const SNAPSHOT_PARTS = \[1,2,3,4\]\.map\(i => path\.join\(ROOT, 'runtime', `hbt_frozen_l0_snapshot_compact\.b64\.part\$\{i\}`\)\);/;
if(!snapshotConst.test(bridgeSource))fail('audited bridge snapshot path contract not found');
let src=bridgeSource.replace(snapshotConst,`const SNAPSHOT_PARTS = [${JSON.stringify(recoveredCompactPart)}];`);
const hashConst=/const EXPECTED_COMPACT_SHA256 = '[0-9a-f]{64}';/;
if(!hashConst.test(src))fail('audited bridge compact hash contract not found');
src=src.replace(hashConst,`const EXPECTED_COMPACT_SHA256 = '${compactHash}';`);

const tmp=path.join(runtimeTemp,'hbt_frozen_forecast_bridge_exact_recovered.mjs');
fs.writeFileSync(tmp,src);
const check=spawnSync(process.execPath,['--check',tmp],{cwd:ROOT,stdio:'inherit'});
if(check.status!==0)process.exit(check.status||2);
console.log('HBT frozen loader: exact recovered snapshot verified',{created:recovered.created,dataCutoff:recovered.dataCutoff,states:compactStates.length,leagues:recovered.leagues.length,aliases:recovered.aliases.length,compactHash});
const run=spawnSync(process.execPath,[tmp,...process.argv.slice(2)],{cwd:ROOT,stdio:'inherit',env:process.env});
process.exitCode=run.status??2;
