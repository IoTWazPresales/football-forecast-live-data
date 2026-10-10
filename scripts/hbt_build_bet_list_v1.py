#!/usr/bin/env python3
"""Export the actual eligible selection list from a freshly evaluated desk."""
import argparse
import hashlib
import json
from pathlib import Path
import hbt_build_betting_desk_v1 as desk
import hbt_execution_surface_v1 as base


def build(target, data_root=desk.ROOT, now=None):
    doc = desk.build(target, data_root=data_root, now=now)
    bets = []
    for fixture in doc['fixtures']:
        for market in fixture['markets']:
            if not market['stakeReady']:
                continue
            assert not market['fundingBlockers']
            assert market['observedOdds'] and market['expectedProfitPerRand'] > 0
            bets.append({'fixture': fixture['fixture'], 'kickoffUtc': fixture['kickoffVerification']['kickoffUtc'],
                         'market': market['market'], 'selection': market['selection'],
                         'decimalOdds': market['observedOdds'], 'winProbability': market['winProbability'],
                         'pushProbability': market['pushProbability'], 'expectedProfitPerRand': market['expectedProfitPerRand'],
                         'bookmaker': market['bookmaker'], 'quotedAt': market['quotedAt'],
                         'status': 'ELIGIBLE_FOR_REVIEW', 'placed': False})
    bets.sort(key=lambda r: (-r['winProbability'], -r['expectedProfitPerRand']))
    assert len(bets) == doc['summary']['readySingles']
    summary = (doc.get('recoveredFusionResearch') or {}).get('summary') or {}
    result = {'schemaVersion': 'HBT-BET-LIST-1', 'targetDate': target, 'generatedAt': doc['generatedAt'],
              'status': 'ELIGIBLE_FOR_REVIEW' if bets else 'NO_ELIGIBLE_BETS', 'bets': bets, 'chains': [],
              'policy': {'automaticBetsPlaced': False, 'chainFundingAllowed': False, 'guaranteedProfit': False,
                         'ranking': 'win probability descending among verified positive-value eligible singles'},
              'counts': {'eligibleSingles': len(bets), 'eligibleChains': 0, 'placedBets': 0,
                         'verifiedPricedMarkets': doc['summary']['bookmakerPricedMarkets'],
                         'recoveredResearchScoreDistributions': summary.get('scoreDistributions', 0)},
              'blockers': doc['summary']['blockerCounts'], 'sourceHashes': doc['sourceHashes']}
    return doc, result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', required=True)
    target = parser.parse_args().date
    doc, result = build(target)
    desk_json = desk.ROOT / f'hbt_betting_desk_{target}.json'
    base.write(desk_json, doc)
    (desk.ROOT / f'hbt_betting_desk_{target}.html').write_text(desk.render(doc), encoding='utf-8')
    result['deskSha256'] = hashlib.sha256(desk_json.read_bytes()).hexdigest()
    base.write(desk.ROOT / f'hbt_bet_list_{target}.json', result)
    rows = ['# HBT bet list — ' + target, '', 'Evaluated: ' + result['generatedAt'], '',
            '**Eligible bets: ' + str(len(result['bets'])) + '. Placed bets: 0.**', '']
    if result['bets']:
        rows += ['| Fixture | Selection | Odds | Profit probability |', '|---|---|---:|---:|']
        for b in result['bets']:
            f = b['fixture']
            rows.append(f"| {f['home']} vs {f['away']} | {b['selection']} | {b['decimalOdds']:.2f} | {b['winProbability']:.1%} |")
    else:
        rows += ['No selection passes the current model, timing, lineup, immutable-capture and bookmaker-price checks.', '',
                 'The restored Fusion score model remains research-only. The live price feed has no configured provider key and no verified quotes.', '',
                 'Chains eligible for funding: 0. Suggested stake: R0.']
    (desk.ROOT / f'hbt_bet_list_{target}.md').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], **result['counts']}, indent=2))


if __name__ == '__main__':
    main()
