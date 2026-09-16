#!/usr/bin/env python3
"""HBT-1.4.2 research-only live safety guard. No predictive parameters change."""
from __future__ import annotations
import json, unicodedata
from collections import Counter
from pathlib import Path
from typing import Any
import hbt_intelligence_integrity_guard_v1 as integrity
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'hbt_live_data'
MATCH=OUT/'hbt_1_4_match_intelligence.json'; PREXI=OUT/'pre_xi_context.json'; CACHE=OUT/'_hbt_1_4_live_cache.json'
PLAYER_FEATURES=OUT/'player_features.json'; PROP_PARAMS=OUT/'player_prop_model_params.json'
VERSION='HBT-1.4.2R-SAFETY-GUARD'


def read(p,d):
    try:return json.load(open(p,encoding='utf-8'))
    except Exception:return d


def write(p,x):
    t=p.with_suffix(p.suffix+'.tmp')
    with open(t,'w',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,separators=(',',':'))
    t.replace(p)


def norm(v:Any)->str:
    s=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in s).split())


def prexi(pre,row):
    for q in (pre.get('fixtures') or {}).values():
        if str((q or {}).get('kickoff') or '')[:10]!=str(row.get('kickoff') or '')[:10]:continue
        if norm((q or {}).get('home'))==norm(row.get('home')) and norm((q or {}).get('away'))==norm(row.get('away')):return q
    return None


def xi_agreement(q,official):
    z={'available':False,'role':'diagnostic shadow only; not frozen confirmed-XI continuity'}
    if not q:return z
    for side,k in (('home','homeStarters'),('away','awayStarters')):
        e={norm(x) for x in (((q.get(side+'Detail') or {}).get('snapshot') or {}).get('expectedXI') or []) if norm(x)}
        a={norm(x) for x in (official.get(k) or []) if norm(x)}
        if e and a:
            n=len(e&a);z[side]={'available':True,'expectedN':len(e),'confirmedN':len(a),'overlapN':n,'overlapRatioOfXI':n/max(1,len(a)),'lineupShockRatio':1-n/max(1,len(a))}
        else:z[side]={'available':False}
    z['available']=bool(z.get('home',{}).get('available') and z.get('away',{}).get('available'));return z


def _find_player_feature(pf,row):
    target_event=str(row.get('eventId') or '')
    hk,ak=norm(row.get('home')),norm(row.get('away'))
    for q in (pf.get('features') or {}).values():
        if target_event and str((q or {}).get('eventId') or '')!=target_event:continue
        if norm((q or {}).get('home'))!=hk or norm((q or {}).get('away'))!=ak:continue
        return q
    return None


def recompute_confirmed_features(row,pf):
    ac=row.setdefault('availabilityContinuity',{});off=row.get('officialXI') or {}
    h=off.get('homeStarters') or [];a=off.get('awayStarters') or []
    base={'available':False,'source':'hbt_collect_players_espn.py/team_snapshot','identityVerified':False,'guardVersion':VERSION}
    if not (off.get('confirmed') and len(h)==11 and len(a)==11):
        ac['confirmedFeatures']={**base,'reason':'official_11v11_not_confirmed'};return False
    q=_find_player_feature(pf,row)
    if not q:
        ac['confirmedFeatures']={**base,'reason':'confirmed_player_feature_row_missing'};return False
    if not q.get('ok'):
        ac['confirmedFeatures']={**base,'reason':'confirmed_player_feature_not_ready:'+str(q.get('reason') or 'unknown'),'sourceFetchedAt':q.get('fetchedAt')};return False
    hs=(q.get('homeSnapshot') or {}).get('xi') or [];aws=(q.get('awaySnapshot') or {}).get('xi') or []
    hset={norm(x) for x in h if norm(x)};aset={norm(x) for x in a if norm(x)};hsset={norm(x) for x in hs if norm(x)};awsset={norm(x) for x in aws if norm(x)}
    if hset!=hsset or aset!=awsset:
        ac['confirmedFeatures']={**base,'reason':'confirmed_player_feature_lineup_identity_mismatch','sourceFetchedAt':q.get('fetchedAt'),'homeOfficialN':len(hset),'homeFeatureN':len(hsset),'awayOfficialN':len(aset),'awayFeatureN':len(awsset)};return False
    c=q.get('continuityDiff');r=q.get('replacementQualityAdv')
    if c is None or r is None:
        ac['confirmedFeatures']={**base,'reason':'confirmed_player_feature_values_missing','sourceFetchedAt':q.get('fetchedAt')};return False
    ac['confirmedFeatures']={'available':True,'confirmedXIContinuityDiff':c,'confirmedReplacementQualityAdv':r,'source':'hbt_collect_players_espn.py/team_snapshot','sourceEventId':q.get('eventId'),'sourceFetchedAt':q.get('fetchedAt'),'identityVerified':True,'homeStarterN':len(hset),'awayStarterN':len(aset),'guardVersion':VERSION,'semantics':'exact confirmed-XI team_snapshot continuity/replacement-quality semantics; readiness only; frozen predictive model unchanged'}
    return True


def validated_prop_markets(params):
    markets=((params.get('holdout') or {}).get('markets') or {})
    return {str(k) for k,v in markets.items() if isinstance(v,dict) and int(v.get('n') or 0)>0}


def guard_props(row,allowed_markets,prop_version):
    field_map={'shots1Plus':'pShot1Plus','shots2Plus':'pShot2Plus','shots3Plus':'pShot3Plus','sot1Plus':'pSOT1Plus','sot2Plus':'pSOT2Plus','anytimeGoal':'pAnytimeGoalRaw'}
    off=row.get('officialXI') or {}; confirmed=bool(off.get('confirmed')); p=row.setdefault('playerProps',{}); rows=p.setdefault('marketRows',{'home':[],'away':[]})
    dropped={'home':[],'away':[]}; kept={'home':0,'away':0};market_counts=Counter()
    for side,k in (('home','homeStarters'),('away','awayStarters')):
        starters={norm(x) for x in off.get(k) or [] if norm(x)}; out=[]
        for r in rows.get(side) or []:
            name=str((r or {}).get('name') or ''); identity=confirmed and norm(name) in starters; model_flag=bool((r or {}).get('validatedPlayerPropModel'))
            actionable=[m for m,field in field_map.items() if m in allowed_markets and (r or {}).get(field) is not None]
            valid=bool(model_flag and actionable)
            if identity and valid:
                q=dict(r);q['confirmedXIIdentityMatch']=True;q['actionableMarkets']=actionable;q['validatedMarketArtifactVersion']=prop_version;q['marketValidationScope']='pooled confirmed starters; no position-specific holdout claim'
                non_action={}
                if q.get('pCardRaw') is not None:non_action['pCardRaw']='player-card market is not present in HBT-1.3R-PLAYER-PROP-CAL holdout validation'
                if non_action:q['nonActionableMarketFields']=non_action
                out.append(q);market_counts.update(actionable)
            else:
                why=[]
                if not identity:why.append('not_in_confirmed_starting_xi')
                if not model_flag:why.append('validated_player_prop_model_missing')
                if model_flag and not actionable:why.append('no_holdout_validated_actionable_market')
                dropped[side].append({'name':name,'reason':'+'.join(why)})
        rows[side]=out;kept[side]=len(out)
    p['actionGate']='CONFIRMED-XI + exact canonical starter identity + holdout-validated player-prop market'
    p['identityGate']={'version':VERSION,'confirmedXIObserved':confirmed,'keptRows':kept,'droppedRows':dropped,'failClosed':True}
    p['validatedMarketScope']={'artifactVersion':prop_version,'allowedMarkets':sorted(allowed_markets),'explicitlyNotValidated':['playerCards'],'failClosed':True}
    p['actionable']=bool(confirmed and (kept['home'] or kept['away']))
    return dict(market_counts)


def decision(row):
    off=row.get('officialXI') or {};h=off.get('homeStarters') or [];a=off.get('awayStarters') or []; confirmed=bool(off.get('confirmed'))
    if not (confirmed and len(h)==11 and len(a)==11):
        b=[]
        if not confirmed:b.append('official_xi_not_confirmed')
        if len(h)!=11:b.append(f'home_starting_xi_count_{len(h)}')
        if len(a)!=11:b.append(f'away_starting_xi_count_{len(a)}')
        return 'PRE_XI_PROVISIONAL',b
    b=[]; ac=row.get('availabilityContinuity') or {}; cf=ac.get('confirmedFeatures') or {}; impact=row.get('playerTeamImpact') or {};hs=impact.get('homeStarterAttack') or {};aw=impact.get('awayStarterAttack') or {}
    if cf.get('confirmedXIContinuityDiff') is None:b.append('confirmed_xi_continuity_not_recomputed')
    if cf.get('confirmedReplacementQualityAdv') is None:b.append('confirmed_replacement_quality_not_recomputed')
    if cf.get('identityVerified') is not True:b.append('confirmed_xi_feature_identity_not_verified')
    if impact.get('mode')!='CONFIRMED_XI':b.append('player_team_impact_not_in_confirmed_xi_mode')
    if impact.get('starterAttackIndexDiff') is None:b.append('confirmed_starter_attack_diff_missing')
    if int(hs.get('matchedN') or 0)<7:b.append('home_confirmed_starter_identity_coverage_below_7_of_11')
    if int(aw.get('matchedN') or 0)<7:b.append('away_confirmed_starter_identity_coverage_below_7_of_11')
    return ('CONFIRMED_XI_OBSERVED',b) if b else ('CONFIRMED_XI_FEATURES_READY',[])


def country(v):
    x=norm(v)
    return 'united kingdom' if x in {'england','scotland','wales','northern ireland','united kingdom','uk'} else x


def guard_weather(row,cache):
    w=row.get('weatherVenue')
    if not isinstance(w,dict):return
    venue=(((row.get('travel') or {}).get('home') or {}).get('currentVenue') or {}); city=str(venue.get('city') or ''); c=str(venue.get('country') or '')
    g=(cache.get('geocode') or {}).get(f'{city}|{c}') if city and c else None; reasons=[]
    if isinstance(g,dict):
        exp,res=country(c),country(g.get('country')); allowed={exp,res}=={'france','monaco'}
        europe={'spain','france','monaco','germany','italy','netherlands','belgium','portugal','united kingdom','poland','austria','switzerland','denmark','sweden','norway','finland','ireland','czechia','czech republic','greece','turkey'}
        if exp in europe and res not in europe and not allowed:reasons.append(f"geocode_country_mismatch:{c}->{g.get('country')}")
        try:
            if g.get('elevationM') is not None and float(g['elevationM'])>5000:reasons.append(f"implausible_elevation_m:{g['elevationM']}")
        except Exception:reasons.append('invalid_elevation')
        w['geocodeAudit']={'requested':f'{city}|{c}','resolvedName':g.get('resolvedName'),'resolvedCountry':g.get('country')}
    else:w['geocodeAudit']={'requested':f'{city}|{c}' if city or c else None,'status':'cache_entry_unavailable'}
    w['qualityGate']=not reasons;w['qualityReasons']=reasons;w['usableForContext']=bool(w.get('available') and not reasons)


def main():
    d=read(MATCH,None)
    if not isinstance(d,dict):raise SystemExit(f'missing or invalid {MATCH}')
    pre=read(PREXI,{});cache=read(CACHE,{});pf=read(PLAYER_FEATURES,{});params=read(PROP_PARAMS,{})
    allowed_markets=validated_prop_markets(params);prop_version=params.get('version')
    counts=Counter();tb=pa=wr=cr=0;market_counts=Counter()
    for row in (d.get('fixtures') or {}).values():
        cr+=int(recompute_confirmed_features(row,pf));row['legacyReadinessState']=row.get('readinessState'); state,block=decision(row);row['decisionReadinessState']=state;row['testBComputable']=state=='CONFIRMED_XI_FEATURES_READY';row['testBBlockingReasons']=block;counts[state]+=1;tb+=int(row['testBComputable'])
        row['confirmedVsExpectedXI']=xi_agreement(prexi(pre,row),row.get('officialXI') or {});market_counts.update(guard_props(row,allowed_markets,prop_version));row['playerPropIdentityReady']=bool((row.get('playerProps') or {}).get('actionable'));pa+=int(row['playerPropIdentityReady'])
        guard_weather(row,cache);wr+=int((row.get('weatherVenue') or {}).get('qualityGate') is False)
    d['guardVersion']=VERSION;d.setdefault('policy',{}).update({'frozenPredictiveModelMutated':False,'bookmakerOddsUsed':False,'testAImmutable':True,'decisionReadinessContract':'PRE_XI_PROVISIONAL -> CONFIRMED_XI_OBSERVED -> CONFIRMED_XI_FEATURES_READY; Test B only from FEATURES_READY','confirmedXIRecomputation':'exact ESPN confirmed-XI team_snapshot semantics with event/team/11-player identity verification; fail closed; no frozen model mutation','playerPropIdentityGate':'fail closed; confirmed starters + holdout-validated prop markets only','playerPropMarketValidation':'actionability derived from player_prop_model_params holdout markets; pCardRaw explicitly non-actionable','weatherQualityGate':'context only; predictive weight remains zero','downstreamIntelligenceMutationAllowed':False})
    d.setdefault('health',{}).update({'decisionReadiness':dict(counts),'testBComputable':tb,'confirmedXIRecomputedFixtures':cr,'playerPropActionableFixtures':pa,'playerPropActionableMarketRows':dict(market_counts),'validatedPlayerPropMarkets':sorted(allowed_markets),'weatherContextRejected':wr});write(MATCH,d)
    # The integrity snapshot is byte-level and lives outside the intelligence file.
    # Every downstream transform must see the same digest or fail closed.
    integrity.snapshot()
    print('HBT-1.4.2 safety guard',dict(counts),'testB',tb,'confirmedRecomputed',cr,'props',pa,'markets',dict(market_counts),'weatherRejected',wr,'integrityLatched',True);return 0
if __name__=='__main__':raise SystemExit(main())
