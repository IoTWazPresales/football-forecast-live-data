#!/usr/bin/env python3
"""Non-predictive Understat transport probe.

Records HTTP/content diagnostics only. It never writes HBT intelligence or forecasts.
"""
from __future__ import annotations
import gzip, json, re, urllib.request, urllib.error, zlib
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'hbt_live_data'/'understat_transport_probe.json'
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36'
LEAGUES={'EPL':'2026','La_liga':'2026','Bundesliga':'2026','Serie_A':'2026','Ligue_1':'2026'}

def decode_body(b:bytes, content_encoding:str):
    enc=(content_encoding or '').lower()
    method='none'; raw=b
    try:
        if b.startswith(b'\x1f\x8b') or 'gzip' in enc:
            raw=gzip.decompress(b); method='gzip'
        elif 'deflate' in enc:
            raw=zlib.decompress(b); method='deflate'
    except Exception as e:
        return b,'decode-error:'+type(e).__name__
    return raw,method

def fetch(url, ajax=False):
    headers={'User-Agent':UA,'Accept':'application/json,text/javascript,*/*;q=0.01' if ajax else 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8','Referer':'https://understat.com/'}
    if ajax: headers['X-Requested-With']='XMLHttpRequest'
    req=urllib.request.Request(url,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            b=r.read(1500000); ct=r.headers.get('content-type',''); ce=r.headers.get('content-encoding',''); status=r.status
    except urllib.error.HTTPError as e:
        b=e.read(200000); ct=e.headers.get('content-type',''); ce=e.headers.get('content-encoding',''); status=e.code
    except Exception as e:
        return {'ok':False,'error':f'{type(e).__name__}: {e}'}
    raw,method=decode_body(b,ce)
    text=raw.decode('utf-8','replace')
    patterns={}
    for name,pat in {
        'datesData':r"datesData", 'teamsData':r"teamsData", 'playersData':r"playersData",
        'JSONparse':r"JSON\.parse", 'decodeURIComponent':r"decodeURIComponent",
        'getLeagueData':r"getLeagueData", 'cloudflare':r"cloudflare|cf-chl|challenge-platform",
    }.items(): patterns[name]=bool(re.search(pat,text,re.I))
    stripped=text.lstrip(); looks=stripped.startswith('{') or stripped.startswith('[')
    parsed=None; parse_error=None
    if looks:
        try:
            obj=json.loads(text)
            parsed={'type':type(obj).__name__,'topLevelKeys':sorted(obj.keys())[:30] if isinstance(obj,dict) else None,'length':len(obj) if hasattr(obj,'__len__') else None}
        except Exception as e: parse_error=f'{type(e).__name__}: {e}'
    return {'ok':200<=status<300,'status':status,'contentType':ct,'contentEncoding':ce,'bytesRead':len(b),'decodedBytes':len(raw),'decodeMethod':method,'looksJson':looks,'jsonParsed':parsed,'jsonParseError':parse_error,'htmlTitle':(re.search(r'<title[^>]*>(.*?)</title>',text,re.I|re.S).group(1).strip() if re.search(r'<title[^>]*>(.*?)</title>',text,re.I|re.S) else None),'patterns':patterns,'prefix':re.sub(r'\s+',' ',text[:220])}

def main():
    out={'schemaVersion':'HBT-UNDERSTAT-TRANSPORT-PROBE-1.1','generatedAt':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'policy':{'diagnosticOnly':True,'writesMatchIntelligence':False,'changesProbabilities':False,'changesWeights':False},'leagues':{}}
    for league,year in LEAGUES.items():
        out['leagues'][league]={'ajax':fetch(f'https://understat.com/getLeagueData/{league}/{year}',True),'page':fetch(f'https://understat.com/league/{league}/{year}',False)}
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(out,indent=2,ensure_ascii=False))
if __name__=='__main__': main()
