#!/usr/bin/env python3
"""Build the immutable HBT prospective card from the exact frozen-runtime bridge.

The frozen control forecast is authoritative for HBT probabilities. Match-
intelligence overlays are attached downstream and may not alter those numbers.
"""
from __future__ import annotations
import argparse, datetime as dt, json
from pathlib import Path
import hbt_build_prospective_card_v2 as card

ROOT=Path('hbt_live_data')
VERSION='HBT-PROSPECTIVE-FROZEN-BRIDGE-1'

def read(p,default=None):
    try:return json.load(open(p,encoding='utf-8'))
    except Exception:return {} if default is None else default

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',required=True);a=ap.parse_args();date=a.date
    src=ROOT/f'frozen_control_forecast_{date}.json';frozen=read(src)
    if frozen.get('targetDate')!=date:raise SystemExit('frozen forecast target mismatch')
    bridge=frozen.get('bridge') or {}
    maxerr=bridge.get('goldenMaxAbsError')
    if maxerr is None or float(maxerr)>1e-9:raise SystemExit(f'golden parity not proven: {maxerr}')
    intel=read(ROOT/'hbt_1_4_match_intelligence.json');pre=read(ROOT/'pre_xi_context.json');market=read(ROOT/'market_intelligence.json')
    idx_intel=card.fixture_index(intel);idx_pre=card.fixture_index(pre);idx_market=card.fixture_index(market)
    captured=dt.datetime.now(dt.timezone.utc);rows=[];excluded=[]
    for r in frozen.get('predictions') or []:
        f=dict(r.get('fixture') or {})
        ok,reason=card.supported_fixture(f)
        if not ok:
            excluded.append({'fixture':f,'reason':reason});continue
        probs=list(r.get('probs') or []); 
        if len(probs)!=3:continue
        h,d,a3=map(float,probs);key=card.k(f.get('date'),f.get('home'),f.get('away'))
        ir=idx_intel.get(key) or idx_market.get(key) or idx_pre.get(key) or {}
        overlay=card.extract_overlay(ir) if ir else {'readinessState':None,'officialXIConfirmed':False,'intelligenceGaps':['MATCH_INTELLIGENCE_NOT_CAPTURED'],'forensicFamiliesSurfaced':{}}
        time=str(f.get('time') or '00:00')[:5]
        ko=dt.datetime.fromisoformat(f"{date}T{time}:00+00:00")
        rows.append({'fixture':f,'statusAtCapture':'PRE_KICKOFF' if ko>captured else 'POST_KICKOFF','origin':'HBT_EXACT_FROZEN_BRIDGE','coverage':r.get('coverage'),'coveragePack':r.get('coveragePack'),'predictionMode':r.get('predictionMode'),'tier':r.get('tier'),'rawTier':r.get('rawTier'),'quality':r.get('quality'),'resolution':r.get('resolution'),'probs':{'H':h,'D':d,'A':a3},'derivedMarkets':card.market_map(h,d,a3),'intelligenceOverlay':overlay,'surfacingPolicy':{'baseProbabilityChangedByOverlay':False,'overlayCanChangeRiskLabelOrStakeOnlyAfterValidatedRule':False,'overlayPurpose':'Expose knowable match state and gaps; do not alter exact frozen HBT probabilities.'}})
    out={'schemaVersion':'HBT-PROSPECTIVE-CARD-2','version':VERSION,'capturedAt':captured.isoformat().replace('+00:00','Z'),'targetDate':date,'origin':'HBT_EXACT_FROZEN_BRIDGE','policy':{'bookmakerOddsUsedAsPredictiveFeature':False,'bookmakerPriceObservedBeforeCapture':False,'modelRetuned':False,'preMatchCaptureImmutable':True,'postKickoffBackfillAllowed':False,'preserveExistingIntelligence':True,'allValidatedIntelligenceFamiliesRetained':True,'unvalidatedOverlayDoesNotChangeProbability':True,'forensicLearningCanCreateHypothesesButNotAutoPromote':True,'competitionLabelIsEligibilityGate':True,'unsupportedCompetitionsMayNotEnterHBT':True,'exactFrozenRuntimeParityRequired':True,'c1ATierPromotionAllowed':False},'parityDiagnostic':maxerr,'intelligenceSources':{'matchIntelligenceGeneratedAt':intel.get('generatedAt'),'preXiGeneratedAt':pre.get('generatedAt'),'marketIntelligenceGeneratedAt':market.get('generatedAt')},'candidates':rows,'excludedUnsupported':excluded,'counts':{'predictions':len(rows),'excludedUnsupported':len(excluded),'preKickoff':sum(x['statusAtCapture']=='PRE_KICKOFF' for x in rows),'postKickoff':sum(x['statusAtCapture']=='POST_KICKOFF' for x in rows),'c1':sum(x.get('coveragePack')=='C1' for x in rows),'withIntelligenceOverlay':sum('MATCH_INTELLIGENCE_NOT_CAPTURED' not in x['intelligenceOverlay'].get('intelligenceGaps',[]) for x in rows)}}
    json.dump(out,open(ROOT/f'hbt_prospective_card_{date}.json','w',encoding='utf-8'),indent=2,ensure_ascii=False)
    print(json.dumps({'targetDate':date,'parity':maxerr,'counts':out['counts']},indent=2))
    return 0
if __name__=='__main__':raise SystemExit(main())
