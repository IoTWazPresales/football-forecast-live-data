#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import zlib from 'node:zlib';

const ROOT = path.resolve(import.meta.dirname, '..');
const RUNTIME = path.join(ROOT, 'runtime');
const DATA = path.join(ROOT, 'hbt_live_data');
const OUT = path.join(DATA, 'frozen_snapshot_chunk_probe.json');

function sha256(buf) { return crypto.createHash('sha256').update(buf).digest('hex'); }
function list(prefix) {
  return fs.readdirSync(RUNTIME).filter(x => x.startsWith(prefix)).sort((a,b) => a.localeCompare(b, undefined, {numeric:true}));
}
function tryJson(buf) {
  try {
    const d = JSON.parse(buf.toString('utf8'));
    return {ok:true,engine:d.engine??d.e??null,schema:d.schema??d.s??null,created:d.created??d.c??null,dataCutoff:d.dataCutoff??d.d??null,states:Array.isArray(d.states)?d.states.length:(Array.isArray(d.x)?d.x.length:null),leagues:Array.isArray(d.leagues)?d.leagues.length:(Array.isArray(d.g)?d.g.length:null),aliases:Array.isArray(d.aliases)?d.aliases.length:(Array.isArray(d.a)?d.a.length:null)};
  } catch (e) { return {ok:false,error:String(e.message||e)}; }
}
function probe(prefix, expected={}) {
  const files=list(prefix), text=files.map(f=>fs.readFileSync(path.join(RUNTIME,f),'utf8').trim()).join('');
  const report={prefix,files,chunkCount:files.length,textChars:text.length,chunkSizes:files.map(f=>fs.statSync(path.join(RUNTIME,f)).size)};
  if(!text)return {...report,status:'EMPTY'};
  let packed;
  try{packed=Buffer.from(text,'base64');}catch(e){return {...report,status:'BAD_BASE64',error:String(e.message||e)};}
  report.packedBytes=packed.length; report.packedSha256=sha256(packed); report.packedHeadHex=packed.subarray(0,16).toString('hex');
  const methods=[['raw',b=>b],['gunzip',b=>zlib.gunzipSync(b)],['unzip',b=>zlib.unzipSync(b)],['inflate',b=>zlib.inflateSync(b)],['inflateRaw',b=>zlib.inflateRawSync(b)],['brotli',b=>zlib.brotliDecompressSync(b)]];
  const attempts=[];
  for(const [name,fn] of methods){try{const out=fn(packed);attempts.push({method:name,decompressedBytes:out.length,sha256:sha256(out),json:tryJson(out)});}catch(e){attempts.push({method:name,ok:false,error:String(e.message||e)});}}
  report.attempts=attempts; report.status=attempts.some(x=>x.json?.ok)?'DECODED_JSON':'NO_VALID_JSON';
  if(expected.packedSha256) report.packedHashMatch=report.packedSha256===expected.packedSha256;
  if(expected.jsonSha256){const good=attempts.find(x=>x.json?.ok);report.jsonHashMatch=good?.sha256===expected.jsonSha256;}
  return report;
}
const output={schemaVersion:'HBT-FROZEN-SNAPSHOT-CHUNK-PROBE-2',generatedAt:new Date().toISOString(),mutation:false,probes:[
  probe('hbt_frozen_l0_snapshot_recovered.br64.',{packedSha256:'91f5e7f05f747daa34a9f26d856e13a6992572770d30d55a100ec83dd18fba1b',jsonSha256:'0ddb9c55624a0e14d8512df08a1afae16da67f129cc97f36d6beaee782323f5f'}),
  probe('hbt_frozen_l0_snapshot_exact.b64.'),
  probe('hbt_frozen_l0_snapshot_compact.b64.'),
]};
fs.mkdirSync(DATA,{recursive:true});fs.writeFileSync(OUT,JSON.stringify(output,null,2)+'\n');console.log(JSON.stringify(output,null,2));
