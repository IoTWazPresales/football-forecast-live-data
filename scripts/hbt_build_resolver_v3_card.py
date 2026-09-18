import json
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path('hbt_live_data')
SRC=ROOT/'hbt_broad_shadow_forecast_2026-09-18_resolver_v3.json'
OUT=ROOT/'hbt_18sep_resolver_v3_candidates.json'
data=json.load(open(SRC,encoding='utf-8'))
captured=datetime.now(timezone.utc)
rows=[]
for r in data.get('predictions',[]):
    f=r['fixture']; h,d,a=map(float,r['probs']); q=float(r.get('quality') or 0)
    ko=datetime.fromisoformat(f"{f['date']}T{f.get('time','00:00')}:00+00:00")
    status='PRE_KICKOFF' if ko>captured else 'POST_KICKOFF'
    hd=h/(h+a) if h+a else None; ad=a/(h+a) if h+a else None
    rows.append({
        'fixture':f,
        'statusAtCapture':status,
        'origin':'HBT_SHADOW_RESOLVER_V3',
        'coverage':r.get('coverage'),
        'coveragePack':r.get('coveragePack'),
        'predictionMode':r.get('predictionMode'),
        'tier':r.get('tier'),
        'rawTier':r.get('rawTier'),
        'quality':q,
        'resolution':r.get('resolution'),
        'probs':{'H':h,'D':d,'A':a},
        'derivedMarkets':{
            'HOME_WIN':{'p':h,'fairOdds':1/h if h else None},
            'DRAW':{'p':d,'fairOdds':1/d if d else None},
            'AWAY_WIN':{'p':a,'fairOdds':1/a if a else None},
            '1X':{'p':h+d,'fairOdds':1/(h+d) if h+d else None},
            'X2':{'p':a+d,'fairOdds':1/(a+d) if a+d else None},
            '12':{'p':h+a,'fairOdds':1/(h+a) if h+a else None},
            'HOME_DNB':{'conditionalP':hd,'winP':h,'pushP':d,'lossP':a,'fairOdds':(h+a)/h if h else None},
            'AWAY_DNB':{'conditionalP':ad,'winP':a,'pushP':d,'lossP':h,'fairOdds':(h+a)/a if a else None}
        }
    })
out={
    'schemaVersion':'HBT-18SEP-RESOLVER-V3-CANDIDATES-1',
    'capturedAt':captured.isoformat().replace('+00:00','Z'),
    'targetDate':'2026-09-18',
    'origin':'HBT_SHADOW_RESOLVER_V3',
    'policy':{
        'externalFootballObservationUsed':False,
        'bookmakerOddsUsedAsPredictiveFeature':False,
        'bookmakerPriceObservedBeforeCapture':False,
        'modelRetuned':False,
        'competitionLabelIsEligibilityGate':False,
        'genderNamespaceSeparated':True,
        'youthReserveNamespaceSeparated':True,
        'uniqueClubSignatureResolution':True,
        'c1UsesFrozenL0StructuralWeights':True,
        'c1ATierPromotionAllowed':False,
        'derivedMarketsAreExactAlgebraFromHDA':True,
        'postKickoffBackfillAllowed':False
    },
    'parityDiagnostic':data.get('bridge',{}).get('goldenMaxAbsError'),
    'c1StateAudit':data.get('bridge',{}).get('c1StateAudit'),
    'candidates':rows,
    'counts':{
        'predictions':len(rows),
        'preKickoff':sum(x['statusAtCapture']=='PRE_KICKOFF' for x in rows),
        'postKickoff':sum(x['statusAtCapture']=='POST_KICKOFF' for x in rows),
        'c1':sum(x.get('coveragePack')=='C1' for x in rows)
    }
}
json.dump(out,open(OUT,'w',encoding='utf-8'),indent=2)
print(json.dumps({
    'capturedAt':out['capturedAt'],
    'counts':out['counts'],
    'c1StateAudit':out['c1StateAudit'],
    'candidates':[
        {'fixture':f"{x['fixture']['home']} vs {x['fixture']['away']}",
         'league':x['fixture'].get('league'),
         'competition':x['fixture'].get('competition'),
         'coveragePack':x.get('coveragePack'),'tier':x.get('tier'),'quality':x.get('quality'),'probs':x.get('probs')}
        for x in rows
    ]
},indent=2,ensure_ascii=False))
