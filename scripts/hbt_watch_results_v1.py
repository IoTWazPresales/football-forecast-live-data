#!/usr/bin/env python3
"""Observe results against an immutable HBT baseline; never refresh predictions."""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import gzip
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo
import hbt_forensic_learning_v1 as common
import hbt_scan_slate_v2_2 as discovery
from hbt_build_betting_desk_v1 import forecast_markets

DATA = Path(__file__).resolve().parents[1] / 'hbt_live_data'
TZ = ZoneInfo('Africa/Johannesburg')

def frozen_bytes(path):
    return path.read_bytes() if path.exists() else gzip.decompress(path.with_suffix(path.suffix + '.gz').read_bytes())

def read(path):
    return json.loads(frozen_bytes(path))

def stamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))

def key(f):
    return common.fixture_key(f['home'], f['away'])

def freeze(date, folder):
    baseline = folder / 'baseline.json'
    if baseline.exists() or baseline.with_suffix('.json.gz').exists():
        return read(baseline)
    sources = {}
    for stem in ('slate_scanner', 'hbt_prospective_card', 'hbt_betting_desk', 'hbt_recovered_fusion_shadow'):
        path = DATA / f'{stem}_{date}.json'
        sources[stem] = read(path)
        (folder / path.name).write_bytes(path.read_bytes())
    scanner = sources['slate_scanner']
    originals = {key(r['fixture']): r for r in sources['hbt_prospective_card']['candidates']}
    desk = {key(r['fixture']): r for r in sources['hbt_betting_desk']['fixtures']}
    fusion = {key(r['fixture']): r for r in sources['hbt_recovered_fusion_shadow']['predictions']}
    rows = []
    for f in scanner['fixtures']:
        if f['hbtSupportLevel'] == 'UNSUPPORTED_COMPETITION' and f.get('competitionSlug') not in discovery.v.ESPN_LEAGUES:
            continue
        streams = []
        original = originals.get(key(f))
        if original:
            probs = original['probs']
            pred = {'fixture': original['fixture'], 'probs': [probs[k] for k in ('H', 'D', 'A')]}
            streams.append({'name': 'Original frozen L0', 'capturedAt': sources['hbt_prospective_card']['capturedAt'],
                            'markets': forecast_markets(pred), 'resultProbabilities': pred['probs']})
        shadow = fusion.get(key(f))
        if shadow and shadow.get('probs'):
            streams.append({'name': 'Restored Fusion research', 'capturedAt': sources['hbt_recovered_fusion_shadow']['generatedAt'],
                            'markets': forecast_markets(shadow), 'resultProbabilities': shadow['probs']})
        events = [m for m in (desk.get(key(f)) or {}).get('markets', []) if not m.get('mainMarket')]
        if events:
            streams.append({'name': 'Saved event-model research', 'capturedAt': sources['hbt_betting_desk']['generatedAt'],
                            'markets': events, 'resultProbabilities': None})
        rows.append({'fixture': f, 'streams': streams})
    out = {'targetDate': date, 'frozenAt': common.now_iso(), 'policy': {'actualUserBetsExcluded': True,
           'modelMutationAllowed': False, 'predictionRefreshAllowed': False, 'automaticPromotionAllowed': False},
           'sourceHashes': {f'{s}_{date}.json': hashlib.sha256((folder / f'{s}_{date}.json').read_bytes()).hexdigest() for s in sources},
           'trackedLeagueFeeds': discovery.v.ESPN_LEAGUES, 'fixtures': rows}
    common.write_json(baseline, out)
    return out

def settle(market, observation):
    """Only settle verified regulation-time finals, even for monotonic goals."""
    if observation.get('identityVerified') and observation.get('statusName') in (
            'STATUS_ABANDONED', 'STATUS_CANCELED', 'STATUS_CANCELLED', 'STATUS_POSTPONED'):
        return 'NO_REGULATION_RESULT'
    if not observation.get('completed') or not observation.get('identityVerified'):
        return 'PENDING'
    if not observation.get('regulationFinal'):
        return 'UNVERIFIED_PERIOD'
    h, a = observation.get('homeScore'), observation.get('awayScore')
    if h is None or a is None:
        return 'MISSING_RESULT'
    k = market['market']; home, draw, away = h > a, h == a, h < a
    checks = {'HOME_WIN': home, 'DRAW': draw, 'AWAY_WIN': away,
              '1X': home or draw, 'X2': away or draw, '12': not draw}
    if k in checks:
        return 'WIN' if checks[k] else 'LOSS'
    if k in ('HOME_DNB', 'AWAY_DNB'):
        return 'REFUND' if draw else ('WIN' if (home if k == 'HOME_DNB' else away) else 'LOSS')
    if k in ('BTTS_YES', 'BTTS_NO'):
        yes = h > 0 and a > 0
        return 'WIN' if yes == (k == 'BTTS_YES') else 'LOSS'
    match = re.fullmatch(r'(TOTAL_GOALS|HOME_GOALS|AWAY_GOALS|CORNERS|YELLOW_CARDS|TOTAL_SHOTS|TOTAL_SOT)_(OVER|UNDER)_([0-9.]+)', k)
    if not match:
        return 'UNSUPPORTED_SETTLEMENT'
    family, side, line = match.groups()
    value = {'TOTAL_GOALS': h+a, 'HOME_GOALS': h, 'AWAY_GOALS': a}.get(family)
    if value is None:
        value = (observation.get('eventCounts') or {}).get(family)
    if value is None:
        return 'MISSING_EVENT_STATS'
    line = float(line)
    return 'REFUND' if value == line else ('WIN' if (value > line if side == 'OVER' else value < line) else 'LOSS')

def fetch_feed(item):
    league, slug, day = item
    sportsdb = slug.isdigit()
    url = (f'https://www.thesportsdb.com/api/v1/json/123/eventsday.php?d={day[:4]}-{day[4:6]}-{day[6:]}&s=Soccer&l={slug}'
           if sportsdb else f'https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={day}&limit=1000')
    try:
        raw = common.http_json(url)
        if sportsdb:
            events = []
            for e in raw.get('events') or []:
                if str(e.get('idLeague')) != slug: continue
                status = e.get('strStatus') or 'Unknown'
                events.append({'id': 'SPORTSDB:'+str(e['idEvent']), 'date': e.get('strTimestamp') or e.get('dateEvent')+'T'+e.get('strTime','00:00'),
                    'status': {'period': 2, 'type': {'completed': status=='FT', 'state': 'post' if status=='FT' else 'in' if status in ('1H','2H','HT') else 'pre', 'description': status}},
                    'competitions': [{'competitors': [{'homeAway':side, 'score':e.get('int'+title+'Score'), 'team':{'displayName':e.get('str'+title+'Team')}} for side,title in (('home','Home'),('away','Away'))]}]})
            raw = {'events': events}
        return {'league': league, 'url': url, 'retrievedAt': common.now_iso(), 'status': 'LOADED', 'raw': raw}
    except Exception as exc:
        return {'league': league, 'url': url, 'retrievedAt': common.now_iso(), 'status': 'FAILED', 'error': str(exc)}

def parse_event(e, league, feed):
    c = (e.get('competitions') or [{}])[0]; teams = c.get('competitors') or []
    h = next((t for t in teams if t.get('homeAway') == 'home'), {})
    a = next((t for t in teams if t.get('homeAway') == 'away'), {})
    status = e.get('status') or c.get('status') or {}; typ = status.get('type') or {}
    def name(t):
        return discovery.v.model_display_name((t.get('team') or {}).get('displayName') or '', league)
    def score(t):
        value = t.get('score'); value = value.get('value') if isinstance(value, dict) else value
        return float(value) if value not in (None, '') else None
    counts = {}
    for family, aliases in {'CORNERS': ('cornerKicks', 'wonCorners'), 'YELLOW_CARDS': ('yellowCards',),
                             'TOTAL_SHOTS': ('totalShots', 'shots'), 'TOTAL_SOT': ('shotsOnTarget',)}.items():
        vals = []
        for t in (h, a):
            ss = {s.get('name'): s.get('displayValue', s.get('value')) for s in t.get('statistics', [])}
            value = next((ss[n] for n in aliases if n in ss), None)
            try: vals.append(float(value))
            except (TypeError, ValueError): pass
        if len(vals) == 2: counts[family] = sum(vals)
    return {'eventId': str(e.get('id') or ''), 'home': name(h), 'away': name(a), 'league': league,
            'kickoff': e.get('date'), 'completed': bool(typ.get('completed')), 'state': typ.get('state'),
            'status': typ.get('description'), 'clock': status.get('displayClock'), 'statusName': typ.get('name'),
            'regulationFinal': bool(typ.get('completed')) and int(status.get('period') or 2) <= 2
               and not any(x in str(typ.get('name')).upper() for x in ('OVERTIME', 'PENALT', 'CANCEL', 'ABANDON')),
            'homeScore': score(h), 'awayScore': score(a), 'eventCounts': counts,
            'sourceUrl': feed['url'], 'retrievedAt': feed['retrievedAt']}

def enrich_final_event_counts(obs):
    """Fetch final statistics only; verify the same event, teams and result."""
    slug = common.LEAGUE_SLUGS.get(obs.get('league'))
    if not slug or not obs.get('completed') or not obs.get('regulationFinal') or not obs.get('identityVerified'):
        return obs
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/summary?event={obs['eventId']}"
    audit = {'url': url, 'retrievedAt': common.now_iso()}
    try:
        raw = common.http_json(url)
        header = raw.get('header') or {}; comps = header.get('competitions') or []
        if str(header.get('id')) != obs['eventId'] or not comps:
            raise ValueError('SUMMARY_EVENT_ID_MISMATCH')
        c = comps[0]; competitors = c.get('competitors') or []
        h = next((t for t in competitors if t.get('homeAway') == 'home'), {})
        a = next((t for t in competitors if t.get('homeAway') == 'away'), {})
        names = {'home': (h.get('team') or {}).get('displayName'), 'away': (a.get('team') or {}).get('displayName')}
        status = c.get('status') or {}; typ = status.get('type') or {}
        if (key(names) != key(obs) or float(h.get('score')) != obs['homeScore']
                or float(a.get('score')) != obs['awayScore'] or not typ.get('completed')
                or int(status.get('period') or 2) > 2 or stamp(c['date']) != stamp(obs['kickoff'])):
            raise ValueError('SUMMARY_FINAL_IDENTITY_SCORE_TIME_MISMATCH')
        teams = common.parse_stats(raw)['teams']; counts = dict(obs.get('eventCounts') or {})
        for family, aliases in {'CORNERS': ('wonCorners','cornerKicks'), 'YELLOW_CARDS': ('yellowCards',),
                                 'TOTAL_SHOTS': ('totalShots',), 'TOTAL_SOT': ('shotsOnTarget',)}.items():
            vals = []
            for name in (names['home'], names['away']):
                stats = next((s for team,s in teams.items() if common.norm(team) == common.norm(name)), {})
                value = next((stats[n] for n in aliases if n in stats), None)
                try: vals.append(float(value))
                except (ValueError, TypeError): pass
            if len(vals) == 2:
                total = sum(vals)
                if family in counts and counts[family] != total:
                    raise ValueError('FINAL_STATISTICS_CONFLICT:'+family)
                counts[family] = total
        audit['status'] = 'VERIFIED_FINAL_STATS'
        return {**obs, 'eventCounts': counts, 'eventStatsAudit': audit}
    except Exception as exc:
        audit.update(status='UNVERIFIED', error=str(exc))
        return {**obs, 'eventStatsAudit': audit}

def run(date):
    folder = DATA / 'watches' / date; folder.mkdir(parents=True, exist_ok=True)
    baseline = freeze(date, folder)
    for name, digest in baseline['sourceHashes'].items():
        assert hashlib.sha256(frozen_bytes(folder / name)).hexdigest() == digest, f'Frozen baseline changed: {name}'
    start = stamp(date + 'T16:00:00Z'); end = stamp(date + 'T00:00:00Z')
    from datetime import timedelta
    end += timedelta(days=1, hours=4)
    days = (start.strftime('%Y%m%d'), end.strftime('%Y%m%d'))
    feeds = [('all', 'all')] + [(code, pair[0]) for code, pair in baseline['trackedLeagueFeeds'].items()]
    feeds.append(('pl.1', str(discovery.v.SPORTSDB_LEAGUES['pl.1'][0])))
    with ThreadPoolExecutor(max_workers=6) as pool:
        fetched = list(pool.map(fetch_feed, [(code, slug, day) for day in days for code, slug in feeds]))
    observations = {}
    # Specific league identity takes precedence over the generic scoreboard.
    for feed in fetched:
        for e in (feed.get('raw') or {}).get('events', []):
            obs = parse_event(e, feed['league'], feed)
            if obs['eventId'] not in observations or feed['league'] != 'all': observations[obs['eventId']] = obs
    rows = []; metrics = {}
    seen = set()
    for saved in baseline['fixtures']:
        f = saved['fixture']; obs = observations.get(str(f.get('sourceFixtureId'))) or {}
        expected = f.get('leagueHint') or f.get('hbtLeague')
        verified = bool(obs) and key(f) == key(obs) and (obs.get('league') == 'all' or not expected or obs.get('league') == expected)
        obs = {**obs, 'identityVerified': verified}
        if any(s['name'] == 'Saved event-model research' for s in saved['streams']):
            obs = enrich_final_event_counts(obs)
        streams = []
        for stream in saved['streams']:
            captured = stamp(stream['capturedAt']); ko = stamp(obs.get('kickoff') or f['kickoff'])
            prospective = captured < ko and verified
            identity_block = expected and obs.get('league') not in (None, 'all', expected)
            if f.get('competitionSlug') == '2026-27-german-2-bundesliga' and expected == 'de.1': identity_block = True
            markets = [{**m, 'settlement': 'IDENTITY_BLOCKED' if identity_block else settle(m, obs)} for m in stream['markets']]
            output = {**stream, 'preKickoffEvidence': prospective and not identity_block,
                      'identityBlocked': bool(identity_block), 'markets': markets}
            probs = stream.get('resultProbabilities')
            if probs and obs.get('completed') and obs.get('regulationFinal') and verified and not identity_block:
                import math
                h, a = obs['homeScore'], obs['awayScore']; outcome = 0 if h>a else 1 if h==a else 2
                output['topPickCorrect'] = max(range(3), key=lambda i: probs[i]) == outcome
                output['brier'] = sum((p-(i==outcome))**2 for i,p in enumerate(probs))
                output['logLoss'] = -math.log(max(probs[outcome], 1e-15))
                group = stream['name'] + (' / pre-kickoff' if prospective else ' / late research')
                metrics.setdefault(group, []).append(output)
            streams.append(output)
        ko = stamp(obs.get('kickoff') or f['kickoff'])
        rows.append({'fixture': f, 'observation': obs, 'streams': streams, 'eveningWindow': start <= ko < end})
        seen.add(str(f.get('sourceFixtureId')))
    for eid, obs in observations.items():
        if eid in seen or obs['league'] == 'all': continue
        ko = stamp(obs['kickoff'])
        timezone_known = ko.tzinfo is not None
        if timezone_known and not start <= ko < end: continue
        if not timezone_known and ko.date().isoformat() != date: continue
        rows.append({'fixture': {'home': obs['home'], 'away': obs['away'], 'kickoff': obs['kickoff'],
                    'competition': obs['league'], 'sourceFixtureId': eid, 'hbtSupportLevel': 'NO_SAVED_FORECAST'},
                    'observation': {**obs, 'identityVerified': True, 'kickoffTimezoneVerified': timezone_known}, 'streams': [], 'eveningWindow': True})
    rows.sort(key=lambda r: r['fixture']['kickoff'])
    summary = {group: {'settled': len(vals), 'topPickCorrect': sum(v['topPickCorrect'] for v in vals),
               'topPickAccuracy': sum(v['topPickCorrect'] for v in vals)/len(vals),
               'meanBrier': sum(v['brier'] for v in vals)/len(vals), 'meanLogLoss': sum(v['logLoss'] for v in vals)/len(vals)} for group,vals in metrics.items()}
    out = {'targetDate': date, 'observedAt': common.now_iso(), 'windowSast': '10 October 18:00 through 11 October 06:00',
           'policy': baseline['policy'], 'baselineSha256': hashlib.sha256(frozen_bytes(folder/'baseline.json')).hexdigest(),
           'sourceAudit': [{k:v for k,v in f.items() if k!='raw'} for f in fetched], 'fixtures': rows, 'summary': summary,
           'settlementCounts': dict(Counter(m['settlement'] for r in rows for s in r['streams'] for m in s['markets']))}
    common.write_json(folder / 'latest.json', out)
    common.write_json(folder / ('observation_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json'), out)
    lines = ['# HBT forecast results watch — '+date, '', 'Observed '+out['observedAt']+'. Actual user wagers are excluded.',
             '', 'Forecasts are frozen. Alternatives are evaluated individually; mutually exclusive outcomes are not a betting portfolio. Late research is separated from pre-kickoff evidence. No model learning or promotion is performed.',
             '', '## Evening fixtures across all tracked discovery leagues', '', '| SAST kickoff | League | Fixture | Score | Status | HBT forecast streams |', '|---|---|---|---|---|---|']
    for r in rows:
        if not r['eveningWindow']: continue
        f=r['fixture'];o=r['observation'];ko=stamp(o.get('kickoff') or f['kickoff'])
        kickoff_text = ko.astimezone(TZ).strftime('%d %b %H:%M') if ko.tzinfo else ko.strftime('%d %b %H:%M')+' (provider timezone unverified)'
        score=f"{o['homeScore']:g}–{o['awayScore']:g}" if o.get('homeScore') is not None and o.get('awayScore') is not None else 'Unverified'
        lines.append(f"| {kickoff_text} | {f['competition']} | {f['home']} vs {f['away']} | {score} | {o.get('status','Unverified')} {o.get('clock') or ''} | {', '.join(s['name'] for s in r['streams']) or 'No saved HBT forecast'} |")
    lines += ['', '## Every modeled selection — full day and evening', '']
    for r in rows:
        if not r['streams']: continue
        f=r['fixture'];lines += [f"### {f['home']} vs {f['away']}", '']
        for s in r['streams']:
            lines += [s['name']+(' — pre-kickoff timestamp' if s['preKickoffEvidence'] else ' — late/unverified research; excluded from clean prospective metrics'), '', '| Selection | Probability | Settlement |', '|---|---:|---|']
            for m in s['markets']: lines.append(f"| {m['selection']} | {m['winProbability']*100:.1f}% | {m['settlement']} |")
            lines += ['']
    lines += ['## Result-model metrics', '', 'These scores evaluate probability quality; they do not establish profitability.', '', '| Stream | Settled | Top pick correct | Mean Brier | Mean log loss |', '|---|---:|---:|---:|---:|']
    for name,v in summary.items(): lines.append(f"| {name} | {v['settled']} | {v['topPickCorrect']} ({v['topPickAccuracy']:.1%}) | {v['meanBrier']:.4f} | {v['meanLogLoss']:.4f} |")
    (folder / 'latest.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'observedAt':out['observedAt'], 'fixtures':len(rows), 'eveningFixtures':sum(r['eveningWindow'] for r in rows), 'settlementCounts':out['settlementCounts'], 'summary':summary, 'sourceFailures':[a for a in out['sourceAudit'] if a['status']=='FAILED']}, indent=2))

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--date',required=True);run(p.parse_args().date)
