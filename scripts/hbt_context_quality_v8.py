#!/usr/bin/env python3
"""HBT-1.4.2 context/source-quality wrapper.

Repairs observability only. The live collector already decodes gzip/deflate on
Understat league transport; the separate context-quality process previously did
not, so it could report JSONDecodeError even when tactical data had loaded.
This wrapper gives diagnostics the same bounded compression-aware HTTP semantics.

No predictive probability, coefficient, tier, Test A state, bookmaker policy, or
research-family promotion is changed.
"""
from __future__ import annotations

import gzip
import json
import urllib.request
import zlib
from pathlib import Path

import hbt_context_quality_v7 as v7

VERSION='HBT-1.4.2R-CONTEXT-QUALITY'
TRANSPORT_PATCH='HBT-CONTEXT-UNDERSTAT-GZIP-DECODE-1'
ORIG_HTTP_JSON=v7.http_json


def http_json_compression_aware(url:str,timeout:int=25,headers:dict[str,str]|None=None):
    # Preserve v7 request semantics exactly; only decode HTTP content encoding
    # before JSON parsing. This is safe for Open-Meteo and other plain responses.
    h={'User-Agent':v7.UA,'Accept':'application/json,*/*'}
    if headers:
        h.update(headers)
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        body=r.read()
        enc=str(r.headers.get('content-encoding') or '').lower()
        if body.startswith(b'\x1f\x8b') or 'gzip' in enc:
            body=gzip.decompress(body)
        elif 'deflate' in enc:
            body=zlib.decompress(body)
        return json.loads(body.decode('utf-8-sig','strict'))


def main()->int:
    v7.VERSION=VERSION
    v7.http_json=http_json_compression_aware
    rc=v7.main()

    # Stamp provenance after v7 writes the context snapshot.
    p=Path(__file__).resolve().parents[1]/'hbt_live_data'/'hbt_1_4_match_intelligence.json'
    d=json.loads(p.read_text(encoding='utf-8'))
    d['contextQualityVersion']=VERSION
    d['contextDiagnosticTransportPatch']=TRANSPORT_PATCH
    d.setdefault('policy',{})['contextDiagnosticTransportOnly']=True
    p.write_text(json.dumps(d,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    return rc


if __name__=='__main__':
    raise SystemExit(main())
