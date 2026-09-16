#!/usr/bin/env python3
"""HBT-1.4.2 bounded Understat transport wrapper for the existing v5 collector.

The live Understat getLeagueData endpoint currently returns a gzip-compressed JSON
body with content-type text/javascript. urllib does not transparently decompress
that response, which made the previous wrapper try to JSON-decode compressed bytes
and caused every Big-Five tactical pack to fail.

This wrapper changes transport only:
- AJAX headers are retained;
- gzip/deflate response bodies are decoded before JSON parsing;
- getMatchData live fan-out remains blocked and cached-only;
- no forecast formula, coefficient, feature weight, tier, odds policy, or Test A
  state is changed.
"""
from __future__ import annotations
import gzip
import json
import time
import urllib.request
import zlib
import hbt_collect_match_intelligence_v5 as v5

VERSION='HBT-1.4.2R-UNDERSTAT-GZIP-AJAX-BOUNDED'
ORIG_HTTP_JSON=v5.espn.http_json

def _decode_body(body:bytes, content_encoding:str='')->bytes:
    enc=(content_encoding or '').lower()
    if body.startswith(b'\x1f\x8b') or 'gzip' in enc:
        return gzip.decompress(body)
    if 'deflate' in enc:
        return zlib.decompress(body)
    return body

def ajax(url:str,timeout:int=18,retries:int=2):
    last=None
    for attempt in range(retries):
        try:
            req=urllib.request.Request(url,headers={
                'User-Agent':'Mozilla/5.0 (compatible; HBT-1.4.2-Live/1.0)',
                'Accept':'application/json,text/javascript,*/*;q=0.01',
                'X-Requested-With':'XMLHttpRequest',
                'Referer':'https://understat.com/'
            })
            with urllib.request.urlopen(req,timeout=timeout) as r:
                raw=r.read()
                body=_decode_body(raw,r.headers.get('content-encoding',''))
                obj=json.loads(body.decode('utf-8-sig','strict'))
                if not isinstance(obj,dict):
                    raise RuntimeError(f'Understat payload is not an object: {type(obj).__name__}')
                return obj
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
    rc=v5.main()
    # The v5 payload is produced after the monkeypatch is active. Stamp only the
    # transport version so diagnostics can distinguish the repaired source path.
    try:
        from pathlib import Path
        p=Path(__file__).resolve().parents[1]/'hbt_live_data'/'hbt_1_4_match_intelligence.json'
        data=json.loads(p.read_text(encoding='utf-8'))
        data['understatTransportVersion']=VERSION
        p.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    except Exception as exc:
        raise RuntimeError(f'collector succeeded but transport version stamp failed: {exc}')
    return rc

if __name__=='__main__':raise SystemExit(main())
