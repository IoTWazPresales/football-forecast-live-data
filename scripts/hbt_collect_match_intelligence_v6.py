#!/usr/bin/env python3
"""HBT-1.4.1 transport wrapper for the existing v5 collector.

Understat's internal getLeagueData/getMatchData endpoints require the
X-Requested-With: XMLHttpRequest header. The v5 collector delegated these URLs
to the generic ESPN JSON helper, which does not set that header and currently
receives HTTP 404. This wrapper patches only Understat requests and delegates all
other traffic to the original helper.

No forecasting formulas, parameters, tiers, event-model coefficients, odds policy,
or Test A state are changed.
"""
from __future__ import annotations
import json
import time
import urllib.request
import hbt_collect_match_intelligence_v5 as v5

VERSION='HBT-1.4.1R-UNDERSTAT-AJAX-TRANSPORT'
ORIG_HTTP_JSON=v5.espn.http_json

def http_json_with_understat_ajax(url:str,timeout:int=25,retries:int=3):
    if not str(url).startswith('https://understat.com/'):
        return ORIG_HTTP_JSON(url,timeout,retries)
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
            if attempt+1<retries:time.sleep(0.8+attempt*1.2)
    raise RuntimeError(f'Understat AJAX fetch failed {url}: {last}')

def main()->int:
    v5.espn.http_json=http_json_with_understat_ajax
    rc=v5.main()
    # v5 writes the canonical output. Transport version is added later by the
    # non-predictive quality stage so v5 remains byte-compatible with its schema.
    return rc

if __name__=='__main__':raise SystemExit(main())
