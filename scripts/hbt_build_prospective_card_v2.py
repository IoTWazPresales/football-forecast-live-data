#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime as dt, json, re, unicodedata
from pathlib import Path
from typing import Any

ROOT=Path('hbt_live_data')
VERSION='HBT-PROSPECTIVE-CARD-2'

def read(p:Path,default=None):
    try:return json.load(open(p,encoding='utf-8'))
    except Exception:return {} if default is None else default

def norm(x:Any)->str:
    s=unicodedata.normalize('NFKD',str(x or '')).encode('ascii','ignore').decode().lower()
    s=re.sub(r'\b(fc|cf|afc|ac|ssc|sc|rc|club|football|futbol|the)\b',' ',s)
    return ' '.join(re.sub(r'[^a-z0-9]+',' ',s).split())

def k(date,home,away):return f'{date}|{norm(home)}|{norm(away)}'

def fixture_index(doc:dict)->dict:
    out={}
    fx=doc.get('fixtures') or {}
    rows=fx.values() if isinstance(fx,dict) else fx if isinstance(fx,list) else []
    for r in rows:
        if not isinstance(r,dict):continue
        date=str(r.get('kickoff') or r.get('date') or '')[:10]
        home=r.get('home');away=r.get('away')
        if date and home and away:out[k(date,home,away)]=r
    return out

def extract_overlay(r:dict)->dict:
    readiness=r.get('readinessState') or (r.get('readiness') or {}).get('state')
    av=r.get('availabilityContinuity') or {}
    tac=r.get('tactical') or {}
    gk=r.get('shotStoppingGoalkeeper') or {}
    sp=r.get('setPieces') or {}
    wl=r.get('workload') or {}
    tr=r.get('travel') or {}
    fm=r.get('formation') or {}
    mg=r.get('manager') or {}
    cs=r.get('competitionState') or {}
    xi=r.get('officialXI') or {}
    gaps=[]
    if readiness!='CONFIRMED_XI_READY':gaps.append('CONFIRMED_XI_NOT_READY')
    if not ((av.get('sourceState') or {}).get('availability')):gaps.append('AVAILABILITY_SIGNAL_MISSING')
    if gk and all(gk.get(x) is None for x in ('homeGoalkeeperResidual','awayGoalkeeperResidual','homeTeamResidual','awayTeamResidual')):gaps.append('GOALKEEPER_SIGNAL_WEAK_OR_MISSING')
    if not gk:gaps.append('GOALKEEPER_SIGNAL_MISSING')
    if not sp:gaps.append('SET_PIECE_SIGNAL_MISSING')
    if not wl or not ((wl.get('home') or {}).get('sourceKnown') or (wl.get('away') or {}).get('sourceKnown')):gaps.append('WORKLOAD_SIGNAL_MISSING')
    if not tr or not ((tr.get('home') or {}).get('sourceKnown') or (tr.get('away') or {}).get('sourceKnown')):gaps.append('TRAVEL_SIGNAL_MISSING')
    if not tac:gaps.append('TACTICAL_SIGNAL_MISSING')
    return {
        'readinessState':readiness,
        'officialXIConfirmed':bool(xi.get('confirmed')),
        'availabilityContinuity':av,
        'tactical':tac,
        'shotStoppingGoalkeeper':gk,
        'setPieces':sp,
        'workload':wl,
        'travel':tr,
        'formation':fm,
        'manager':mg,
        'competitionState':cs,
        'validatedEventFamilies':r.get('validatedEventFamilies') or [],
        'intelligenceGaps':sorted(set(gaps)),
        'forensicFamiliesSurfaced':{
            'DEFENSIVE_AVAILABILITY_CLUSTER':bool(av),
            'RETURNING_PLAYER_FITNESS':bool(av or wl),
            'GOALKEEPER_RECENT_ERROR_FORM':bool(gk),
            'CONFIRMED_XI_DELTA':bool(xi or readiness),
            'PRESS_RESISTANCE_MATCHUP':bool(tac),
            'SET_PIECE_DEFENDING':bool(sp)
        }
    }

def market_map(h,d,a):
    hd=h/(h+a) if h+a else None;ad=a/(h+a) if h+a else None
    return {
      'HOME_WIN':{'p':h,'fairOdds':1/h if h else None,'family':'1X2'},
      'DRAW':{'p':d,'fairOdds':1/d if d else None,'family':'1X2'},
      'AWAY_WIN':{'p':a,'fairOdds':1/a if a else None,'family':'1X2'},
      '1X':{'p':h+d,'fairOdds':1/(h+d) if h+d else None,'family':'DOUBLE_CHANCE'},
      'X2':{'p':a+d,'fairOdds':1/(a+d) if a+d else None,'family':'DOUBLE_CHANCE'},
      '12':{'p':h+a,'fairOdds':1/(h+a) if h+a else None,'family':'DOUBLE_CHANCE'},
      'HOME_DNB':{'conditionalP':hd,'winP':h,'pushP':d,'lossP':a,'fairOdds':(h+a)/h if h else None,'family':'DNB'},
      'AWAY_DNB':{'conditionalP':ad,'winP':a,'pushP':d,'lossP':h,'fairOdds':(h+a)/a if a else None,'family':'DNB'}
    }

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--date',required=True);a=ap.parse_args();date=a.date
    src=ROOT/f'hbt_broad_shadow_forecast_{date}_resolver_v3.json';data=read(src)
    if not data.get('predictions'):raise SystemExit(f'no predictions in {src}')
    intel=read(ROOT/'hbt_1_4_match_intelligence.json');pre=read(ROOT/'pre_xi_context.json');market=read(ROOT/'market_intelligence.json')
    idx_intel=fixture_index(intel);idx_pre=fixture_index(pre);idx_market=fixture_index(market)
    captured=dt.datetime.now(dt.timezone.utc);rows=[]
    for r in data['predictions']:
        f=r['fixture'];h,d,a3=map(float,r['probs']);date0=f['date'];key=k(date0,f['home'],f['away'])
        ko=dt.datetime.fromisoformat(f"{date0}T{f.get('time','00:00')}:00+00:00")
        ir=idx_intel.get(key) or idx_market.get(key) or idx_pre.get(key) or {}
        overlay=extract_overlay(ir) if ir else {'readinessState':None,'officialXIConfirmed':False,'intelligenceGaps':['MATCH_INTELLIGENCE_NOT_CAPTURED'],'forensicFamiliesSurfaced':{}}
        rows.append({
            'fixture':f,'statusAtCapture':'PRE_KICKOFF' if ko>captured else 'POST_KICKOFF',
            'origin':'HBT_SHADOW_RESOLVER_V3','coverage':r.get('coverage'),'coveragePack':r.get('coveragePack'),
            'predictionMode':r.get('predictionMode'),'tier':r.get('tier'),'rawTier':r.get('rawTier'),'quality':r.get('quality'),
            'resolution':r.get('resolution'),'probs':{'H':h,'D':d,'A':a3},'derivedMarkets':market_map(h,d,a3),
            'intelligenceOverlay':overlay,
            'surfacingPolicy':{
                'baseProbabilityChangedByOverlay':False,
                'overlayCanChangeRiskLabelOrStakeOnlyAfterValidatedRule':False,
                'overlayPurpose':'Expose knowable match state and gaps; do not silently invent probability weights.'
            }
        })
    out={
      'schemaVersion':'HBT-PROSPECTIVE-CARD-2','version':VERSION,'capturedAt':captured.isoformat().replace('+00:00','Z'),'targetDate':date,
      'origin':'HBT_SHADOW_RESOLVER_V3','policy':{
        'bookmakerOddsUsedAsPredictiveFeature':False,'bookmakerPriceObservedBeforeCapture':False,'modelRetuned':False,
        'preMatchCaptureImmutable':True,'postKickoffBackfillAllowed':False,'preserveExistingIntelligence':True,
        'allValidatedIntelligenceFamiliesRetained':True,'unvalidatedOverlayDoesNotChangeProbability':True,
        'forensicLearningCanCreateHypothesesButNotAutoPromote':True,'competitionLabelIsEligibilityGate':False,
        'genderNamespaceSeparated':True,'youthReserveNamespaceSeparated':True,'c1UsesFrozenL0StructuralWeights':True,'c1ATierPromotionAllowed':False
      },
      'parityDiagnostic':(data.get('bridge') or {}).get('goldenMaxAbsError'),'c1StateAudit':(data.get('bridge') or {}).get('c1StateAudit'),
      'intelligenceSources':{
        'matchIntelligenceGeneratedAt':intel.get('generatedAt'),'preXiGeneratedAt':pre.get('generatedAt'),'marketIntelligenceGeneratedAt':market.get('generatedAt')
      },
      'candidates':rows,
      'counts':{'predictions':len(rows),'preKickoff':sum(x['statusAtCapture']=='PRE_KICKOFF' for x in rows),'postKickoff':sum(x['statusAtCapture']=='POST_KICKOFF' for x in rows),'c1':sum(x.get('coveragePack')=='C1' for x in rows),'withIntelligenceOverlay':sum('MATCH_INTELLIGENCE_NOT_CAPTURED' not in x['intelligenceOverlay'].get('intelligenceGaps',[]) for x in rows)}
    }
    outp=ROOT/f'hbt_prospective_card_{date}.json';json.dump(out,open(outp,'w',encoding='utf-8'),indent=2,ensure_ascii=False)
    print(json.dumps({'capturedAt':out['capturedAt'],'counts':out['counts'],'candidates':[{'fixture':f"{x['fixture']['home']} vs {x['fixture']['away']}",'tier':x['tier'],'quality':x['quality'],'probs':x['probs'],'coveragePack':x.get('coveragePack'),'readiness':x['intelligenceOverlay'].get('readinessState'),'gaps':x['intelligenceOverlay'].get('intelligenceGaps')} for x in rows]},indent=2,ensure_ascii=False))
    return 0
if __name__=='__main__':raise SystemExit(main())
