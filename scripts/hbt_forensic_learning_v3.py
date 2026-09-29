#!/usr/bin/env python3
"""HBT forensic learning v3: competition-safe guard layer.

Runs the guard-aware v2 settlement, then independently excludes rows whose
captured or settled competition identity is unsupported/unresolved. This keeps
such rows as process/guard evidence while preventing predictive learning,
calibration, or hypothesis promotion from non-HBT competitions.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import hbt_forensic_learning_v1 as common
import hbt_forensic_learning_v2 as v2

VERSION = "HBT-FORENSIC-LEARNING-3-COMPETITION-SAFE"
SUPPORTED_CODES = {'en.1','es.1','de.1','it.1','fr.1','nl.1','pt.1','sco.1','tr.1','uefa.cl','en.2','es.2','it.2','be.1','pl.1','ie.1'}
UNSUPPORTED_MARKERS = ('friendly','women','womens','youth','u21','u20','u19','u18','national team','nations league','international friendly','world cup','qualifier','qualification')


def norm_comp(x: Any) -> str:
    return ' '.join(str(x or '').lower().replace('_',' ').replace('-',' ').split())


def unsupported_identity(fx: dict[str, Any], actual_comp: Any) -> str | None:
    league = str(fx.get('league') or '').strip()
    if league not in SUPPORTED_CODES:
        return 'UNSUPPORTED_OR_UNRESOLVED_COMPETITION_CODE'
    captured = norm_comp(fx.get('competitionSlug') or fx.get('competition'))
    settled = norm_comp(actual_comp)
    if any(m in captured for m in UNSUPPORTED_MARKERS):
        return 'EXPLICIT_UNSUPPORTED_CAPTURED_COMPETITION'
    if any(m in settled for m in UNSUPPORTED_MARKERS):
        return 'EXPLICIT_UNSUPPORTED_SETTLED_COMPETITION'
    return None


def recompute_summary(out: dict[str, Any]) -> None:
    audits = out.get('audits') or []
    settled = [a for a in audits if (a.get('actual') or {}).get('settled')]
    eligible = [a for a in settled if (a.get('learning') or {}).get('eligibleForPredictiveLearning')]
    blocked = [a for a in audits if not (a.get('learning') or {}).get('eligibleForPredictiveLearning')]
    top_correct = sum(1 for a in eligible if (a.get('predictionOutcome') or {}).get('topPickCorrect'))
    r0 = [a for a in eligible if (a.get('shadowR0') or {}).get('settlement') in {'WIN','LOSS','VOID'}]
    executions = [a for a in settled if (a.get('execution') or {}).get('settlement')]
    stake = sum(float((a.get('execution') or {}).get('stake') or 0) for a in executions)
    ret = sum(float((a.get('execution') or {}).get('return') or 0) for a in executions)
    out['summary'].update({
        'learningEligibleSettled': len(eligible),
        'guardBlockedRows': len(blocked),
        'topPickCorrectEligible': top_correct,
        'topPickAccuracyEligible': top_correct / len(eligible) if eligible else None,
        'meanBrierEligible': sum(a['predictionOutcome']['brier'] for a in eligible) / len(eligible) if eligible else None,
        'meanLogLossEligible': sum(a['predictionOutcome']['logLoss'] for a in eligible) / len(eligible) if eligible else None,
        'shadowR0Settled': len(r0),
        'shadowR0Wins': sum((a.get('shadowR0') or {}).get('settlement') == 'WIN' for a in r0),
        'shadowR0Losses': sum((a.get('shadowR0') or {}).get('settlement') == 'LOSS' for a in r0),
        'shadowR0Voids': sum((a.get('shadowR0') or {}).get('settlement') == 'VOID' for a in r0),
        'verifiedExecutions': len(executions),
        'executionStake': stake,
        'executionReturn': ret,
        'executionProfit': ret - stake,
    })


def run(date: str) -> dict[str, Any]:
    out = v2.run(date)
    source_path, source_doc, rows = common.source_candidates(date)
    by_key = {}
    for row in rows:
        fx = common.row_fixture(row)
        by_key[common.fixture_key(fx.get('home'), fx.get('away'))] = fx

    for audit in out.get('audits') or []:
        key = common.fixture_key(audit.get('home'), audit.get('away'))
        fx = by_key.get(key) or {}
        reason = unsupported_identity(fx, (audit.get('actual') or {}).get('competition'))
        if not reason:
            continue
        audit['executionGuard'].update({
            'eligibleAtSurface': False,
            'blockReason': reason,
            'guardOutcome': 'BLOCKED_CORRECTLY_NO_MODEL_LEARNING',
        })
        audit['learning'].update({
            'eligibleForPredictiveLearning': False,
            'hypothesisTags': [],
            'researchRequired': False,
            'modelMutationAllowed': False,
            'featurePromotionAllowed': False,
            'nextStep': 'Retain as unsupported-competition guard evidence only; never treat as HBT predictive evidence',
        })
        if audit.get('shadowR0'):
            audit['shadowR0']['eligibleForCalibration'] = False

    out['version'] = VERSION
    out['policy']['unsupportedCompetitionRowsExcludedFromPredictiveLearning'] = True
    out['policy']['unsupportedCompetitionsMayNotBeTreatedAsHBT'] = True
    recompute_summary(out)
    common.write_json(common.FORENSIC / f'hbt_forensic_{date}.json', out)
    return out


def self_test() -> None:
    assert unsupported_identity({'league': None, 'competition':'2026-club-friendly'}, '2026-club-friendly')
    assert unsupported_identity({'league':'de.1','competition':'2026-club-friendly'}, '2026-club-friendly')
    assert unsupported_identity({'league':'de.1','competition':'German Bundesliga'}, 'German Bundesliga') is None
    print('HBT forensic v3 self-test: PASS')


def main() -> int:
    ap=argparse.ArgumentParser();ap.add_argument('--date');ap.add_argument('--self-test',action='store_true');args=ap.parse_args()
    if args.self_test:self_test();return 0
    if not args.date:raise SystemExit('--date required')
    out=run(args.date);print(json.dumps(out['summary'],indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
