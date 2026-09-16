#!/usr/bin/env python3
"""HBT-1.4.1 non-predictive live context quality repair + source diagnostics.

Scope is deliberately narrow:
- repair ambiguous Open-Meteo geocodes with ISO countryCode filtering;
- refresh weather context only when the existing geocode/weather is demonstrably bad;
- expose Understat source/shape diagnostics instead of silently treating failures as data absence.

This script never changes HBT football probabilities, tiers, frozen parameters, Test A,
or bookmaker-odds policy. Weather remains context-only with predictive weight zero.
"""
from __future__ import annotations
import datetime as dt
import json
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'hbt_live_data'
MATCH=OUT/'hbt_1_4_match_intelligence.json'
CACHE=OUT/'_hbt_1_4_live_cache.json'
VERSION='HBT-1.4.1R-CONTEXT-QUALITY'
UA='Mozilla/5.0 (compatible; HBT-1.4.1-ContextQuality/1.0)'
LEAGUES={'en.1':'EPL','es.1':'La_liga','de.1':'Bundesliga','it.1':'Serie_A','fr.1':'Ligue_1'}
COUNTRY_CODE={
    'england':'GB','scotland':'GB','wales':'GB','northern ireland':'GB','united kingdom':'GB','uk':'GB',
    'spain':'ES','france':'FR','germany':'DE','italy':'IT','netherlands':'NL','belgium':'BE','portugal':'PT',
    'poland':'PL','austria':'AT','switzerland':'CH','denmark':'DK','sweden':'SE','norway':'NO','finland':'FI',
    'ireland':'IE','czechia':'CZ','czech republic':'CZ','greece':'GR','turkey':'TR','monaco':'MC'
}

def read(p:Path,default:Any)->Any:
    try:return json.load(open(p,encoding='utf-8'))
    except Exception:return default

def write(p:Path,x:Any)->None:
    t=p.with_suffix(p.suffix+'.tmp')
    with open(t,'w',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,separators=(',',':'))
    t.replace(p)

def norm(v:Any)->str:
    s=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in s).split())

def http_json(url:str,timeout:int=25)->dict[str,Any]:
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json,*/*'})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8','replace'))

def expected_iso(city:str,country:str)->str|None:
    # Monaco is a sovereign city-state even if a venue source labels it France.
    if norm(city)=='monaco':return 'MC'
    return COUNTRY_CODE.get(norm(country))

def geocode_ok(g:Any,iso:str|None)->bool:
    if not isinstance(g,dict) or g.get('lat') is None or g.get('lon') is None:return False
    try:
        if g.get('elevationM') is not None and float(g['elevationM'])>5000:return False
    except Exception:return False
    gc=str(g.get('countryCode') or '').upper()
    if iso and gc:return gc==iso
    # Legacy cache entries do not have countryCode; compare normalized country conservatively.
    if iso and not gc:
        legacy={v:k for k,v in COUNTRY_CODE.items()}
        target=legacy.get(iso)
        if target and norm(g.get('country')) not in {target,'united kingdom' if iso=='GB' else target}:return False
    return True

def robust_geocode(city:str,country:str)->dict[str,Any]|None:
    if not city:return None
    iso=expected_iso(city,country)
    q={'name':f'{city}, {iso or country}' if (iso or country) else city,'count':10,'language':'en','format':'json'}
    if iso:q['countryCode']=iso
    raw=http_json('https://geocoding-api.open-meteo.com/v1/search?'+urllib.parse.urlencode(q))
    rows=raw.get('results') or []
    if not rows:return None
    c=rows[0]
    if iso and str(c.get('country_code') or '').upper()!=iso:return None
    return {'lat':c.get('latitude'),'lon':c.get('longitude'),'elevationM':c.get('elevation'),'resolvedName':c.get('name'),'country':c.get('country'),'countryCode':c.get('country_code'),'admin1':c.get('admin1'),'source':'Open-Meteo geocoding with ISO countryCode'}

def parse_dt(v:Any)->dt.datetime|None:
    try:return dt.datetime.fromisoformat(str(v or '').replace('Z','+00:00'))
    except Exception:return None

def forecast(geo:dict[str,Any],venue:dict[str,Any],kick:dt.datetime)->dict[str,Any]:
    q=urllib.parse.urlencode({'latitude':geo['lat'],'longitude':geo['lon'],'hourly':'temperature_2m,precipitation_probability,precipitation,wind_speed_10m,wind_gusts_10m,weather_code','timezone':'UTC','forecast_days':7})
    raw=http_json('https://api.open-meteo.com/v1/forecast?'+q)
    H=raw.get('hourly') or {}; times=H.get('time') or []
    if not times:raise RuntimeError('forecast hour array empty')
    ix=min(range(len(times)),key=lambda i:abs((dt.datetime.fromisoformat(times[i]).replace(tzinfo=dt.timezone.utc)-kick).total_seconds()))
    return {'available':True,'source':'Open-Meteo forecast','forecastIssuedAt':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),'venueCity':venue.get('city'),'elevationM':geo.get('elevationM'),'temperatureC':H['temperature_2m'][ix],'precipitationProbability':H['precipitation_probability'][ix],'precipitationMm':H['precipitation'][ix],'windKmh':H['wind_speed_10m'][ix],'gustKmh':H['wind_gusts_10m'][ix],'weatherCode':H['weather_code'][ix],'promotionEligible':False,'reason':'live forecast retained as context only; no causal historical forecast archive','geocodeRepairVersion':VERSION}

def repair_weather(d:dict[str,Any],cache:dict[str,Any])->dict[str,Any]:
    stats={'checked':0,'geocodesRefreshed':0,'weatherRefreshed':0,'repairFailed':0,'unchanged':0}
    geo_cache=cache.setdefault('geocode',{}); weather_cache=cache.setdefault('weather',{})
    now=dt.datetime.now(dt.timezone.utc)
    for row in (d.get('fixtures') or {}).values():
        kick=parse_dt(row.get('kickoff')); venue=(((row.get('travel') or {}).get('home') or {}).get('currentVenue') or {})
        city,country=str(venue.get('city') or ''),str(venue.get('country') or '')
        if not kick or not city:continue
        stats['checked']+=1; ck=f'{city}|{country}'; iso=expected_iso(city,country); old=geo_cache.get(ck)
        current_weather=row.get('weatherVenue') or {}
        must_repair=not geocode_ok(old,iso)
        if not must_repair:
            stats['unchanged']+=1;continue
        try:
            g=robust_geocode(city,country)
            if not g:raise RuntimeError(f'no country-consistent geocode for {city}|{country}|{iso}')
            geo_cache[ck]=g;stats['geocodesRefreshed']+=1
            # Do not backfill past-match weather with forecast/hindsight. Only repair live future context.
            if kick>=now-dt.timedelta(minutes=30):
                w=forecast(g,venue,kick);row['weatherVenue']=w;stats['weatherRefreshed']+=1
                # The old coordinate keyed weather cache may remain as inert provenance; write corrected current key too.
                wk=f"{float(g['lat']):.4f}|{float(g['lon']):.4f}|{kick.isoformat()[:13]}"
                weather_cache[wk]={'cachedAt':time.time(),'data':w}
            else:
                current_weather['geocodeRepairNote']='geocode repaired after kickoff; weather not retrospectively backfilled';row['weatherVenue']=current_weather
        except Exception as exc:
            stats['repairFailed']+=1
            current_weather['contextQualityRepairError']=str(exc)[:180];row['weatherVenue']=current_weather
    return stats

def understat_diag(year:int)->dict[str,Any]:
    out={}
    for league,name in LEAGUES.items():
        out[league]={}
        for label,y in (('current',year),('previous',year-1)):
            url=f'https://understat.com/getLeagueData/{name}/{y}'
            try:
                p=http_json(url,30); teams=p.get('teams'); players=p.get('players')
                tvals=list(teams.values()) if isinstance(teams,dict) else teams if isinstance(teams,list) else []
                out[league][label]={'status':'loaded','url':url,'topLevelKeys':sorted(p.keys()),'teamN':len(tvals or []),'playerN':len(players or []) if isinstance(players,list) else len(players or {}) if isinstance(players,dict) else 0,'datesN':len(p.get('dates') or []),'hasTeams':bool(tvals),'sampleTeamKeys':sorted((tvals[0] or {}).keys())[:20] if tvals else []}
            except Exception as exc:
                out[league][label]={'status':'failed','url':url,'error':f'{type(exc).__name__}: {exc}'[:240]}
    return out

def main()->int:
    d=read(MATCH,None)
    if not isinstance(d,dict):raise SystemExit(f'missing or invalid {MATCH}')
    cache=read(CACHE,{}); year=dt.datetime.now().year
    wx=repair_weather(d,cache); diag=understat_diag(year)
    d['contextQualityVersion']=VERSION
    d.setdefault('sourceDiagnostics',{})['understat']=diag
    d.setdefault('health',{})['contextQualityWeatherRepair']=wx
    d.setdefault('policy',{}).update({'frozenPredictiveModelMutated':False,'bookmakerOddsUsed':False,'testAImmutable':True,'contextQualityRepair':'geocoding/weather context only; no probability/tier/parameter changes','understatDiagnostics':'observability only; missing remains missing'})
    write(CACHE,cache);write(MATCH,d)
    loaded=sum(int(v.get(k,{}).get('status')=='loaded') for v in diag.values() for k in ('current','previous'))
    print('HBT-1.4.1 context quality',wx,'Understat packs loaded',loaded,'of',len(diag)*2);return 0
if __name__=='__main__':raise SystemExit(main())
