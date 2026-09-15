#!/usr/bin/env python3
"""HBT slate discovery / coverage scanner v2.

Rules:
- discover fixtures before ranking;
- reconcile live HBT intelligence separately from predictive output;
- consume only date-matched prospective frozen-control forecast artifacts;
- never infer missing probabilities and never retrain a frozen model;
- keep FULL_MODEL and FALLBACK ranking buckets separate;
- treat a known frozen forecast missing from discovery as a coverage failure.

Bookmaker odds are not fetched or used here.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hbt_live_data"
HBT14 = OUT / "hbt_1_4_match_intelligence.json"
MARKET = OUT / "market_intelligence.json"
PREXI = OUT / "pre_xi_context.json"
OUTPUT = OUT / "slate_scanner.json"
VERSION = "HBT-SLATE-SCANNER-2"
UA = "Mozilla/5.0 (compatible; HBT-Slate-Scanner/2.0)"

FULL_MODEL_LEAGUES = {"en.1", "es.1", "de.1", "it.1", "fr.1"}
FULL_MODEL_SLUGS = {
    "english premier league", "premier league", "spanish laliga", "laliga", "la liga",
    "german bundesliga", "bundesliga", "italian serie a", "serie a", "french ligue 1", "ligue 1",
}
STATUS = {
    "FULL_MODEL", "FALLBACK", "INSUFFICIENT_DATA", "UNSUPPORTED_COMPETITION",
    "SOURCE_FAILURE", "NOT_YET_READY",
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def http_json(url: str, timeout: int = 25) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def key(s: Any) -> str:
    x = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    x = x.replace("&", " and ")
    x = re.sub(r"\b(fc|cf|afc|ac|ssc|sc|rc|club|football|futbol|fussball|calcio|the)\b", " ", x)
    x = re.sub(r"[^a-z0-9]+", " ", x)
    x = " ".join(x.split())
    aliases = {
        "deportivo alaves": "alaves", "real madrid cf": "real madrid",
        "rayo vallecano de madrid": "rayo vallecano",
        "rcd espanyol de barcelona": "espanyol", "rcd espanyol": "espanyol",
        "afc ajax": "ajax", "willem ii tilburg": "willem ii",
        "heart of midlothian": "hearts", "heart of midlothian fc": "hearts",
        "paris saint germain": "psg", "paris sg": "psg",
        "internazionale": "inter", "inter milan": "inter",
        "manchester united": "man united", "manchester city": "man city",
        "tottenham hotspur": "tottenham", "wolverhampton wanderers": "wolves",
        "newcastle united": "newcastle", "west ham united": "west ham",
        "brighton and hove albion": "brighton", "borussia monchengladbach": "monchengladbach",
        "bayern munchen": "bayern munich",
    }
    return aliases.get(x, x)


def day_of(row: dict[str, Any]) -> str:
    v = row.get("kickoff") or row.get("date") or (row.get("fixture") or {}).get("date") or ""
    return str(v)[:10]


def fixture_key(row: dict[str, Any]) -> str:
    fx = row.get("fixture") if isinstance(row.get("fixture"), dict) else row
    return f"{day_of(row)}|{key(fx.get('home'))}|{key(fx.get('away'))}"


def iso_kickoff(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return dt.datetime.fromtimestamp(float(v), tz=dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    s = str(v)
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except Exception:
        return s or None


def parse_espn(date: dt.date) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ds = date.strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={ds}&limit=1000"
    fetched = now(); raw = http_json(url); rows = []
    for e in raw.get("events") or []:
        comps = e.get("competitions") or []; c = comps[0] if comps else {}
        teams = c.get("competitors") or []
        home = next((x for x in teams if x.get("homeAway") == "home"), teams[0] if teams else {})
        away = next((x for x in teams if x.get("homeAway") == "away"), teams[1] if len(teams) > 1 else {})
        hn = str((home.get("team") or {}).get("displayName") or (home.get("team") or {}).get("name") or "").strip()
        an = str((away.get("team") or {}).get("displayName") or (away.get("team") or {}).get("name") or "").strip()
        if not hn or not an: continue
        league = c.get("league") or {}; season = e.get("season") or {}
        label = str(league.get("name") or league.get("abbreviation") or season.get("slug") or "Unknown competition").strip()
        slug = str(season.get("slug") or "").strip()
        rows.append({"source":"ESPN_ALL","sourceFixtureId":str(e.get("id") or ""),"sourceFreshness":fetched,
                     "competition":label,"competitionSlug":slug,"kickoff":iso_kickoff(e.get("date")),"home":hn,"away":an})
    return rows, {"source":"ESPN_ALL","url":url,"fetchedAt":fetched,"status":"loaded","events":len(rows)}


def parse_sofascore(date: dt.date) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ds = date.isoformat(); url = f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{ds}"
    fetched = now(); raw = http_json(url); rows = []
    for e in raw.get("events") or []:
        h, a, t = e.get("homeTeam") or {}, e.get("awayTeam") or {}, e.get("tournament") or {}
        ut = t.get("uniqueTournament") or {}; hn, an = str(h.get("name") or "").strip(), str(a.get("name") or "").strip()
        if not hn or not an: continue
        rows.append({"source":"SOFASCORE","sourceFixtureId":str(e.get("id") or ""),"sourceFreshness":fetched,
                     "competition":str(ut.get("name") or t.get("name") or "Unknown competition"),
                     "competitionSlug":str(ut.get("slug") or t.get("slug") or ""),
                     "kickoff":iso_kickoff(e.get("startTimestamp")),"home":hn,"away":an})
    return rows, {"source":"SOFASCORE","url":url,"fetchedAt":fetched,"status":"loaded","events":len(rows)}


def merge_sources(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        k = fixture_key(row)
        if not k.strip("|"): continue
        if k not in out:
            out[k] = {**row,"fixtureSources":[row["source"]],"sourceFixtureIds":{row["source"]:row.get("sourceFixtureId")}}
        else:
            z = out[k]
            if row["source"] not in z["fixtureSources"]: z["fixtureSources"].append(row["source"])
            z["sourceFixtureIds"][row["source"]] = row.get("sourceFixtureId")
            if (not z.get("competition") or z.get("competition") == "Unknown competition") and row.get("competition"):
                z["competition"], z["competitionSlug"] = row["competition"], row.get("competitionSlug")
    return sorted(out.values(), key=lambda x:(x.get("kickoff") or "",x.get("competition") or "",x.get("home") or ""))


def hbt_index() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    h14, market, pre = read_json(HBT14, {}), read_json(MARKET, {}), read_json(PREXI, {})
    idx: dict[str, dict[str, Any]] = {}
    for source_name, doc in (("HBT14",h14),("MARKET",market),("PREXI",pre)):
        for fid, row in (doc.get("fixtures") or {}).items():
            z = idx.setdefault(fixture_key(row), {"ids":{},"rows":{}})
            z["ids"][source_name], z["rows"][source_name] = fid, row
    return idx, {"hbt14GeneratedAt":h14.get("generatedAt"),"marketGeneratedAt":market.get("generatedAt"),
                 "preXiGeneratedAt":pre.get("generatedAt"),"indexedFixtures":len(idx)}


def frozen_forecast_index(target: dt.date) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    path = OUT / f"frozen_control_forecast_{target.isoformat()}.json"
    doc = read_json(path, {})
    valid = bool(doc.get("schemaVersion") == "HBT-FROZEN-CONTROL-FORECAST-1" and
                 doc.get("targetDate") == target.isoformat() and
                 (doc.get("policy") or {}).get("prospectiveExport") is True and
                 (doc.get("policy") or {}).get("generalFutureLiveFeed") is False)
    rows = doc.get("predictions") or [] if valid else []
    idx = {fixture_key(r): r for r in rows if fixture_key(r).strip("|")}
    meta = {"available":valid,"path":path.name if path.exists() else None,"sourceExportedAt":doc.get("sourceExportedAt") if valid else None,
            "sourceLabVersion":doc.get("sourceLabVersion") if valid else None,"predictions":len(idx),
            "generalFutureLiveFeed":False if valid else None}
    return idx, meta


def completeness(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row: return {"known":False,"score":0.0,"familiesPresent":[]}
    names = ("availabilityContinuity","tactical","playerTeamImpact","shotStoppingGoalkeeper","setPieces","referee",
             "weatherVenue","workload","travel","competitionState","manager","formation","substitutionBehaviour")
    present = [f for f in names if row.get(f) not in (None,{},[],"")]
    return {"known":True,"score":round(len(present)/len(names),4),"familiesPresent":present}


def league_from_hit(hit: dict[str, Any] | None) -> str | None:
    for name in ("HBT14","MARKET","PREXI"):
        row = ((hit or {}).get("rows") or {}).get(name) or {}
        if row.get("league"): return str(row["league"])
    return None


def full_model_comp(public: dict[str, Any], hit: dict[str, Any] | None, fc: dict[str, Any] | None) -> bool:
    league = league_from_hit(hit) or str(((fc or {}).get("fixture") or {}).get("league") or "")
    if league in FULL_MODEL_LEAGUES: return True
    s = key(public.get("competitionSlug") or public.get("competition") or "")
    return any(x in s or s in x for x in FULL_MODEL_SLUGS if s)


def valid_probs(v: Any) -> bool:
    return isinstance(v, list) and len(v) == 3 and all(isinstance(x,(int,float)) and 0 <= float(x) <= 1 for x in v) and abs(sum(v)-1) < 0.02


def classify(public: dict[str, Any], hit: dict[str, Any] | None, fc: dict[str, Any] | None, fc_meta: dict[str, Any]) -> dict[str, Any]:
    rows = (hit or {}).get("rows") or {}; h14, market, pre = rows.get("HBT14") or {}, rows.get("MARKET") or {}, rows.get("PREXI") or {}
    league = league_from_hit(hit) or str(((fc or {}).get("fixture") or {}).get("league") or "") or None
    mode = str((fc or {}).get("predictionMode") or "")
    probs = (fc or {}).get("probs") if fc else None
    if fc and valid_probs(probs) and "FUSION" in mode:
        status, reason = "FULL_MODEL", "Matched a prospective frozen HBT control forecast with Fusion probability output."
    elif fc and valid_probs(probs) and mode.startswith("L0"):
        status, reason = "FALLBACK", "Matched a prospective frozen structural L0 forecast; retained separately from Fusion/full-model confidence."
    elif h14:
        status, reason = "NOT_YET_READY", "Live HBT-1.4 intelligence exists, but no date-matched frozen control probability output is available for ranking."
    elif market or pre:
        status, reason = "NOT_YET_READY", "Fixture exists upstream in HBT context/market feeds, but predictive output is not available in the scanner contract."
    elif full_model_comp(public, hit, fc):
        status, reason = "INSUFFICIENT_DATA", "Competition is in the full-model support contract, but the fixture lacks reconciled predictive output."
    else:
        status, reason = "UNSUPPORTED_COMPETITION", "Fixture was discovered, but no validated full-model or date-matched explicit fallback forecast is available."

    validated = h14.get("validatedEventFamilies") or market.get("validatedEventFamilies") or []
    live_ev = h14.get("eventMarkets") or market.get("eventMarkets") or {}
    score_markets = (fc or {}).get("scoreMarkets")
    rank_ok = status in {"FULL_MODEL","FALLBACK"} and valid_probs(probs)
    return {
        **public,
        "hbtSupportLevel":status,"rankingBucket":status if rank_ok else None,"predictionMode":mode or "NONE",
        "probabilityOutput":probs if valid_probs(probs) else None,"pick":(fc or {}).get("pick"),"pickProbability":(fc or {}).get("pickProb"),
        "tier":(fc or {}).get("tier"),"rawTier":(fc or {}).get("rawTier"),"quality":(fc or {}).get("quality"),
        "forecastCoverage":(fc or {}).get("coverage"),"coveragePack":(fc or {}).get("coveragePack"),"fusionEligible":bool((fc or {}).get("fusionEligible")),
        "predictionSource":({"type":"FROZEN_CONTROL_AUDIT","sourceExportedAt":fc_meta.get("sourceExportedAt"),
                             "sourceLabVersion":fc_meta.get("sourceLabVersion"),"prospectiveForTargetDate":True,"generalFutureLiveFeed":False} if fc else None),
        "intelligenceCompleteness":completeness(h14 or None),"xiState":h14.get("readinessState") or pre.get("intelligenceReadiness"),
        "scoreMarketsExist":bool(score_markets or live_ev),"scoreMarkets":score_markets,
        "validatedEventMarketsExist":bool(validated),"validatedEventFamilies":validated,
        "hbtLeague":league,"hbtFixtureIds":(hit or {}).get("ids") or {},
        "classificationReason":reason,"exclusionReason":None if rank_ok else reason,
        "rankEligible":rank_ok,"rankEligibleFullModel":status == "FULL_MODEL" and rank_ok,"rankEligibleFallback":status == "FALLBACK" and rank_ok,
    }


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--date", help="Target slate date YYYY-MM-DD; defaults to UTC today"); args = ap.parse_args()
    target = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(dt.timezone.utc).date()
    discovered, audits = [], []
    for name, fn in (("ESPN_ALL",parse_espn),("SOFASCORE",parse_sofascore)):
        try:
            rows, audit = fn(target); discovered.extend(rows); audits.append(audit)
        except Exception as exc:
            audits.append({"source":name,"fetchedAt":now(),"status":"failed","events":0,"error":str(exc)[:240]})
    merged = merge_sources(discovered); hidx, feed_health = hbt_index(); fidx, fc_meta = frozen_forecast_index(target)
    fixtures = [classify(row,hidx.get(fixture_key(row)),fidx.get(fixture_key(row)),fc_meta) for row in merged]
    discovered_keys = {fixture_key(x) for x in merged}; orphan_keys = sorted(set(fidx)-discovered_keys)
    orphans = [{"fixture":(fidx[k].get("fixture") or {}),"predictionMode":fidx[k].get("predictionMode"),"tier":fidx[k].get("tier"),
                "reason":"Known prospective HBT forecast was not rediscovered by configured public slate sources."} for k in orphan_keys]

    loaded = any(a.get("status") == "loaded" for a in audits); source_ok = bool(merged) and loaded
    if not fixtures and not loaded:
        fixtures = [{"fixtureSources":[],"sourceFixtureIds":{},"sourceFreshness":now(),"competition":None,"competitionSlug":None,
                     "kickoff":None,"home":None,"away":None,"hbtSupportLevel":"SOURCE_FAILURE","rankingBucket":None,"predictionMode":"NONE",
                     "probabilityOutput":None,"classificationReason":"All public discovery sources failed.","exclusionReason":"All public discovery sources failed.",
                     "rankEligible":False,"rankEligibleFullModel":False,"rankEligibleFallback":False}]
    counts = {s:sum(1 for x in fixtures if x.get("hbtSupportLevel") == s) for s in sorted(STATUS)}
    unsupported = sorted({str(x.get("competition")) for x in fixtures if x.get("hbtSupportLevel") == "UNSUPPORTED_COMPETITION" and x.get("competition")})
    full_rank = [x for x in fixtures if x.get("rankEligibleFullModel")]; fallback_rank = [x for x in fixtures if x.get("rankEligibleFallback")]
    payload = {
        "schemaVersion":"HBT-SLATE-2","version":VERSION,"generatedAt":now(),"targetDate":target.isoformat(),
        "policy":{"discoveryBeforeRanking":True,"bookmakerOddsUsed":False,"frozenPredictiveModelMutated":False,"retrainingPerformed":False,
                  "fallbackFabricated":False,"dateScopedFrozenAuditAdapter":True,"rankingAllowedOnlyAfterDiscovery":True,"testAImmutable":True,
                  "missingForecastMeansUnknown":True,"fullModelAndFallbackNeverMerged":True},
        "sourceAudit":audits,"hbtFeedHealth":feed_health,"frozenForecastAdapter":fc_meta,
        "coverage":{"fixturesDiscovered":len(merged),"classifiedRows":len(fixtures),**counts,"forecastRowsAvailable":len(fidx),
                    "forecastRowsMatched":len(fidx)-len(orphans),"knownForecastsMissedByDiscovery":len(orphans),
                    "knownForecastDiscoveryMisses":orphans,"unsupportedCompetitions":unsupported},
        "rankingGate":{"sourceDiscoverySucceeded":source_ok,"knownForecastCoverageComplete":not orphans,
                       "discoveryComplete":bool(source_ok and not orphans),"rankEligibleFixtures":len(full_rank)+len(fallback_rank),
                       "fullModelRankEligible":len(full_rank),"fallbackRankEligible":len(fallback_rank),
                       "note":"Discovery completeness means configured public sources reconciled all known date-scoped HBT forecasts; it is not a claim of universal world-football coverage."},
        "fixtures":fixtures,
    }
    write_json(OUTPUT,payload)
    print("HBT slate scanner",target,payload["coverage"],payload["rankingGate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
