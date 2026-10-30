#!/usr/bin/env python3
"""Preserve first pre-kickoff recovered-Fusion P1/P2 evidence, fail closed.

This is a research-only source sidecar; it never changes HBT L0 forecasts,
trained coefficients, wagers, R1/R2 decisions or bookmaker prices.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

VERSION='HBT-FUSION-FIRST-ADD-1'
SUPPORTED={'en.1','es.1','de.1','it.1','fr.1'}

def parse_utc(value):
    if not isinstance(value,str) or not value.endswith('Z'):
        raise ValueError('UTC time with explicit Z required')
    stamp=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    if stamp.tzinfo is None:raise ValueError('naive timestamp')
    return stamp.astimezone(dt.timezone.utc)

def valid_probs(values):
    return (isinstance(values,list) and len(values)==3 and
        all(type(p) in (int,float) and math.isfinite(p) and 0<p<1 for p in values) and
        abs(sum(values)-1)<1e-9)

def fixture_key(f):
    return '|'.join(str(f[k]).strip().casefold() for k in ('date','league','home','away'))

def capture(root:Path, target:str, *,now=None):
    dt.date.fromisoformat(target)
    root=Path(root)
    src=root/f'hbt_recovered_fusion_shadow_{target}.json'
    blob=src.read_bytes()
    shadow=json.loads(blob)
    policy=shadow.get('policy') or {}
    if shadow.get('schemaVersion')!='HBT-RECOVERED-FUSION-SHADOW-1' or shadow.get('targetDate')!=target:
        raise ValueError('wrong source date or schema')
    if policy.get('retrainingPerformed') is not False or policy.get('controlForecastUnchanged') is not True or policy.get('executionAllowed') is not False:
        raise ValueError('unverified frozen-model policy: refusing capture')
    generated=parse_utc(shadow['generatedAt'])
    now=now or dt.datetime.now(dt.timezone.utc)
    if generated>now+dt.timedelta(minutes=1):raise ValueError('source clock in the future')
    if now-generated>dt.timedelta(minutes=15):
        raise ValueError('stale source file: first-add cannot be backfilled from a later run')
    source_hash=hashlib.sha256(blob).hexdigest()
    outdir=root/'captures'/'fusion'
    saved=[];preserved=[];excluded=[];seen=set()
    for pred in shadow.get('predictions') or []:
        f=pred.get('fixture') or {}
        if pred.get('status')!='RESEARCH_ONLY':
            excluded.append({'fixture':f,'reason':'NOT_A_FUSION_FORECAST'});continue
        try:
            if f.get('date')!=target or f.get('league') not in SUPPORTED or not all(f.get(k) for k in ('home','away','time')):
                raise ValueError('UNSUPPORTED_OR_UNVERIFIED_FIXTURE_IDENTITY')
            clock=str(f['time'])
            if len(clock)!=5 or clock[2]!=':':raise ValueError('INVALID_UTC_KICKOFF')
            kickoff=dt.datetime.fromisoformat(f'{target}T{clock}:00+00:00')
            if kickoff-generated<=dt.timedelta(minutes=1) or kickoff-now<=dt.timedelta(minutes=1):
                raise ValueError('POST_KICKOFF_OR_TOO_LATE')
            if not (pred.get('diagnostics') or {}).get('preKickoff') is True:
                raise ValueError('SOURCE_MARKED_POST_KICKOFF')
            if not (pred.get('diagnostics') or {}).get('performanceFeedCurrent') is True:
                raise ValueError('PERFORMANCE_FEED_NOT_CURRENT')
            if not valid_probs(pred.get('probs')) or not isinstance(pred.get('scoreMarkets'),dict):
                raise ValueError('MISSING_OR_INVALID_FULL_FUSION_DISTRIBUTION')
            mode=pred.get('predictionMode')
            if mode not in ('PRE-XI FUSION','CONFIRMED-XI FUSION'):
                raise ValueError('UNRECOGNIZED_FUSION_MODE')
            stage='P2' if mode=='CONFIRMED-XI FUSION' else 'P1'
            if stage=='P2' and (pred.get('diagnostics') or {}).get('confirmedXi') is not True:
                raise ValueError('CLAIMED_CONFIRMED_XI_NOT_VERIFIED')
            key=fixture_key(f)+'|'+stage
            if key in seen:raise ValueError('DUPLICATE_FIXTURE_STAGE')
            seen.add(key)
            evidence_id=hashlib.sha256(key.encode()).hexdigest()[:24]
            path=outdir/f'hbt_fusion_firstadd_{target}_{evidence_id}_{stage}.json'
            doc={'schemaVersion':VERSION,'fixtureIdentityKey':key,'targetDate':target,
                 'capturedAt':now.isoformat().replace('+00:00','Z'),
                 'sourceGeneratedAt':shadow['generatedAt'],'sourceSha256':source_hash,
                 'sourcePath':src.relative_to(root).as_posix(),
                 'originalDeploymentCreated':shadow.get('deploymentCreated'),
                 'policy':{'immutableFirstAdd':True,'retrainingPerformed':False,
                   'bettingEligible':False,'marketPricesUsedAsPredictors':False,
                   'cleanCalibrationEligible':False,
                   'cleanEvidencePending':'INDEPENDENT_PREMATCH_IDENTITY_KICKOFF_LINEUP_AND_RESULTS_PROOF',
                   'modelPromoted':False,'distinctP1P2NotIndependentMatches':True},
                 'forecast':pred}
            outdir.mkdir(parents=True,exist_ok=True)
            serialized=json.dumps(doc,indent=2,ensure_ascii=False)+'\n'
            try:
                with path.open('x',encoding='utf-8') as handle:handle.write(serialized)
                saved.append(path.name)
            except FileExistsError:
                # Never replace or count a later refresh of the same fixture/stage.
                prior=json.loads(path.read_text(encoding='utf-8'))
                if (prior.get('fixtureIdentityKey')!=key or
                    prior.get('policy',{}).get('immutableFirstAdd') is not True):
                    raise ValueError('pre-existing first-add record corrupt: '+str(path))
                preserved.append(path.name)
        except (ValueError,KeyError,TypeError) as exc:
            excluded.append({'fixture':f,'reason':str(exc)})
    return {'targetDate':target,'sourceGeneratedAt':shadow['generatedAt'],
      'sourceSha256':source_hash,'firstAddWritten':len(saved),'existingPreserved':len(preserved),
      'excluded':len(excluded),'newFiles':saved,'excludedRows':excluded,
      'cleanCalibrationObservationsCreated':0,'fundedBetsCreated':0}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--date',required=True)
    ap.add_argument('--root',default='hbt_live_data',type=Path)
    args=ap.parse_args()
    print(json.dumps(capture(args.root,args.date),indent=2))

if __name__=='__main__':main()
