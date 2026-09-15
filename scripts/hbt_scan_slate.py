#!/usr/bin/env python3
"""HBT slate discovery / coverage scanner.

Discovery happens before model ranking. The scanner discovers the public football
slate for a target date, reconciles it against existing HBT live outputs, and
classifies every discovered fixture without changing any predictive model.

Primary discovery: ESPN cross-league scoreboard.
Secondary discovery: SofaScore daily schedule when reachable. Failure of either
source is explicit and never converted to an empty slate.

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
VERSION = "HBT-SLATE-SCANNER-1"
UA = "Mozilla/5.0 (compatible; HBT-Slate-Scanner/1.0)"

FULL_MODEL_LEAGUES = {
    "en.1": {"english-premier-league", "premier-league"},
    "es.1": {"spanish-laliga", "laliga", "la-liga"},
    "de.1": {"german-bundesliga", "bundesliga"},
    "it.1": {"italian-serie-a", "serie-a"},
    "fr.1": {"french-ligue-1", "ligue-1"},
}

STATUS = {
    "FULL_MODEL",
    "FALLBACK",
    "INSUFFICIENT_DATA",
    "UNSUPPORTED_COMPETITION",
    "SOURCE_FAILURE",
    "NOT_YET_READY",
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
        "deportivo alaves": "alaves",
        "real madrid cf": "real madrid",
        "paris saint germain": "psg",
        "paris sg": "psg",
        "internazionale": "inter",
        "inter milan": "inter",
        "manchester united": "man united",
        "manchester city": "man city",
        "tottenham hotspur": "tottenham",
        "wolverhampton wanderers": "wolves",
        "newcastle united": "newcastle",
        "west ham united": "west ham",
        "brighton and hove albion": "brighton",
        "borussia monchengladbach": "monchengladbach",
        "bayern munchen": "bayern munich",
    }
    return aliases.get(x, x)


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


def competition_from_espn(event: dict[str, Any]) -> tuple[str, str]:
    season = event.get("season") or {}
    slug = str(season.get("slug") or "").strip()
    label = ""
    comp = event.get("competitions") or []
    if comp:
        league = (comp[0] or {}).get("league") or {}
        label = str(league.get("name") or league.get("abbreviation") or "").strip()
    if not label:
        label = slug.replace("-", " ").title() if slug else "Unknown competition"
    return label, slug


def parse_espn(date: dt.date) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ds = date.strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={ds}&limit=1000"
    fetched = now()
    raw = http_json(url)
    rows: list[dict[str, Any]] = []
    for e in raw.get("events") or []:
        comps = e.get("competitions") or []
        c = comps[0] if comps else {}
        teams = c.get("competitors") or []
        home = next((x for x in teams if x.get("homeAway") == "home"), teams[0] if teams else {})
        away = next((x for x in teams if x.get("homeAway") == "away"), teams[1] if len(teams) > 1 else {})
        hn = str((home.get("team") or {}).get("displayName") or (home.get("team") or {}).get("name") or "").strip()
        an = str((away.get("team") or {}).get("displayName") or (away.get("team") or {}).get("name") or "").strip()
        if not hn or not an:
            continue
        cname, cslug = competition_from_espn(e)
        rows.append({
            "source": "ESPN_ALL",
            "sourceFixtureId": str(e.get("id") or ""),
            "sourceFreshness": fetched,
            "competition": cname,
            "competitionSlug": cslug,
            "kickoff": iso_kickoff(e.get("date")),
            "home": hn,
            "away": an,
        })
    return rows, {"source": "ESPN_ALL", "url": url, "fetchedAt": fetched, "status": "loaded", "events": len(rows)}


def parse_sofascore(date: dt.date) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ds = date.isoformat()
    url = f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{ds}"
    fetched = now()
    raw = http_json(url)
    rows: list[dict[str, Any]] = []
    for e in raw.get("events") or []:
        h = e.get("homeTeam") or {}
        a = e.get("awayTeam") or {}
        t = e.get("tournament") or {}
        ut = t.get("uniqueTournament") or {}
        hn = str(h.get("name") or "").strip()
        an = str(a.get("name") or "").strip()
        if not hn or not an:
            continue
        rows.append({
            "source": "SOFASCORE",
            "sourceFixtureId": str(e.get("id") or ""),
            "sourceFreshness": fetched,
            "competition": str(ut.get("name") or t.get("name") or "Unknown competition"),
            "competitionSlug": str(ut.get("slug") or t.get("slug") or ""),
            "kickoff": iso_kickoff(e.get("startTimestamp")),
            "home": hn,
            "away": an,
        })
    return rows, {"source": "SOFASCORE", "url": url, "fetchedAt": fetched, "status": "loaded", "events": len(rows)}


def fixture_key(row: dict[str, Any]) -> str:
    day = str(row.get("kickoff") or "")[:10]
    return f"{day}|{key(row.get('home'))}|{key(row.get('away'))}"


def merge_sources(primary: list[dict[str, Any]], secondary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in primary + secondary:
        k = fixture_key(row)
        if not k.strip("|"):
            continue
        if k not in out:
            out[k] = {**row, "fixtureSources": [row["source"]], "sourceFixtureIds": {row["source"]: row.get("sourceFixtureId")}}
        else:
            z = out[k]
            if row["source"] not in z["fixtureSources"]:
                z["fixtureSources"].append(row["source"])
            z["sourceFixtureIds"][row["source"]] = row.get("sourceFixtureId")
            if (not z.get("competition") or z.get("competition") == "Unknown competition") and row.get("competition"):
                z["competition"] = row["competition"]
                z["competitionSlug"] = row.get("competitionSlug")
    return sorted(out.values(), key=lambda x: (x.get("kickoff") or "", x.get("competition") or "", x.get("home") or ""))


def hbt_index() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    h14 = read_json(HBT14, {})
    market = read_json(MARKET, {})
    pre = read_json(PREXI, {})
    idx: dict[str, dict[str, Any]] = {}
    for source_name, doc, field in (("HBT14", h14, "fixtures"), ("MARKET", market, "fixtures"), ("PREXI", pre, "fixtures")):
        for fid, row in (doc.get(field) or {}).items():
            k = fixture_key(row)
            z = idx.setdefault(k, {"ids": {}, "rows": {}})
            z["ids"][source_name] = fid
            z["rows"][source_name] = row
    health = {
        "hbt14GeneratedAt": h14.get("generatedAt"),
        "marketGeneratedAt": market.get("generatedAt"),
        "preXiGeneratedAt": pre.get("generatedAt"),
        "indexedFixtures": len(idx),
    }
    return idx, health


def league_from_hbt(hit: dict[str, Any] | None) -> str | None:
    if not hit:
        return None
    for name in ("HBT14", "MARKET", "PREXI"):
        row = (hit.get("rows") or {}).get(name) or {}
        if row.get("league"):
            return str(row.get("league"))
    return None


def full_model_slug(slug: str) -> bool:
    s = key(slug).replace(" ", "-")
    return any(any(x in s or s in x for x in aliases) for aliases in FULL_MODEL_LEAGUES.values() if s)


def completeness(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {"known": False, "score": 0.0, "familiesPresent": []}
    families = []
    for f in ("availabilityContinuity", "tactical", "playerTeamImpact", "shotStoppingGoalkeeper", "setPieces", "referee", "weatherVenue", "workload", "travel", "competitionState", "manager", "formation", "substitutionBehaviour"):
        v = row.get(f)
        if v not in (None, {}, [], ""):
            families.append(f)
    return {"known": True, "score": round(len(families) / 13, 4), "familiesPresent": families}


def classify(public: dict[str, Any], hit: dict[str, Any] | None) -> dict[str, Any]:
    h14 = ((hit or {}).get("rows") or {}).get("HBT14") or {}
    market = ((hit or {}).get("rows") or {}).get("MARKET") or {}
    pre = ((hit or {}).get("rows") or {}).get("PREXI") or {}
    league = league_from_hbt(hit)
    known_full_comp = league in FULL_MODEL_LEAGUES if league else full_model_slug(str(public.get("competitionSlug") or public.get("competition") or ""))

    if hit and h14:
        status = "FULL_MODEL"
        reason = "Discovered fixture reconciled to HBT-1.4 live intelligence."
    elif hit and (market or pre):
        status = "NOT_YET_READY"
        reason = "Fixture exists upstream in HBT context/market feed but HBT-1.4 match intelligence is not ready yet."
    elif known_full_comp:
        status = "INSUFFICIENT_DATA"
        reason = "Competition is in the current full-model support contract, but the discovered fixture did not reconcile to HBT live data."
    else:
        status = "UNSUPPORTED_COMPETITION"
        reason = "Fixture was discovered, but this repository has no validated full-model or explicit fallback feed for this competition."

    ev = h14.get("eventMarkets") or market.get("eventMarkets") or {}
    validated = h14.get("validatedEventFamilies") or market.get("validatedEventFamilies") or []
    xi = h14.get("readinessState") or (pre.get("intelligenceReadiness") if pre else None)
    probs = h14.get("probabilities") or market.get("probabilities") or pre.get("probabilities") or None
    return {
        **public,
        "hbtSupportLevel": status,
        "predictionMode": ("HBT-1.4 LIVE INTELLIGENCE / frozen HBT-1.1.2 control" if status == "FULL_MODEL" else "NONE"),
        "probabilityOutput": probs,
        "intelligenceCompleteness": completeness(h14 if h14 else None),
        "xiState": xi,
        "scoreMarketsExist": bool(ev),
        "validatedEventMarketsExist": bool(validated),
        "validatedEventFamilies": validated,
        "hbtLeague": league,
        "hbtFixtureIds": (hit or {}).get("ids") or {},
        "exclusionReason": None if status == "FULL_MODEL" else reason,
        "classificationReason": reason,
        "rankEligible": status == "FULL_MODEL" and probs is not None,
    }


def source_failure_row(date: dt.date, audits: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "fixtureSources": [], "sourceFixtureIds": {}, "sourceFreshness": now(),
        "competition": None, "competitionSlug": None, "kickoff": None, "home": None, "away": None,
        "hbtSupportLevel": "SOURCE_FAILURE", "predictionMode": "NONE", "probabilityOutput": None,
        "intelligenceCompleteness": {"known": False, "score": 0.0, "familiesPresent": []},
        "xiState": None, "scoreMarketsExist": False, "validatedEventMarketsExist": False,
        "validatedEventFamilies": [], "hbtLeague": None, "hbtFixtureIds": {},
        "exclusionReason": f"All public slate discovery sources failed for {date.isoformat()}.",
        "classificationReason": "No public fixture source was available; empty slate must not be interpreted as no matches.",
        "rankEligible": False, "sourceAudit": audits,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="Target slate date YYYY-MM-DD; defaults to UTC today")
    args = ap.parse_args()
    target = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(dt.timezone.utc).date()

    discovered: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    for name, fn in (("ESPN_ALL", parse_espn), ("SOFASCORE", parse_sofascore)):
        try:
            rows, audit = fn(target)
            discovered.extend(rows)
            audits.append(audit)
        except Exception as exc:
            audits.append({"source": name, "fetchedAt": now(), "status": "failed", "events": 0, "error": str(exc)[:240]})

    merged = merge_sources([x for x in discovered if x["source"] == "ESPN_ALL"], [x for x in discovered if x["source"] == "SOFASCORE"])
    idx, feed_health = hbt_index()
    fixtures = [classify(row, idx.get(fixture_key(row))) for row in merged]
    if not fixtures and not any(a.get("status") == "loaded" for a in audits):
        fixtures = [source_failure_row(target, audits)]

    counts = {s: 0 for s in sorted(STATUS)}
    for row in fixtures:
        counts[row["hbtSupportLevel"]] += 1
    unsupported_competitions = sorted({str(x.get("competition")) for x in fixtures if x.get("hbtSupportLevel") == "UNSUPPORTED_COMPETITION" and x.get("competition")})

    payload = {
        "schemaVersion": "HBT-SLATE-1",
        "version": VERSION,
        "generatedAt": now(),
        "targetDate": target.isoformat(),
        "policy": {
            "discoveryBeforeRanking": True,
            "bookmakerOddsUsed": False,
            "frozenPredictiveModelMutated": False,
            "fallbackFabricated": False,
            "rankingAllowedOnlyAfterDiscovery": True,
            "testAImmutable": True,
        },
        "sourceAudit": audits,
        "hbtFeedHealth": feed_health,
        "coverage": {
            "fixturesDiscovered": len(merged),
            "classifiedRows": len(fixtures),
            **{k: counts[k] for k in counts},
            "unsupportedCompetitions": unsupported_competitions,
        },
        "rankingGate": {
            "discoveryComplete": bool(merged) and any(a.get("status") == "loaded" for a in audits),
            "rankEligibleFixtures": sum(bool(x.get("rankEligible")) for x in fixtures),
            "note": "A complete slate may contain zero rank-eligible fixtures if probability output is not present in this repository feed.",
        },
        "fixtures": fixtures,
    }
    write_json(OUTPUT, payload)
    print("HBT slate scanner", target, payload["coverage"], payload["rankingGate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
