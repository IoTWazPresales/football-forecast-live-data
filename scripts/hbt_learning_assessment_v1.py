#!/usr/bin/env python3
"""Exploratory HBT learning assessment over forensic evidence.

This script is deliberately downstream-only. It never changes probabilities,
weights, tiers, state packs or execution history. Legacy forensic evidence is
kept separate from clean guard-aware evidence and may generate hypotheses only.
"""
from __future__ import annotations

import json
from collections import defaultdict, Counter
from pathlib import Path
from typing import Any

ROOT = Path('hbt_live_data')
FORENSIC = ROOT / 'forensic'
OUT = FORENSIC / 'hbt_learning_assessment_v1.json'
VERSION = 'HBT-LEARNING-ASSESSMENT-1'
DATES = ['2026-09-18','2026-09-19','2026-09-20','2026-09-22','2026-09-23']


def read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def pct(n: int, d: int) -> float | None:
    return n / d if d else None


def qbucket(q: float | None) -> str:
    if q is None: return 'UNKNOWN'
    if q < .70: return '<0.70'
    if q < .85: return '0.70-0.85'
    if q < .95: return '0.85-0.95'
    return '>=0.95'


def pbucket(p: float | None) -> str:
    if p is None: return 'UNKNOWN'
    if p < .45: return '<0.45'
    if p < .55: return '0.45-0.55'
    if p < .65: return '0.55-0.65'
    if p < .75: return '0.65-0.75'
    return '>=0.75'


def add_group(groups: dict[str, dict[str, float]], name: str, correct: bool | None, brier: float | None, logloss: float | None) -> None:
    g=groups.setdefault(name, {'n':0,'correct':0,'brierSum':0.0,'brierN':0,'logLossSum':0.0,'logLossN':0})
    g['n'] += 1
    if correct is True: g['correct'] += 1
    if isinstance(brier,(int,float)):
        g['brierSum'] += float(brier); g['brierN'] += 1
    if isinstance(logloss,(int,float)):
        g['logLossSum'] += float(logloss); g['logLossN'] += 1


def finish_groups(groups: dict[str, dict[str,float]]) -> dict[str,dict[str,Any]]:
    out={}
    for k,g in sorted(groups.items()):
        n=int(g['n']); c=int(g['correct'])
        out[k]={
            'n':n,'correct':c,'accuracy':pct(c,n),
            'meanBrier':g['brierSum']/g['brierN'] if g['brierN'] else None,
            'meanLogLoss':g['logLossSum']/g['logLossN'] if g['logLossN'] else None,
        }
    return out


def main() -> int:
    by_prov={}; by_stale={}; by_quality={}; by_prob={}; by_day={}
    process=Counter(); guard=Counter(); exact_r0=Counter()
    execution_days={}; total_stake=0.0; total_return=0.0
    legacy_rows=0; clean_rows=0; blocked_rows=0; settled_eligible=0

    for d in DATES:
        path=FORENSIC/f'hbt_forensic_{d}.json'
        doc=read(path,{})
        if not doc: continue
        schema=str(doc.get('schemaVersion') or '')
        is_clean=schema=='HBT-FORENSIC-AUDIT-2'
        day_exec={'stake':0.0,'return':0.0,'wins':0,'losses':0,'voids':0,'n':0}
        for a in doc.get('audits') or []:
            learning=a.get('learning') or {}
            eligible=bool(learning.get('eligibleForPredictiveLearning',True)) if is_clean else True
            if is_clean and not eligible:
                blocked_rows += 1
                guard[str((a.get('executionGuard') or {}).get('blockReason') or 'UNKNOWN')] += 1
                continue
            if is_clean: clean_rows += 1
            else: legacy_rows += 1
            if not (a.get('actual') or {}).get('settled'): continue
            po=a.get('predictionOutcome') or {}
            if po.get('topPickCorrect') is None: continue
            settled_eligible += 1
            correct=bool(po.get('topPickCorrect'))
            brier=po.get('brier'); ll=po.get('logLoss'); top_p=po.get('topPickProbability')
            pre=a.get('preMatch') or {}
            prov='C1' if pre.get('coveragePack')=='C1' else 'NON_C1'
            stale='STALE' if 'stale' in str(pre.get('coverage') or '').lower() else 'NOT_STALE'
            add_group(by_prov,prov,correct,brier,ll)
            add_group(by_stale,stale,correct,brier,ll)
            add_group(by_quality,qbucket(float(pre['quality']) if isinstance(pre.get('quality'),(int,float)) else None),correct,brier,ll)
            add_group(by_prob,pbucket(float(top_p) if isinstance(top_p,(int,float)) else None),correct,brier,ll)
            add_group(by_day,d,correct,brier,ll)
            for tag in learning.get('hypothesisTags') or []:
                process[str(tag)] += 1
            r0=a.get('shadowR0') or {}
            if r0.get('settlement'):
                exact_r0[str(r0.get('settlement'))] += 1
            ex=a.get('execution') or {}
            if ex.get('settlement'):
                day_exec['n'] += 1
                day_exec[str(ex.get('settlement')).lower()+'s'] += 1
                st=float(ex.get('stake') or 0); ret=float(ex.get('return') or 0)
                day_exec['stake'] += st; day_exec['return'] += ret
                total_stake += st; total_return += ret
        if day_exec['n']:
            day_exec['profit']=day_exec['return']-day_exec['stake']
            day_exec['roi']=day_exec['profit']/day_exec['stake'] if day_exec['stake'] else None
            execution_days[d]=day_exec

    reg=read(FORENSIC/'hbt_learning_hypotheses_v2.json',{})
    hypotheses={}
    for name,h in (reg.get('hypotheses') or {}).items():
        hypotheses[name]={
            'uniqueOccurrences':h.get('uniqueOccurrences'),
            'uniqueLossOccurrences':h.get('uniqueLossOccurrences'),
            'cleanOccurrences':h.get('cleanOccurrences'),
            'legacyOccurrences':h.get('legacyOccurrences'),
            'promotionAllowed':h.get('promotionAllowed'),
        }

    prov=finish_groups(by_prov); stale=finish_groups(by_stale); quality=finish_groups(by_quality); prob=finish_groups(by_prob); day=finish_groups(by_day)
    lessons=[]
    if total_stake:
        lessons.append({
            'code':'VALUE_GATE_REMAINS_REQUIRED',
            'evidence':{'matchedStake':total_stake,'matchedReturn':total_return,'matchedProfit':total_return-total_stake,'matchedROI':(total_return-total_stake)/total_stake},
            'interpretation':'Winning selections alone did not guarantee positive bankroll growth; retain price/EV gating downstream of HBT probabilities.',
            'action':'KEEP_EXECUTION_VALUE_LAYER',
        })
    c1=prov.get('C1'); non=prov.get('NON_C1')
    if c1 and non:
        lessons.append({
            'code':'C1_REQUIRES_SEPARATE_CALIBRATION',
            'evidence':{'C1':c1,'NON_C1':non},
            'interpretation':'C1 transfer behaviour differs enough to remain separately measured; this legacy comparison is exploratory and cannot promote or retune C1.',
            'action':'KEEP_C1_CAP_AND_COLLECT_CLEAN_PROSPECTIVE_DATA',
        })
    if stale.get('STALE') and stale.get('NOT_STALE'):
        lessons.append({
            'code':'STATE_FRESHNESS_REMAINS_A_FIRST_CLASS_SIGNAL',
            'evidence':{'STALE':stale['STALE'],'NOT_STALE':stale['NOT_STALE']},
            'interpretation':'Freshness should remain visible in surfacing/staking and be tested on clean future slates rather than silently folded into weights.',
            'action':'KEEP_STALE_STATE_RISK_FLAG',
        })
    if blocked_rows:
        lessons.append({
            'code':'IDENTITY_GUARD_PREVENTED_CONTAMINATION',
            'evidence':{'guardBlockedRows':blocked_rows,'blockReasons':dict(guard)},
            'interpretation':'Blocked women/reserve/generic-identity rows must not count toward model calibration even when their hypothetical market later wins.',
            'action':'KEEP_FAIL_CLOSED_IDENTITY_GATE',
        })
    lessons.append({
        'code':'EXACT_R0_CALIBRATION_RESTARTS_CLEANLY',
        'evidence':{'cleanExactR0Settlements':dict(exact_r0)},
        'interpretation':'Older protected-market observations remain useful context, but the authoritative exact-R0 calibration series should begin only from guard-aware eligible future slates.',
        'action':'ACCUMULATE_CLEAN_R0_SERIES',
    })

    out={
        'schemaVersion':'HBT-LEARNING-ASSESSMENT-1','version':VERSION,
        'scope':DATES,
        'policy':{
            'predictiveModelMutated':False,'weightsRetuned':False,'existingIntelligenceRemoved':False,
            'legacyEvidenceExploratoryOnly':True,'cleanEvidenceRequiredForPromotion':True,
            'automaticFeaturePromotion':False,'holdoutValidationRequired':True,
        },
        'evidenceQuality':{
            'legacyEligibleRows':legacy_rows,'cleanGuardAwareRows':clean_rows,'guardBlockedRowsExcluded':blocked_rows,
            'settledEligibleRows':settled_eligible,
        },
        'raw1X2Assessment':{
            'byDay':day,'byProvenance':prov,'byFreshness':stale,'byQualityBucket':quality,'byTopPickProbabilityBucket':prob,
            'warning':'Raw H/D/A top-pick accuracy is not the same metric as protected-market 1X/X2/12/DNB accuracy.'
        },
        'processHypothesisTagsObserved':dict(process.most_common()),
        'uniqueHypothesisRegistry':hypotheses,
        'matchedExecutionAssessment':{
            'byDay':execution_days,'stake':total_stake,'return':total_return,'profit':total_return-total_stake,
            'roi':(total_return-total_stake)/total_stake if total_stake else None,
            'warning':'Matched execution rows may be incomplete for older slates and exclude some multis/alias-unmatched user bets.'
        },
        'exactR0CleanSeries':dict(exact_r0),
        'lessons':lessons,
        'nextPromotionRule':'No hypothesis changes predictive weights until historical backtest plus unseen holdout improvement and clean prospective confirmation.',
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(out,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
