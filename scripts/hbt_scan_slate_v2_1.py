#!/usr/bin/env python3
"""Source-hardening wrapper for HBT Slate Scanner 2.

Adds the league-specific fixture sources already used by the frozen HBT Forecast
Desk when generic cross-league discovery omits supported/fallback fixtures.
No prediction is created here; this only expands fixture discovery.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import hbt_scan_slate_v2 as base

base.VERSION = "HBT-SLATE-SCANNER-2.1"
_ORIG_ESPN = base.parse_espn

ESPN_LEAGUES = {
    "en.2": ("eng.2", "Championship"),
    "es.2": ("esp.2", "Segunda División"),
    "it.2": ("ita.2", "Serie B"),
    "be.1": ("bel.1", "Belgian Pro League"),
    "ie.1": ("irl.1", "League of Ireland Premier Division"),
    "sco.1": ("sco.1", "Scottish Premiership"),
    "tr.1": ("tur.1", "Süper Lig"),
    "uefa.cl": ("uefa.champions", "UEFA Champions League"),
    "nl.1": ("ned.1", "Eredivisie"),
    "pt.1": ("por.1", "Primeira Liga"),
}
SPORTSDB_LEAGUES = {
    "pl.1": (4422, "Ekstraklasa"),
    "ie.1": (4643, "League of Ireland Premier Division"),
}


def espn_league(date: dt.date, code: str, slug: str, label: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ds = date.strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={ds}&limit=1000"
    fetched = base.now(); raw = base.http_json(url); rows = []
    for e in raw.get("events") or []:
        comps = e.get("competitions") or []; c = comps[0] if comps else {}; teams = c.get("competitors") or []
        home = next((x for x in teams if x.get("homeAway") == "home"), teams[0] if teams else {})
        away = next((x for x in teams if x.get("homeAway") == "away"), teams[1] if len(teams) > 1 else {})
        hn = str((home.get("team") or {}).get("displayName") or (home.get("team") or {}).get("name") or "").strip()
        an = str((away.get("team") or {}).get("displayName") or (away.get("team") or {}).get("name") or "").strip()
        if not hn or not an: continue
        rows.append({
            "source": f"ESPN:{code}", "sourceFixtureId": str(e.get("id") or ""), "sourceFreshness": fetched,
            "competition": label, "competitionSlug": code, "leagueHint": code,
            "kickoff": base.iso_kickoff(e.get("date")), "home": hn, "away": an,
        })
    return rows, {"source": f"ESPN:{code}", "url": url, "fetchedAt": fetched, "status": "loaded", "events": len(rows)}


def sportsdb_league(date: dt.date, code: str, league_id: int, label: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ds = date.isoformat()
    url = f"https://www.thesportsdb.com/api/v1/json/123/eventsday.php?d={ds}&s=Soccer&l={league_id}"
    fetched = base.now(); raw = base.http_json(url); rows = []
    for e in raw.get("events") or []:
        if str(e.get("idLeague") or "") != str(league_id): continue
        hn, an = str(e.get("strHomeTeam") or "").strip(), str(e.get("strAwayTeam") or "").strip()
        if not hn or not an: continue
        stamp = e.get("strTimestamp")
        kickoff = base.iso_kickoff(stamp) if stamp else f"{e.get('dateEventLocal') or e.get('dateEvent') or ds}T{str(e.get('strTimeLocal') or e.get('strTime') or '00:00')[:5]}:00"
        rows.append({
            "source": f"THESPORTSDB:{code}", "sourceFixtureId": str(e.get("idEvent") or ""), "sourceFreshness": fetched,
            "competition": label, "competitionSlug": code, "leagueHint": code,
            "kickoff": kickoff, "home": hn, "away": an,
        })
    return rows, {"source": f"THESPORTSDB:{code}", "url": url, "fetchedAt": fetched, "status": "loaded", "events": len(rows)}


def parse_discovery_bundle(date: dt.date) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []; components: list[dict[str, Any]] = []; successes = 0
    providers: list[tuple[str, Any]] = [("ESPN_ALL", lambda: _ORIG_ESPN(date))]
    providers += [(f"ESPN:{c}", lambda c=c,s=s,l=l: espn_league(date,c,s,l)) for c,(s,l) in ESPN_LEAGUES.items()]
    providers += [(f"THESPORTSDB:{c}", lambda c=c,i=i,l=l: sportsdb_league(date,c,i,l)) for c,(i,l) in SPORTSDB_LEAGUES.items()]
    for name, fn in providers:
        try:
            got, audit = fn(); rows.extend(got); components.append(audit); successes += 1
        except Exception as exc:
            components.append({"source":name,"fetchedAt":base.now(),"status":"failed","events":0,"error":str(exc)[:240]})
    if not successes:
        raise RuntimeError("all ESPN/coverage discovery sources failed")
    return rows, {
        "source":"HBT_DISCOVERY_BUNDLE", "fetchedAt":base.now(), "status":"loaded",
        "events":len(rows), "successfulComponents":successes, "components":components,
    }


base.parse_espn = parse_discovery_bundle

if __name__ == "__main__":
    raise SystemExit(base.main())
