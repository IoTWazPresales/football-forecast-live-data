#!/usr/bin/env python3
"""Read-only, fail-closed settlement of one Git-pinned recovered Fusion first-add.

A result manifest is human-verified evidence, not a live results feed. This tool
checks its internal consistency and refuses unverifiable or late observations.
No historical data, predictions, prices, stakes, or model parameters are written.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlparse

VALID_LEAGUES = {'en.1', 'es.1', 'de.1', 'it.1', 'fr.1'}
DC = {'1X': (0, 1), 'X2': (1, 2), '12': (0, 2)}


def utc(value):
    if not isinstance(value, str) or not value.endswith('Z'):
        raise ValueError('UTC timestamp with Z required')
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + '+00:00')
    except ValueError as exc:
        raise ValueError('invalid UTC timestamp') from exc
    return parsed.astimezone(dt.timezone.utc)


def probs(p):
    return (isinstance(p, list) and len(p) == 3 and
            all(type(v) in (int, float) and math.isfinite(v) and 0 < v < 1 for v in p) and
            abs(sum(p)-1) < 1e-8)


def git_blob_sha(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def binary(p, actual):
    if type(p) not in (int, float) or not math.isfinite(p) or not 0 < p < 1:
        raise ValueError('invalid binary probability')
    return {'probability': p, 'actual': int(actual),
            'brier': (p-int(actual))**2,
            'logLoss': -math.log(p if actual else 1-p)}


def multiclass(p, actual):
    if not probs(p):
        raise ValueError('invalid 1X2 probabilities')
    return {'probabilities': p, 'actual': actual, 'correctTopPick': p.index(max(p)) == actual,
            'brier': sum((v-int(i == actual))**2 for i,v in enumerate(p)),
            'logLoss': -math.log(p[actual])}


def audit(capture_bytes, manifest):
    if not isinstance(manifest, dict) or manifest.get('schemaVersion') != 'HBT-INDEPENDENT-SETTLEMENT-1':
        raise ValueError('missing independent manifest')
    if git_blob_sha(capture_bytes) != manifest.get('captureGitBlobSha'):
        raise ValueError('capture bytes differ from Git-pinned first-add blob')
    c = json.loads(capture_bytes)
    if c.get('schemaVersion') != 'HBT-FUSION-FIRST-ADD-1':
        raise ValueError('wrong first-add schema')
    f = c.get('forecast') or {}; fx = f.get('fixture') or {}
    key = c.get('fixtureIdentityKey')
    if key != manifest.get('fixtureIdentityKey') or not key.endswith('|P1'):
        raise ValueError('unmatched or non-P1 fixture')
    if fx.get('league') not in VALID_LEAGUES or fx.get('date') != c.get('targetDate'):
        raise ValueError('unsupported competition or date mismatch')
    expected = '|'.join(str(fx.get(k,'')).strip().casefold() for k in ('date','league','home','away'))+'|P1'
    if key != expected or manifest.get('category') != 'senior_men':
        raise ValueError('identity/category unverified')
    if manifest.get('resultStatus') != 'FT_90_VERIFIED' or manifest.get('identityVerified') is not True or manifest.get('kickoffVerified') is not True:
        raise ValueError('regulation-time or independent identity proof missing')
    if manifest.get('captureGitCommit') is None or len(manifest['captureGitCommit']) != 40:
        raise ValueError('commit pin missing')
    if manifest.get('sourceSha256') != c.get('sourceSha256'):
        raise ValueError('source hash provenance mismatch')
    urls = manifest.get('resultSources') or []
    hosts = {urlparse(u).hostname for u in urls if isinstance(u,str) and urlparse(u).scheme == 'https'}
    if len(hosts) < 2 or None in hosts:
        raise ValueError('two independent result source domains required')
    kickoff = utc(manifest.get('kickoffUtc'))
    recorded_kickoff = dt.datetime.fromisoformat(fx['date']+'T'+fx['time']+':00+00:00')
    if kickoff != recorded_kickoff:
        raise ValueError('independent kickoff disagrees with forecast')
    if not (utc(manifest['captureCommitTimeUtc']) <= utc(c['capturedAt']) + dt.timedelta(minutes=1) < kickoff and
            utc(c['sourceGeneratedAt']) <= utc(c['capturedAt']) < kickoff):
        raise ValueError('temporal leakage or unverified capture clock')
    if c.get('policy',{}).get('cleanCalibrationEligible') is not False or f.get('status') != 'RESEARCH_ONLY' or f.get('predictionMode') != 'PRE-XI FUSION':
        raise ValueError('not an unpromoted pre-XI research forecast')
    if f.get('executionEligible') is not False or f.get('diagnostics',{}).get('preKickoff') is not True:
        raise ValueError('forecast eligibility/provenance failed')
    h, a = manifest.get('homeGoals90'), manifest.get('awayGoals90')
    if type(h) is not int or type(a) is not int or min(h,a) < 0:
        raise ValueError('invalid regulation-time score')
    outcome = 0 if h > a else 1 if h == a else 2
    fusion = f.get('probs')
    if not probs(fusion) or f.get('layerPredictions',{}).get('Fusion') != fusion:
        raise ValueError('fusion probability lineage mismatch')
    sm = f.get('scoreMarkets') or {}
    hda = sm.get('hda')
    if not probs(hda) or f.get('layerPredictions',{}).get('L4') != hda:
        raise ValueError('score distribution must be traced to L4, not Fusion 1X2')
    for key2, idx in {'oneX':(0,1), 'x2':(1,2), 'twelve':(0,2)}.items():
        if key2 in sm and abs(sm[key2] - sum(hda[i] for i in idx)) > 1e-8:
            raise ValueError('score-distribution DC inconsistent with L4 hda')
    fusion_dc = {k:binary(sum(fusion[i] for i in inds),outcome in inds) for k,inds in DC.items()}
    actuals = {'oneX':outcome in (0,1), 'x2':outcome in (1,2), 'twelve':outcome in (0,2),
               'bttsYes':h>0 and a>0, 'over15':h+a>=2, 'over25':h+a>=3, 'over35':h+a>=4}
    score_markets = {k:binary(sm[k],v) for k,v in actuals.items() if k in sm}
    return {'fixtureIdentityKey':manifest['fixtureIdentityKey'], 'result90':f'{h}-{a}',
            'cohort':'RESEARCH_ONLY_P1_NOT_CLEAN', 'n':1,
            'fusion1X2':multiclass(fusion,outcome), 'fusionDerivedDC':fusion_dc,
            'L4ScoreDistribution1X2':multiclass(hda,outcome),
            'L4ScoreDistributionMarkets':score_markets,
            'calibration':'NOT_ESTIMABLE_N1', 'r5HypotheticalROI':None,
            'r5ROIReason':'NO_VERIFIED_CONTEMPORANEOUS_ODDS_OR_PREMATCH_SELECTION',
            'bettingEligible':False, 'newTrainingData':False}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--capture',required=True,type=Path)
    ap.add_argument('--manifest',required=True,type=Path)
    args=ap.parse_args()
    print(json.dumps(audit(args.capture.read_bytes(),json.loads(args.manifest.read_text())),indent=2))


if __name__ == '__main__':
    main()
