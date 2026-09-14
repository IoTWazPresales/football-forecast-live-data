#!/usr/bin/env python3
"""Extract actual-lineup tactical shape and venue travel for HBT's 2018-19 frozen cohort era.

Primary tactical source: ESPN historical summary formation strings. Fallback:
Understat starter positions converted to an observed line-shape. Venue cities come
from ESPN summaries; each club's home-base venue is inferred only from its own
home fixtures in the same historical season. No outcomes are used to construct
features, and no bookmaker data is used.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json, re, time, urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import hbt_collect_players_espn as p
import hbt_collect_market_intelligence_v4 as v4

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'hbt_live_data';OUTPUT=OUT/'tactical_travel_2018.json';CACHE=OUT/'_tactical_2018_cache.json'
VERSION='HBT-1.3R-TACTICAL-TRAVEL-2018'
LEAGUES={'EPL':('en.1','eng.1'),'La_liga':('es.1','esp.1'),'Bundesliga':('de.1','ger.1'),'Serie_A':('it.1','ita.1'),'Ligue_1':('fr.1','fra.1')}
ALIASES={'internazionale':'inter','internazionale milano':'inter','paris saint germain':'psg','olympique lyonnais':'lyon','olympique marseille':'marseille','borussia monchengladbach':'monchengladbach','bayern munich':'bayern','bayern munchen':'bayern','tottenham hotspur':'tottenham','wolverhampton wanderers':'wolves','athletic club':'athletic bilbao'}


def key(s:str)->str:
    k=p.team_key(s);return ALIASES.get(k,k)
def sim(a:str,b:str)->float:
    a,b=key(a),key(b)
    if a==b:return 1.
    aa,bb=set(a.split()),set(b.split())
    if not aa or not bb:return 0.
    j=len(aa&bb)/len(aa|bb)
    if aa<=bb or bb<=aa:j=max(j,.88)
    return j
def league_pack(name:str)->dict[str,Any]:return p.http_json(f'https://understat.com/getLeagueData/{name}/2018',30,3)
def parse_when(s:str)->dt.datetime|None:
    s=str(s or '').replace('T',' ').replace('Z','')
    for fmt in ('%Y-%m-%d %H:%M:%S','%Y-%m-%d %H:%M','%Y-%m-%d'):
      try:return dt.datetime.strptime(s[:19],fmt)
      except:pass
    return None
def understat_matches()->list[dict[str,Any]]:
    out=[]
    for name,(lc,espn) in LEAGUES.items():
      raw=league_pack(name)
      for r in raw.get('dates') or []:
        if not r.get('isResult'):continue
        h=r.get('h') or {};a=r.get('a') or {};when=parse_when(r.get('datetime') or r.get('date'))
        if not when:continue
        out.append({'understatId':str(r.get('id') or ''),'date':when.date().isoformat(),'datetime':when.isoformat(),'league':lc,'espnLeague':espn,'home':h.get('title') or h.get('name') or '','away':a.get('title') or a.get('name') or ''})
    return out

def scoreboard(league:str,day:str,cache:dict[str,Any])->list[dict[str,Any]]:
    ck=f'{league}|{day}';old=(cache.get('scoreboards') or {}).get(ck)
    if isinstance(old,list):return old
    ds=day.replace('-','');url=f'https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard?dates={ds}'
    try:
      raw=p.http_json(url,20,3);rows=[]
      lc=next((v[0] for v in LEAGUES.values() if v[1]==league),'')
      for e in raw.get('events') or []:
        er=p.event_record(e,lc,league)
        if er:rows.append(er)
      cache.setdefault('scoreboards',{})[ck]=rows;return rows
    except Exception:return []
def match_espn(r:dict[str,Any],cache:dict[str,Any])->dict[str,Any]|None:
    rows=scoreboard(r['espnLeague'],r['date'],cache);best=None
    for e in rows:
      sc=(sim(r['home'],e.get('home') or '')+sim(r['away'],e.get('away') or ''))/2
      if best is None or sc>best[0]:best=(sc,e)
    return best[1] if best and best[0]>=.62 else None
def us_match(mid:str,cache:dict[str,Any])->dict[str,Any]|None:
    old=(cache.get('understat') or {}).get(mid)
    if isinstance(old,dict):return old
    try:
      raw=p.http_json(f'https://understat.com/getMatchData/{mid}',20,3);cache.setdefault('understat',{})[mid]=raw;return raw
    except Exception:return None
def roster_shape(raw:dict[str,Any]|None,side:str)->str|None:
    if not raw:return None
    ro=(raw.get('rosters') or {}).get(side) or {};vals=ro.values() if isinstance(ro,dict) else ro if isinstance(ro,list) else []
    d=m=f=0
    for q in vals:
      pos=str((q or {}).get('position') or '').upper()
      if pos=='SUB' or not pos:continue
      if pos=='GK':continue
      if pos.startswith('D'):d+=1
      elif 'FW' in pos or pos in {'F','CF','ST'}:f+=1
      else:m+=1
    if d+m+f<9:return None
    return f'{d}-{m}-{f}'
def parse_shape(s:str|None)->dict[str,Any]:
    if not s:return {'raw':None,'defenders':None,'midfielders':None,'attackers':None,'lines':None,'aggression':None}
    try:
      parts=[int(x) for x in str(s).split('-')]
      if len(parts)<3:return {'raw':s,'defenders':None,'midfielders':None,'attackers':None,'lines':None,'aggression':None}
      return {'raw':s,'defenders':parts[0],'midfielders':sum(parts[1:-1]),'attackers':parts[-1],'lines':len(parts),'aggression':parts[-1]+.45*sum(parts[1:-1])}
    except:return {'raw':s,'defenders':None,'midfielders':None,'attackers':None,'lines':None,'aggression':None}
def fetch_one(r:dict[str,Any],cache:dict[str,Any])->dict[str,Any]:
    e=match_espn(r,cache);summary=None;hf=af=None;venue=None
    if e:
      try:
        raw=p.http_json(v4.summary_url(e),20,2);hf=(v4.recursive_formations(raw,str(e.get('homeId'))) or [None])[0];af=(v4.recursive_formations(raw,str(e.get('awayId'))) or [None])[0];venue=v4.parse_venue(raw)
      except Exception:pass
    ur=us_match(r['understatId'],cache)
    hf=hf or roster_shape(ur,'h');af=af or roster_shape(ur,'a')
    return {**r,'espnEventId':str((e or {}).get('id') or '') or None,'homeFormation':parse_shape(hf),'awayFormation':parse_shape(af),'formationSource':'ESPN actual formation' if e and hf and af else 'Understat observed starter-role fallback','venue':venue,'matchedEspn':bool(e)}

def main()->int:
    OUT.mkdir(parents=True,exist_ok=True);cache={}
    try:cache=json.load(open(CACHE,encoding='utf-8'))
    except:cache={'scoreboards':{},'understat':{},'geocode':{}}
    rows=understat_matches();out=[]
    # Scoreboard calls are cached by date/league; keep moderate concurrency.
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
      fut=[ex.submit(fetch_one,r,cache) for r in rows]
      for i,x in enumerate(fut):
        try:out.append(x.result())
        except Exception as e:pass
        if i and i%150==0:print('features',i,'/',len(rows),flush=True)
    # infer each team's home-base city only from its home fixtures in this season
    cities=defaultdict(list)
    for r in out:
      v=r.get('venue') or {};city=v.get('city');country=v.get('country')
      if city:cities[(r['league'],key(r['home']))].append((str(city),str(country or '')))
    bases={}
    for k,vals in cities.items():
      c=Counter(vals).most_common(1)[0][0];bases[k]={'city':c[0],'country':c[1] or None}
    for r in out:
      v=r.get('venue') or {};loc=v4.geocode(v.get('city'),v.get('country'),cache)
      hb=bases.get((r['league'],key(r['home'])));ab=bases.get((r['league'],key(r['away'])))
      hl=v4.geocode((hb or {}).get('city'),(hb or {}).get('country'),cache);al=v4.geocode((ab or {}).get('city'),(ab or {}).get('country'),cache)
      hkm=v4.haversine_km(hl,loc);akm=v4.haversine_km(al,loc)
      r['travel']={'homeKm':round(hkm,1) if hkm is not None else None,'awayKm':round(akm,1) if akm is not None else None,'awayMinusHomeKm':round(akm-hkm,1) if hkm is not None and akm is not None else None,'venue':v,'homeBase':hb,'awayBase':ab}
    payload={'schemaVersion':'HBT-TACTICAL-TRAVEL-1','version':VERSION,'generatedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'season':2018,'policy':{'bookmakerOddsUsed':False,'outcomesUsedToBuildFeatures':False,'formation':'ESPN actual formation when exposed; Understat observed starter-role fallback otherwise','travel':'club home-base venue inferred from own home fixtures; great-circle city distance'},'coverage':{'rows':len(out),'espnMatched':sum(bool(x.get('matchedEspn')) for x in out),'formationBoth':sum(bool(x.get('homeFormation',{}).get('raw') and x.get('awayFormation',{}).get('raw')) for x in out),'travelBoth':sum(x.get('travel',{}).get('homeKm') is not None and x.get('travel',{}).get('awayKm') is not None for x in out)},'rows':out}
    OUTPUT.write_text(json.dumps(payload,separators=(',',':')),encoding='utf-8');CACHE.write_text(json.dumps(cache,separators=(',',':')),encoding='utf-8');print(payload['coverage']);return 0
if __name__=='__main__':raise SystemExit(main())
