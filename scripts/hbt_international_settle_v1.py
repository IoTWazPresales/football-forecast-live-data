#!/usr/bin/env python3
"""Settle immutable HBT international prospective evidence.

Only scores rows that were captured pre-kickoff and marked cleanProspectiveEligible.
It never refits/retunes the model and never reads bookmaker prices.
"""
from __future__ import annotations
import argparse, datetime as dt, json, math, urllib.request
from pathlib import Path
from typing import Any

import hbt_international_challenger_v1 as v1

ROOT=Path(__file__).resolve().parents[1]
INTL=ROOT/"hbt_live_data"/"international"
UA="Mozilla/5.0 (compatible; HBT-1.4-International-Settlement/1.0)"

def read(p:Path,default:Any)->Any:
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return default

def write(p:Path,obj:Any)->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_suffix(p.suffix+".tmp")
    t.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    t.replace(p)

def fetch_summary(eid:str)->dict[str,Any]:
    url=f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/summary?event={eid}"
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=20) as r:
        return json.loads(r.read().decode("utf-8","replace"))

def outcome(summary:dict[str,Any],home:str,away:str)->dict[str,Any]|None:
    h=(summary.get("header") or {})
    comps=h.get("competitions") or []
    c=comps[0] if comps else {}
    status=((c.get("status") or {}).get("type") or {})
    if not bool(status.get("completed")):
        return None
    teams=c.get("competitors") or []
    hr=next((x for x in teams if x.get("homeAway")=="home"),None)
    ar=next((x for x in teams if x.get("homeAway")=="away"),None)
    if not hr or not ar:return None
    hn=str((hr.get("team") or {}).get("displayName") or (hr.get("team") or {}).get("name") or "")
    an=str((ar.get("team") or {}).get("displayName") or (ar.get("team") or {}).get("name") or "")
    if v1.norm(hn)!=v1.norm(home) or v1.norm(an)!=v1.norm(away):
        return {"identityMismatch":True,"observedHome":hn,"observedAway":an}
    try:
        hg=int(float(hr.get("score"))); ag=int(float(ar.get("score")))
    except Exception:return None
    return {"identityMismatch":False,"homeGoals":hg,"awayGoals":ag,"result":"H" if hg>ag else "A" if ag>hg else "D"}

def score(rows:list[dict[str,Any]], field:str)->dict[str,Any]:
    ll=br=0.0; hit=0; n=0
    for r in rows:
        p=(r.get(field) or {})
        if not all(isinstance(p.get(k),(int,float)) for k in ("H","D","A")):continue
        y={"H":0,"D":1,"A":2}[r["result"]]; q=[float(p["H"]),float(p["D"]),float(p["A"])]
        ll += -math.log(max(q[y],1e-15))
        one=[0.0,0.0,0.0]; one[y]=1.0
        br += sum((q[i]-one[i])**2 for i in range(3))
        hit += int(max(range(3),key=lambda i:q[i])==y); n+=1
    return {"n":n,"logLoss":ll/n if n else None,"brier":br/n if n else None,"accuracy":hit/n if n else None}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--all-unsettled",action="store_true")
    args=ap.parse_args()
    dates=[]
    if args.date: dates=[args.date]
    elif args.all_unsettled:
        dates=sorted(p.stem.rsplit("_",1)[-1] for p in INTL.glob("hbt_international_intelligence_*.json"))
    else: raise SystemExit("provide --date or --all-unsettled")
    done=[]
    for d in dates:
        src=INTL/f"hbt_international_intelligence_{d}.json"
        if not src.exists(): src=INTL/f"hbt_international_prospective_{d}.json"
        if not src.exists(): continue
        dest=INTL/f"hbt_international_settlement_{d}.json"
        doc=read(src,{})
        settled=[]; pending=[]; blocked=[]
        for row in doc.get("prospectiveCandidates") or []:
            if row.get("cleanProspectiveEligible") is not True:
                blocked.append({"fixture":row.get("fixture"),"reason":"not cleanProspectiveEligible"}); continue
            eid=str(row.get("sourceFixtureId") or "")
            fx=row.get("fixture") or {}
            if not eid:
                blocked.append({"fixture":fx,"reason":"missing sourceFixtureId"}); continue
            try: obs=outcome(fetch_summary(eid),str(fx.get("home") or ""),str(fx.get("away") or ""))
            except Exception as exc:
                pending.append({"fixture":fx,"reason":f"source error: {str(exc)[:160]}"}); continue
            if obs is None:
                pending.append({"fixture":fx,"reason":"not completed"}); continue
            if obs.get("identityMismatch"):
                blocked.append({"fixture":fx,"reason":"identity mismatch","observed":obs}); continue
            final_probs=row.get("probs") or {}
            base_probs=row.get("baseStructuralProbabilityBeforeRecentInteraction") or final_probs
            settled.append({
                "fixture":fx,"sourceFixtureId":eid,"domain":row.get("domain"),
                "result":obs["result"],"score":{"home":obs["homeGoals"],"away":obs["awayGoals"]},
                "structuralProbs":base_probs,"challengerProbs":final_probs,
                "challengerPick":row.get("pick"),"challengerPickProbability":row.get("pickProbability"),
            })
        m_base=score(settled,"structuralProbs"); m_ch=score(settled,"challengerProbs")
        improves=bool(m_base["n"] and m_ch["logLoss"]<m_base["logLoss"] and m_ch["brier"]<m_base["brier"])
        out={
            "schemaVersion":"HBT-INTERNATIONAL-SETTLEMENT-1","version":"HBT-1.4-INTERNATIONAL-SETTLEMENT-1",
            "generatedAt":dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00","Z"),
            "targetDate":d,"source":src.name,
            "policy":{"prospectiveOnly":True,"cleanRowsOnly":True,"identityVerified":True,"bookmakerOddsRead":False,
                      "retrainingPerformed":False,"retuningPerformed":False,"automaticPromotion":False,"automaticFunding":False},
            "summary":{"cleanSettled":len(settled),"pending":len(pending),"blocked":len(blocked)},
            "metrics":{"structuralOnly":m_base,"recentInteractionChallenger":m_ch,
                       "recentInteractionImprovesLogLossAndBrierOnThisProspectiveSample":improves,
                       "promotionEvidenceSufficient":False,
                       "note":"Small clean prospective samples are confirmatory/hypothesis evidence only; promotion still requires accumulated prospective confirmation and full interaction/ablation gates."},
            "settled":settled,"pending":pending,"blocked":blocked,
        }
        write(dest,out); done.append({"date":d,"summary":out["summary"],"metrics":out["metrics"]})
    print(json.dumps(done,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
