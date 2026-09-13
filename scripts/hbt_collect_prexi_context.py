#!/usr/bin/env python3
"""HBT-1.2R prospective P1 + manager shadow collector.

Research only. This feed never changes HBT-1.1.2 probabilities, tiers, or picks.
It adds current injury reports, expected-XI estimates from past confirmed lineups,
and prospective coach-change tracking for later validation.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
from pathlib import Path
from typing import Any

import hbt_collect_players_espn as p

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hbt_live_data"
CTX_CACHE = OUT / "_espn_prexi_context_cache.json"
MANIFEST = OUT / "manifest.json"
OUTPUT = OUT / "pre_xi_context.json"
SCHEMA = "HBT-LIVE-DATA-1"


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def flatten(obj: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        out.append(obj)
        for v in obj.values(): out.extend(flatten(v))
    elif isinstance(obj, list):
        for v in obj: out.extend(flatten(v))
    return out


def player_key(s: str) -> str:
    return p.team_key(s)


def injury_rows(raw: Any) -> list[dict[str, Any]]:
    """Normalize the flexible ESPN injury-report shapes without treating missing as healthy."""
    out, seen = [], set()
    for d in flatten(raw):
        ath = d.get("athlete") if isinstance(d.get("athlete"), dict) else None
        name = (ath or {}).get("displayName") or (ath or {}).get("fullName") or (ath or {}).get("shortName") or ""
        pid = str((ath or {}).get("id") or "")
        if not name and isinstance(d.get("player"), dict):
            q = d["player"]; name = q.get("displayName") or q.get("fullName") or q.get("name") or ""; pid = str(q.get("id") or "")
        if not name and not pid: continue
        bits = []
        for k in ("status","type","detail","details","description","shortComment","longComment","comment","returnDate"):
            v = d.get(k)
            if isinstance(v, dict): bits += [str(x) for x in v.values() if isinstance(x,(str,int,float))]
            elif isinstance(v,(str,int,float)): bits.append(str(v))
        detail = " | ".join(bits); low = detail.lower()
        if re.search(r"suspend|ban|red card", low): cls, hard = "suspended", True
        elif re.search(r"question|doubt|day.to.day|game.?time|probable", low): cls, hard = "doubtful", False
        elif re.search(r"out|injur|illness|fracture|strain|sprain|surgery|acl|mcl|hamstring|ankle|knee|muscle|groin", low): cls, hard = "injured", True
        else: cls, hard = "reported", False
        sig = f"{pid or player_key(name)}|{cls}|{detail}"
        if sig in seen: continue
        seen.add(sig)
        out.append({"id":pid,"name":name,"class":cls,"hardUnavailable":hard,"detail":detail[:600]})
    return out


def fetch_injuries(event: dict[str, Any], team_id: str) -> tuple[list[dict[str, Any]], str, str]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{event['espnLeague']}/teams/{team_id}/injuries"
    try:
        raw = p.http_json(url,15,2)
        rows = injury_rows(raw)
        # Empty soccer injury responses are not interpreted as "everyone healthy".
        # They are kept as unknown/empty-source state until corroborating data exists.
        return rows, ("loaded" if rows else "loaded-empty-unknown"), url
    except Exception as e:
        return [], f"failed: {e}", url


def coach_name(raw: Any) -> str:
    if not isinstance(raw, dict): return ""
    c = raw.get("coach")
    if isinstance(c,str): return c.strip()
    if isinstance(c,dict):
        for k in ("displayName","fullName","name","shortName"):
            if c.get(k): return str(c[k]).strip()
    for x in raw.get("coaches") or []:
        if isinstance(x,dict):
            for k in ("displayName","fullName","name","shortName"):
                if x.get(k): return str(x[k]).strip()
    for d in flatten(raw):
        role = str(d.get("role") or d.get("position") or d.get("type") or d.get("title") or "").lower()
        if "coach" not in role and "manager" not in role: continue
        for k in ("displayName","fullName","name","shortName"):
            if d.get(k): return str(d[k]).strip()
    return ""


def fetch_coach(event: dict[str, Any], team_id: str, year: int) -> tuple[str,str,str]:
    # Soccer site rosters often omit coach metadata. Prefer the season/team coaches
    # core endpoint, then fall back to the site roster if necessary.
    urls = [
        f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/{event['espnLeague']}/seasons/{year}/teams/{team_id}/coaches",
        f"https://site.api.espn.com/apis/site/v2/sports/soccer/{event['espnLeague']}/teams/{team_id}/roster",
    ]
    errors=[]
    for url in urls:
        try:
            raw=p.http_json(url,15,2)
            name=coach_name(raw)
            if not name and isinstance(raw,dict):
                for item in raw.get("items") or []:
                    if isinstance(item,dict) and item.get("$ref"):
                        try:
                            prof=p.http_json(str(item["$ref"]).replace("http://","https://"),10,1)
                            name=coach_name(prof)
                            if not name and isinstance(prof,dict):
                                for k in ("displayName","fullName","name","shortName"):
                                    if prof.get(k): name=str(prof[k]).strip(); break
                        except Exception as exc: errors.append(str(exc))
                    if name: break
            if name: return name,"loaded",url
        except Exception as e: errors.append(str(e))
    return "",("loaded-no-coach" if not errors else "unresolved: "+errors[-1][:180]),urls[0]


def track_coach(cache: dict[str,Any], event: dict[str,Any], team_id: str, team: str, coach: str, now: dt.datetime) -> dict[str,Any]:
    k = f"{event['league']}|{team_id or p.team_key(team)}"; teams = cache.setdefault("teams",{}); old = teams.get(k) if isinstance(teams.get(k),dict) else None
    row = {"team":team,"teamId":team_id,"coach":coach or None,"firstSeenAt":None,"lastSeenAt":p.iso_now(),"previousCoach":None,"changeDetectedAt":None,"changedThisRun":False,"tenureLowerBoundDays":None,"trackingStatus":"prospective lower-bound only" if coach else "coach unavailable"}
    if not coach: return row
    if old and old.get("coach") == coach:
        row["firstSeenAt"] = old.get("firstSeenAt") or old.get("lastSeenAt") or p.iso_now(); row["previousCoach"] = old.get("previousCoach"); row["changeDetectedAt"] = old.get("changeDetectedAt")
    elif old and old.get("coach"):
        row["firstSeenAt"] = p.iso_now(); row["previousCoach"] = old.get("coach"); row["changeDetectedAt"] = p.iso_now(); row["changedThisRun"] = True
    else: row["firstSeenAt"] = p.iso_now()
    f = p.parse_dt(row["firstSeenAt"])
    if f: row["tenureLowerBoundDays"] = max(0.0,(now-f).total_seconds()/86400)
    teams[k] = {x:row[x] for x in ("team","teamId","coach","firstSeenAt","lastSeenAt","previousCoach","changeDetectedAt")}
    return row


def prior_lineups_extended(event: dict[str,Any], side: str, pcache: dict[str,Any], year: int) -> tuple[list[list[dict[str,Any]]], list[int]]:
    """Use only completed matches before kickoff, spanning current and previous season.

    This is research-only and fixes the early-season cold start without inventing current
    availability. Previous-season lineups naturally decay because only the most recent
    six confirmed lineups are retained.
    """
    team_id = event["homeId"] if side == "home" else event["awayId"]
    kickoff = p.parse_dt(event.get("date")) or dt.datetime.now(dt.timezone.utc)
    prev=[]
    for sy in (year,year-1):
        for raw in p.get_team_schedule(event["espnLeague"],team_id,sy,pcache):
            er=p.event_record(raw,event["league"],event["espnLeague"])
            if not er or er["id"]==event["id"] or not er.get("completed"): continue
            edt=p.parse_dt(er.get("date"))
            if not edt or edt>=kickoff: continue
            er["historySeason"]=sy; prev.append(er)
    dedup={x["id"]:x for x in prev}; prev=sorted(dedup.values(),key=lambda x:x.get("date") or "")[-8:]
    rows=[]; used=[]
    for e in prev:
        lu=p.get_summary(e,pcache,force=False)
        if not lu: continue
        eside="home" if str(e.get("homeId"))==str(team_id) else "away"
        pl=lu.get(eside) or []
        if sum(x.get("status")=="starting" for x in pl)>=10:
            rows.append(pl); used.append(int(e.get("historySeason") or year))
        time.sleep(.03)
    return rows[-6:],used[-6:]


def p1_snapshot(event: dict[str,Any], side: str, year: int, pcache: dict[str,Any], injuries: list[dict[str,Any]], injury_known: bool) -> dict[str,Any] | None:
    hist, history_seasons = prior_lineups_extended(event,side,pcache,year)
    if len(hist) < p.MIN_PRIOR_MATCHDAYS: return None
    universe = {}
    for m in hist:
        for q in m:
            pid = str(q.get("id") or player_key(q.get("name") or "")); universe[pid] = {"id":pid,"name":q.get("name") or "","pos":q.get("pos") or ""}
    info = []
    for q in universe.values():
        sts = []
        for m in hist:
            f = next((x for x in m if str(x.get("id")) == q["id"]),None); sts.append(f.get("status") if f else "not_in_squad")
        imp,n = p.player_importance(sts); info.append({**q,"importance":imp,"priorN":n})
    ideal = p.select_xi(info)
    if len(ideal) < 10: return None
    byid = {str(x.get("id")):x for x in injuries if x.get("id")}; byname = {player_key(x.get("name") or ""):x for x in injuries if x.get("name")}
    hard,doubt = set(),set()
    for q in info:
        r = byid.get(q["id"]) or byname.get(player_key(q["name"]))
        if not r: continue
        if r.get("hardUnavailable"): hard.add(q["id"])
        elif r.get("class") == "doubtful": doubt.add(q["id"])
    expected = p.select_xi([x for x in info if x["id"] not in hard])
    if len(expected) < 10: return None
    ideal_strength = sum(float(x.get("importance") or 0) for x in ideal) or 1.0; exp_strength = sum(float(x.get("importance") or 0) for x in expected)
    missing = [x for x in ideal if x["id"] in hard]; doubtful = [x for x in ideal if x["id"] in doubt]
    prev = [x for x in hist[-1] if x.get("status") == "starting"]; prev_ids = {str(x.get("id")) for x in prev}; exp_ids = {x["id"] for x in expected}
    overlap = len(prev_ids & exp_ids)/11.0; pg = next((x for x in prev if x.get("pos")=="GK"),None); eg = next((x for x in expected if x.get("pos")=="GK"),None); same_gk = 1.0 if pg and eg and str(pg.get("id"))==eg["id"] else 0.0
    return {"priorMatches":len(hist),"historySeasonsUsed":history_seasons,"injuryAvailabilityKnown":bool(injury_known),"availabilityLoss":(p.clip(sum(float(x.get("importance") or 0) for x in missing)/ideal_strength,0,1) if injury_known else None),"replacementQuality":(p.replacement_quality(ideal,expected) if injury_known else None),"expectedXIRatio":(p.clip(exp_strength/ideal_strength,0,1.25) if injury_known else None),"expectedContinuity":.85*p.clip(overlap,0,1)+.15*same_gk,"hardUnavailableIdealN":(len(missing) if injury_known else None),"hardUnavailableIdeal":([x["name"] for x in missing] if injury_known else []),"doubtfulIdealN":(len(doubtful) if injury_known else None),"doubtfulIdealWeight":(p.clip(sum(float(x.get("importance") or 0) for x in doubtful)/ideal_strength,0,1) if injury_known else None),"doubtfulIdeal":([x["name"] for x in doubtful] if injury_known else []),"idealXI":[x["name"] for x in ideal],"expectedXI":[x["name"] for x in expected]}


def main() -> int:
    OUT.mkdir(parents=True,exist_ok=True); now = dt.datetime.now(dt.timezone.utc); year = now.year if now.month>=7 else now.year-1
    pcache = p.read_cache(); ccache = read_json(CTX_CACHE,{"teams":{}}); ccache.setdefault("teams",{})
    events,audit = [],[]
    for delta in range(-1,5):
        rows,a = p.fetch_events_for_day(now.date()+dt.timedelta(days=delta)); events += rows; audit += a
    fixtures,seen,injcache,coachcache = {},set(),{},{}
    for e in events:
        if e["id"] in seen or e.get("completed"): continue
        seen.add(e["id"]); kick = p.parse_dt(e.get("date"))
        if not kick or (kick-now).total_seconds()/3600 < -2: continue
        key = f"{kick.date().isoformat()}|{p.team_key(e['home'])}|{p.team_key(e['away'])}"; sides={}
        for side in ("home","away"):
            tid = e["homeId"] if side=="home" else e["awayId"]; name = e["home"] if side=="home" else e["away"]
            ik=f"{e['espnLeague']}|{tid}"; injuries,istatus,iurl = injcache.setdefault(ik,fetch_injuries(e,tid)); coach,cstatus,curl = coachcache.setdefault(ik,fetch_coach(e,tid,year)); manager = track_coach(ccache,e,tid,name,coach,now)
            injury_known=(istatus=="loaded"); snap = p1_snapshot(e,side,year,pcache,injuries,injury_known)
            sides[side] = {"teamId":tid,"team":name,"injurySourceStatus":istatus,"injurySource":iurl,"injuryReport":injuries,"snapshot":snap,"manager":manager,"coachSourceStatus":cstatus,"coachSource":curl}
            time.sleep(.03)
        H,A = sides["home"]["snapshot"],sides["away"]["snapshot"]; features = None
        if H and A:
            availability_known=bool(H.get("injuryAvailabilityKnown") and A.get("injuryAvailabilityKnown"))
            features={"availabilityKnown":availability_known,"availabilityAdv":((A["availabilityLoss"]-H["availabilityLoss"]) if availability_known else None),"replacementQualityAdv":((H["replacementQuality"]-A["replacementQuality"]) if availability_known else None),"expectedXIStrengthDiff":((H["expectedXIRatio"]-A["expectedXIRatio"]) if availability_known else None),"expectedContinuityDiff":H["expectedContinuity"]-A["expectedContinuity"],"doubtfulWeightDiff":((H["doubtfulIdealWeight"]-A["doubtfulIdealWeight"]) if availability_known else None)}
        reasons=[]
        for side in ("home","away"):
            if sides[side]["injurySourceStatus"].startswith("failed"): reasons.append(f"{side} injury source failed")
            elif sides[side]["injurySourceStatus"]=="loaded-empty-unknown": reasons.append(f"{side} injury feed empty; availability not assumed healthy")
            if sides[side]["snapshot"] is None: reasons.append(f"{side} insufficient prior confirmed-lineup history")
        fixtures[key] = {"ok":bool(features),"availabilityKnown":bool(features and features.get("availabilityKnown")),"eventId":e["id"],"league":e["league"],"home":e["home"],"away":e["away"],"kickoff":e["date"],"fetchedAt":p.iso_now(),"source":"ESPN prospective P1 shadow collector","researchOnly":True,"reason":"; ".join(reasons),"features":features,"homeDetail":sides["home"],"awayDetail":sides["away"],"manager":manager,"managerFeatures":{"homeCoach":sides["home"]["manager"].get("coach"),"awayCoach":sides["away"]["manager"].get("coach"),"homeManagerChangedDetected":bool(sides["home"]["manager"].get("changedThisRun")),"awayManagerChangedDetected":bool(sides["away"]["manager"].get("changedThisRun")),"homeTenureLowerBoundDays":sides["home"]["manager"].get("tenureLowerBoundDays"),"awayTenureLowerBoundDays":sides["away"]["manager"].get("tenureLowerBoundDays"),"validatedForPrediction":False},"predictionPolicy":"SHADOW ONLY — never changes HBT-1.1.2 deployed probabilities or tier"}
    generated = p.iso_now(); payload = {"schemaVersion":SCHEMA,"generatedAt":generated,"seasonStartYear":year,"researchVersion":"HBT-1.2R-P1-MGR-Shadow","policy":{"researchOnly":True,"feedsBackIntoPrediction":False,"oddsUsed":False,"missingInjuryDataIsZero":False,"earlySeasonHistory":"current + previous season confirmed lineups; most recent six only","managerTenure":"prospective lower bound from first observation; not historical tenure","promotionGate":"requires separate causal validation before any coefficient or tier change"},"fixtures":fixtures,"sourceAudit":audit}
    p.write_json(OUTPUT,payload); p.write_json(p.CACHE_PATH,pcache); p.write_json(CTX_CACHE,ccache)
    m = read_json(MANIFEST,{"schemaVersion":SCHEMA,"files":{},"freshness":{},"sourceAudit":{},"policy":{}}); m.setdefault("files",{})["preXiContext"] = OUTPUT.name; m.setdefault("freshness",{})["preXiContextMaxAgeMinutes"] = 60; m.setdefault("sourceAudit",{})["preXiContext"] = audit; m.setdefault("policy",{})["preXiShadow"] = "ESPN injuries + prior confirmed lineups + prospective coach tracking; research only"; m["generatedAt"] = generated; m["seasonStartYear"] = year; p.write_json(MANIFEST,m)
    print("P1 shadow feed:",len(fixtures),"fixtures;",sum(1 for x in fixtures.values() if x.get("ok")),"lineup-feature-complete;",sum(1 for x in fixtures.values() if x.get("availabilityKnown")),"availability-known;",sum(len(x["homeDetail"]["injuryReport"])+len(x["awayDetail"]["injuryReport"]) for x in fixtures.values()),"injury rows;",sum(1 for x in fixtures.values() if x.get("managerFeatures",{}).get("homeCoach"))+sum(1 for x in fixtures.values() if x.get("managerFeatures",{}).get("awayCoach")),"coach sides")
    return 0

if __name__ == "__main__": raise SystemExit(main())