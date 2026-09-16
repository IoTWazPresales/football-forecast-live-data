#!/usr/bin/env python3
"""HBT-1.4.1 bounded transport wrapper for the existing v5 collector.

Understat's getLeagueData endpoint requires the X-Requested-With AJAX header.
Restoring it is enough to recover the league/team/player packs used by tactical
profiles and player-to-team impact. The existing v5 collector also attempts up
to eight getMatchData requests per team/fixture for set-piece/substitution/GK
context. Turning that fan-out on for every live fixture made the scheduled job
unbounded and is therefore deliberately deferred until it has its own cached,
rate-bounded collector.

Existing cached getMatchData records are still consumed by v5.us_match before
this transport function is called. New per-match requests fail closed quickly,
so missing remains missing rather than delaying or fabricating intelligence.

No forecasting formulas, parameters, tiers, event-model coefficients, odds policy,
or Test A state are changed.
"""
from __future__ import annotations
import json
import time
import urllib.request
import hbt_collect_match_intelligence_v5 as v5

VERSION='HBT-1.4.1R-UNDERSTAT-AJAX-BOUNDED'
ORIG_HTTP_JSON=v5.espn.http_json

def ajax(url:str,timeout:int=18,retries:int=2):
    last=None
    for attempt in range(retries):
        try:
            req=urllib.request.Request(url,headers={
                'User-Agent':'Mozilla/5.0 (compatible; HBT-1.4.1-Live/1.0)',
                'Accept':'application/json,*/*',
                'X-Requested-With':'XMLHttpRequest',
                'Referer':'https://understat.com/'
            })
            with urllib.request.urlopen(req,timeout=timeout) as r:
                return json.loads(r.read().decode('utf-8-sig','replace'))
        except Exception as exc:
            last=exc
            if attempt+1<retries:time.sleep(0.6)
    raise RuntimeError(f'Understat AJAX fetch failed {url}: {last}')

def http_json_bounded(url:str,timeout:int=25,retries:int=3):
    u=str(url)
    if not u.startswith('https://understat.com/'):
        return ORIG_HTTP_JSON(url,timeout,retries)
    if '/getLeagueData/' in u:
        return ajax(u,min(timeout,18),min(retries,2))
    if '/getMatchData/' in u:
        # v5.us_match catches this and returns None. Cached records are used before
        # the call reaches here. This avoids hundreds of live network requests.
        raise RuntimeError('getMatchData live fanout deferred to bounded cache collector')
    return ajax(u,min(timeout,18),min(retries,2))

def main()->int:
    v5.espn.http_json=http_json_bounded
    return v5.main()

if __name__=='__main__':raise SystemExit(main())
