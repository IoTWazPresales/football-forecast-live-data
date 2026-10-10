#!/usr/bin/env python3
"""Fetch a small explicit set of official club sources; absent coverage is absent proof.

This collector cannot correct a forecast or declare a model ready. It records
observed official kickoffs separately, with response hash and extraction text.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import urllib.request
from zoneinfo import ZoneInfo

import hbt_execution_surface_v1 as base

ROOT = Path(__file__).resolve().parents[1] / 'hbt_live_data'
AJAX_URL = 'https://www.ajax.nl/wedstrijden/'
MADRID_URL = 'https://www.realmadrid.com/en-US/news/football/first-team/latest-news/el-real-madrid-villarreal-se-jugara-sabado-10-de-octubre-a-las-21-00-h-10-09-2026'
MONTHS = {'januari': 1, 'februari': 2, 'maart': 3, 'april': 4, 'mei': 5, 'juni': 6,
          'juli': 7, 'augustus': 8, 'september': 9, 'oktober': 10, 'november': 11, 'december': 12}


def text(fragment):
    return ' '.join(html.unescape(re.sub('<[^>]*>', ' ', fragment)).split())


def parse_ajax(body, target):
    rows = []
    for block in re.findall(r'<li\b[^>]*class="matches-block__match"[^>]*>(.*?)</li>', body, re.S):
        stamp = re.search(r'class="matches-block__date"[^>]*>(.*?)</span>', block, re.S)
        people = re.search(r'class="matches-block__participants[^"\n]*"[^>]*>(.*?)</span>\s*([^<]*)', block, re.S)
        if not stamp or not people:
            continue
        match = re.search(r'(\d{1,2}) (\w+) (\d{4}) (\d{2}:\d{2})', text(stamp.group(1)))
        if not match or match[2] not in MONTHS:
            continue
        local = datetime.fromisoformat(f'{match[3]}-{MONTHS[match[2]]:02d}-{int(match[1]):02d}T{match[4]}').replace(tzinfo=ZoneInfo('Europe/Amsterdam'))
        if local.date().isoformat() != target:
            continue
        participants = text(people.group(1) + ' ' + people.group(2)).split(' - ')
        if len(participants) != 2 or 'Ajax' not in participants:
            continue
        rows.append({'home': participants[0], 'away': participants[1],
                     'kickoffUtc': base.iso(local), 'sourceTimezone': 'Europe/Amsterdam',
                     'sourceExcerpt': text(stamp.group(1)) + ' | ' + ' - '.join(participants)})
    return list({(r['home'], r['away'], r['kickoffUtc']): r for r in rows}.values())


def parse_madrid(body, target):
    rows = []
    for raw in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', body, re.S):
        doc = json.loads(html.unescape(raw))
        if not isinstance(doc, dict) or doc.get('@type') != 'NewsArticle':
            continue
        headline = str(doc.get('headline') or '')
        publication = base.parse_aware(doc.get('datePublished'))
        if not publication or 'Real Madrid-Villarreal' not in headline:
            continue
        match = re.search(r'October (\d{1,2}), at (\d{1,2}):(\d{2}) (am|pm) (CEST|CET)', headline)
        if not match:
            continue
        hour = int(match[2]) % 12 + (12 if match[4] == 'pm' else 0)
        local = datetime(publication.year, 10, int(match[1]), hour, int(match[3]), tzinfo=ZoneInfo('Europe/Madrid'))
        # Never reinterpret an archived announcement as next year's fixture.
        if local.date().isoformat() != target or not publication < local < publication + timedelta(days=120):
            continue
        if local.tzname() != match[5]:
            continue
        rows.append({'home': 'Real Madrid', 'away': 'Villarreal', 'kickoffUtc': base.iso(local),
                     'sourceTimezone': 'Europe/Madrid', 'sourceExcerpt': headline,
                     'sourcePublishedAt': doc['datePublished']})
    return rows


def collect(target):
    confirmations, audit = [], []
    for label, url, parser in [('Ajax official club schedule', AJAX_URL, parse_ajax),
                               ('Real Madrid official club announcement', MADRID_URL, parse_madrid)]:
        observed = base.iso(datetime.now(timezone.utc))
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (HBT official fixture crosscheck)'})
            with urllib.request.urlopen(req, timeout=20) as response:
                raw = response.read()
                final_url = response.geturl()
            observed = base.iso(datetime.now(timezone.utc))
            # A redirect to another host cannot silently acquire official-source status.
            from urllib.parse import urlsplit
            if urlsplit(final_url).hostname != urlsplit(url).hostname:
                raise ValueError('official source redirected to another host')
            digest = hashlib.sha256(raw).hexdigest()
            extracted = parser(raw.decode('utf-8', 'replace'), target)
            for row in extracted:
                row.update(independentSource=label, sourceUrl=url, verifiedAt=observed, responseSha256=digest)
            confirmations.extend(extracted)
            audit.append({'source': label, 'sourceUrl': url, 'observedAt': observed, 'responseSha256': digest,
                          'status': 'MATCHES_EXTRACTED' if extracted else 'NO_MATCH_FOR_TARGET', 'count': len(extracted)})
        except Exception as exc:
            audit.append({'source': label, 'sourceUrl': url, 'observedAt': observed,
                          'status': 'SOURCE_OR_EXTRACTION_FAILURE', 'error': f'{type(exc).__name__}: {exc}'[:240]})
    return {'schemaVersion': 'HBT-INDEPENDENT-KICKOFFS-1', 'targetDate': target,
            'generatedAt': base.iso(datetime.now(timezone.utc)), 'confirmations': confirmations, 'sourceAudit': audit,
            'policy': {'changesForecast': False, 'allFixturesVerified': False,
                       'officialSourceCoverage': 'Ajax schedule and one dated Real Madrid announcement only',
                       'sourceDisagreementBlocksExecution': True}}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--date', required=True); args = ap.parse_args()
    date.fromisoformat(args.date)
    doc = collect(args.date)
    base.write(ROOT / f'hbt_independent_kickoffs_{args.date}.json', doc)
    print(json.dumps({'targetDate': args.date, 'confirmations': len(doc['confirmations']), 'sources': doc['sourceAudit']}, indent=2))


if __name__ == '__main__':
    main()
