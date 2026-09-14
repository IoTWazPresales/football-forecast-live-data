#!/usr/bin/env python3
"""Runtime hardening for HBT-1.3 market intelligence.

- Reuses the R3 robust ESPN season-label schedule lookup.
- Falls back to previous-season Understat player rates when current-season
  league player data are not yet populated.
- Infers a club's base venue from its own prior home fixtures before falling
  back to ESPN team metadata.
- Tightens readiness so default/unmatched player rows are never called a model.
"""
from __future__ import annotations

import json, math
from collections import Counter
from typing import Any

import hbt_collect_context_v3_runtime as _schedule_patch  # noqa: F401
import hbt_collect_market_intelligence_v4 as v4
import hbt_collect_players_espn as p

_original_understat=v4.understat_players
_original_travel=v4.travel_profile


def robust_understat_players(league:str,year:int,cache:dict[str,Any])->list[dict[str,Any]]:
    candidates=[]
    for sy in (year,year-1,year+1):
        try:rows=_original_understat(league,sy,cache) or []
        except Exception:rows=[]
        if rows:
            zz=[]
            for r in rows:
                q=dict(r);q['_hbtSeasonLabel']=sy;zz.append(q)
            candidates.append((len(zz),0 if sy==year else 1 if sy==year-1 else 2,zz))
    if not candidates:return []
    # Prefer a sufficiently populated current season; otherwise the largest pack,
    # with previous season preferred over a future/adjacent label on ties.
    cur=next((x for x in candidates if x[1]==0 and x[0]>=100),None)
    if cur:return cur[2]
    candidates.sort(key=lambda x:(-x[0],x[1]));return candidates[0][2]


def robust_travel(event:dict[str,Any],team_id:str,current_venue:dict[str,Any]|None,prev_rows:list[dict[str,Any]],cache:dict[str,Any])->dict[str,Any]:
    # Infer home base from an actual prior home fixture venue. This is much safer
    # than treating ESPN's team.location string as a city.
    home_candidates=[]
    for x in prev_rows:
        ev=x.get('event') or {};sm=x.get('summary') or {};venue=sm.get('venue') or {}
        if str(ev.get('homeId') or '')==str(team_id) and venue.get('city'):
            home_candidates.append((str(venue.get('city')),str(venue.get('country') or ''),venue.get('name')))
    homev=None
    if home_candidates:
        c=Counter((a,b) for a,b,_ in home_candidates).most_common(1)[0][0]
        name=next((n for a,b,n in reversed(home_candidates) if (a,b)==c and n),None)
        homev={'name':name,'city':c[0],'country':c[1] or None}
    if not homev:
        base=_original_travel(event,team_id,current_venue,prev_rows,cache)
        # reject a known bad fallback: club name copied into city/location
        hv=base.get('homeVenue') or {}
        if hv.get('city') and p.team_key(str(hv.get('city')))==p.team_key(event['home'] if str(event.get('homeId'))==str(team_id) else event['away']):
            base['homeVenue']=None;base['homeBaseToFixtureKm']=None;base['sourceKnown']=False
        return base
    cur=v4.geocode((current_venue or {}).get('city'),(current_venue or {}).get('country'),cache)
    base_loc=v4.geocode(homev.get('city'),homev.get('country'),cache)
    lastv=None
    if prev_rows:
        v=(prev_rows[-1].get('summary') or {}).get('venue') or {}
        lastv=v4.geocode(v.get('city'),v.get('country'),cache)
    bkm=v4.haversine_km(base_loc,cur);lkm=v4.haversine_km(lastv,cur)
    return {'currentVenue':current_venue,'homeVenue':homev,'homeBaseToFixtureKm':round(bkm,1) if bkm is not None else None,'lastVenueToFixtureKm':round(lkm,1) if lkm is not None else None,'sourceKnown':bool(cur and base_loc),'semantics':'great-circle venue-city distance; home base inferred from prior home fixture venues'}


v4.understat_players=robust_understat_players
v4.travel_profile=robust_travel


def postprocess()->None:
    try:data=json.load(open(v4.OUTPUT,encoding='utf-8'))
    except Exception:return
    health={'fixtures':0,'playerMatchedSides':0,'playerExpectedSides':0,'cornerReady':0,'cardReady':0,'formationReady':0,'travelReady':0,'recentRowsSides':0}
    for row in (data.get('fixtures') or {}).values():
        health['fixtures']+=1
        side_ok=[]
        for side in ('homeDetail','awayDetail'):
            d=row.get(side) or {};players=d.get('players') or [];matched=sum(1 for q in players if q.get('understatId'))
            d['playerSourceMatchedN']=matched;d['playerSourceExpectedN']=len(players)
            ok=matched>=6
            d['playerPropsSourceReady']=ok;side_ok.append(ok)
            if ok:health['playerMatchedSides']+=1
            if players:health['playerExpectedSides']+=1
            if int((d.get('recent') or {}).get('n') or 0)>0:health['recentRowsSides']+=1
        em=row.get('eventMarkets') or {}
        # Require actual recent statistical history on both teams before an event
        # market is declared usable.
        hd=row.get('homeDetail') or {};ad=row.get('awayDetail') or {};hr=hd.get('recent') or {};ar=ad.get('recent') or {}
        c_ready=all((x.get('cornersN') or 0)>=3 for x in (hr,ar)) and (em.get('corners') or {}).get('totalLambda') is not None
        y_ready=all((x.get('yellow_cardsN') or 0)>=3 for x in (hr,ar)) and (em.get('yellowCards') or {}).get('totalLambda') is not None
        f_ready=bool((hd.get('formation') or {}).get('expected') and (ad.get('formation') or {}).get('expected'))
        t_ready=bool((hd.get('travel') or {}).get('sourceKnown') and (ad.get('travel') or {}).get('sourceKnown'))
        row['readiness']={'playerProps':all(side_ok),'corners':c_ready,'cards':y_ready,'formation':f_ready,'travel':t_ready}
        health['cornerReady']+=int(c_ready);health['cardReady']+=int(y_ready);health['formationReady']+=int(f_ready);health['travelReady']+=int(t_ready)
    data['health']=health
    data.setdefault('policy',{})['readiness']='player props require >=6 matched expected-XI players per side; corners/cards require >=3 recent stat rows per side; no missing-as-zero'
    p.write_json(v4.OUTPUT,data)
    try:
        m=json.load(open(v4.MANIFEST,encoding='utf-8'));m['marketIntelligenceHealth']=health;p.write_json(v4.MANIFEST,m)
    except Exception:pass
    print('HBT-1.3 hardened health',health)


def main()->int:
    rc=v4.main();postprocess();return rc

if __name__=='__main__':raise SystemExit(main())
