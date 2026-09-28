#!/usr/bin/env node
/**
 * HBT frozen forecast bridge loader.
 *
 * The implementation payload is stored compressed under runtime/ so the exact
 * audited bridge can be hash-verified before execution. The payload directly
 * hydrates the recovered HBT-0.4a frozen deployment snapshot; it does not fit,
 * retune, or search predictive coefficients.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import zlib from 'node:zlib';
import { spawnSync } from 'node:child_process';

const ROOT = process.cwd();
const parts = [1, 2].map(i => path.join(ROOT, 'runtime', `hbt_frozen_forecast_bridge_exact.b64.part${i}`));
for (const p of parts) {
  if (!fs.existsSync(p)) {
    console.error('HBT exact bridge payload missing', p);
    process.exit(2);
  }
}

const src = zlib.gunzipSync(
  Buffer.from(parts.map(p => fs.readFileSync(p, 'utf8').trim()).join(''), 'base64')
).toString('utf8');
const hash = crypto.createHash('sha256').update(src).digest('hex');
const expected = '1890e458ce87974dbd2e00d013be691cf4ef02231cc85edbff4e2ccfc4294923';
if (hash !== expected) {
  console.error('HBT exact bridge payload hash mismatch', hash);
  process.exit(2);
}

const tmp = path.join(process.env.RUNNER_TEMP || '/tmp', 'hbt_frozen_forecast_bridge_exact.mjs');
fs.writeFileSync(tmp, src);
const check = spawnSync(process.execPath, ['--check', tmp], { cwd: ROOT, stdio: 'inherit' });
if (check.status !== 0) process.exit(check.status || 2);
const run = spawnSync(process.execPath, [tmp, ...process.argv.slice(2)], {
  cwd: ROOT,
  stdio: 'inherit',
  env: process.env,
});
process.exitCode = run.status ?? 2;
