#!/usr/bin/env python3
"""HBT-1.4 international prospective/context hardening v2.

Consumes the research-only v1 international challenger and the same-day scanner.
It does not refit the football model. It:
- excludes already-started fixtures from prospective evidence;
- verifies home/neutral/displaced context from explicit ESPN neutral flags and
  venue-country identity, then recomputes only the already-selected home-context term;
- probes ESPN's generic summary endpoint for actual competition identity and
  official international rosters/XIs;
- keeps all outputs R0 research-only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.parse
from pathlib import Path
from typing import Any

import hbt_international_challenger_v1 as v1

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "hbt_live_data"
INTL = DATA / "international"
SCANNER = DATA / "slate_scanner.json"
VERSION = "HBT-1.4-INTERNATIONAL-CONTEXT-2.1-VENUE-IDENTITY"


def read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(d: dt.datetime) -> str:
    return d.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_dt(value: Any) -> dt.datetime | None:
    try:
        d = dt.datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return d.astimezone(dt.timezone.utc) if d.tzinfo else None
    except Exception:
        return None


def competitor_names(event: dict[str, Any]) -> tuple[str, str]:
    comps = event.get("competitions") or []
    c = comps[0] if comps else {}
    teams = c.get("competitors") or []
    home = next((x for x in teams if x.get("homeAway") == "home"), teams[0] if teams else {})
    away = next((x for x in teams if x.get("homeAway") == "away"), teams[1] if len(teams) > 1 else {})
    ht, at = home.get("team") or {}, away.get("team") or {}
    return str(ht.get("displayName") or ht.get("name") or "").strip(), str(at.get("displayName") or at.get("name") or "").strip()


def scoreboard_event_meta(target: dt.date) -> dict[str, dict[str, Any]]:
    url = v1.ESPN_ALL.format(date=target.strftime("%Y%m%d"))
    raw = json.loads(v1.http_bytes(url, 30).decode("utf-8", "replace"))
    out: dict[str, dict[str, Any]] = {}
    for event in raw.get("events") or []:
        eid = str(event.get("id") or "")
        if not eid:
            continue
        comps = event.get("competitions") or []
        c = comps[0] if comps else {}
        venue = c.get("venue") or {}
        addr = venue.get("address") or {}
        home, away = competitor_names(event)
        neutral_raw = c.get("neutralSite")
        neutral = neutral_raw if isinstance(neutral_raw, bool) else None
        status = ((event.get("status") or {}).get("type") or {})
        out[eid] = {
            "eventId": eid,
            "home": home,
            "away": away,
            "kickoff": event.get("date"),
            "neutralSite": neutral,
            "neutralSiteRawPresent": "neutralSite" in c,
            "venue": {
                "name": venue.get("fullName") or venue.get("name"),
                "city": addr.get("city"),
                "country": addr.get("country"),
            },
            "eventSeason": event.get("season"),
            "competitionLeague": c.get("league"),
            "competitionType": c.get("type"),
            "status": {"state": status.get("state"), "completed": status.get("completed")},
        }
    return out


def roster_row(row: dict[str, Any]) -> dict[str, Any]:
    ath = row.get("athlete") or row
    pos = row.get("position") or ath.get("position") or {}
    if isinstance(pos, dict):
        pos_name = pos.get("abbreviation") or pos.get("name") or pos.get("displayName")
    else:
        pos_name = str(pos or "")
    return {
        "id": str(ath.get("id") or row.get("id") or ""),
        "name": ath.get("displayName") or ath.get("fullName") or ath.get("shortName") or "",
        "position": pos_name,
        "starter": bool(row.get("starter") is True),
        "substitute": bool(row.get("substitute") is True or row.get("subbedIn") is True),
    }


def probe_summary(event_id: str) -> dict[str, Any]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/summary?event={urllib.parse.quote(event_id)}"
    try:
        raw = json.loads(v1.http_bytes(url, 20).decode("utf-8", "replace"))
    except Exception as exc:
        return {"available": False, "endpoint": "ESPN_ALL_SUMMARY", "error": str(exc)[:240]}
    rosters = []
    starter_counts = []
    for roster in raw.get("rosters") or []:
        team = roster.get("team") or {}
        players = [roster_row(x) for x in (roster.get("roster") or roster.get("athletes") or []) if isinstance(x, dict)]
        starters = sum(1 for x in players if x.get("starter"))
        starter_counts.append(starters)
        rosters.append({
            "teamId": str(team.get("id") or ""),
            "team": team.get("displayName") or team.get("name") or "",
            "starters": starters,
            "players": players,
        })
    header = raw.get("header") or {}
    league = header.get("league") or {}
    confirmed = len(rosters) >= 2 and all(x >= 10 for x in starter_counts[:2])
    return {
        "available": True,
        "endpoint": "ESPN_ALL_SUMMARY",
        "confirmedXI": confirmed,
        "rosterSides": len(rosters),
        "starterCounts": starter_counts,
        "leagueIdentity": {
            "id": league.get("id"), "name": league.get("name"), "slug": league.get("slug"),
            "abbreviation": league.get("abbreviation"),
        },
        "rosters": rosters,
    }


def key(home: Any, away: Any, kickoff: Any) -> tuple[str, str, str]:
    return (v1.norm(home), v1.norm(away), str(kickoff or "")[:16])


def country_key(value: Any) -> str:
    x = v1.norm(value)
    aliases = {
        "united states of america": "united states",
        "usa": "united states",
        "u s a": "united states",
        "uae": "united arab emirates",
        "russia": "russia",
        "republic of korea": "korea republic",
        "south korea": "korea republic",
        "democratic republic of congo": "dr congo",
        "d r congo": "dr congo",
        "cabo verde": "cape verde",
    }
    return aliases.get(x, x)


def venue_context(home: str, away: str, meta: dict[str, Any]) -> dict[str, Any]:
    neutral = meta.get("neutralSite") if meta else None
    venue = (meta.get("venue") or {}) if meta else {}
    country = str(venue.get("country") or "").strip()
    hk, ak, vk = country_key(home), country_key(away), country_key(country)

    # Explicit neutral is strongest evidence.
    if neutral is True:
        return {"status": "VERIFIED_NEUTRAL", "useHomeAdvantage": False, "verified": True,
                "evidence": "ESPN neutralSite=true", "venueCountry": country or None}

    # Venue-country identity is more informative than a missing generic neutral flag.
    if vk and hk and vk == hk:
        return {"status": "VERIFIED_HOME_COUNTRY", "useHomeAdvantage": True, "verified": True,
                "evidence": "venue country matches nominal home national team", "venueCountry": country}
    if vk and ak and vk == ak:
        return {"status": "VERIFIED_AWAY_COUNTRY_OR_DISPLACED_HOME", "useHomeAdvantage": False, "verified": True,
                "evidence": "venue country matches nominal away national team; nominal home boost removed", "venueCountry": country}

    # UK is deliberately unresolved when ESPN returns only the sovereign country;
    # England/Scotland/Wales/Northern Ireland cannot safely be inferred from it.
    if vk in {"united kingdom", "uk", "great britain"} and hk in {"england", "scotland", "wales", "northern ireland"}:
        return {"status": "VENUE_COUNTRY_AMBIGUOUS_UK_HOME_NATION", "useHomeAdvantage": True, "verified": False,
                "evidence": "venue country too coarse for constituent home nation", "venueCountry": country}

    if vk:
        return {"status": "VERIFIED_THIRD_COUNTRY_NEUTRAL_OR_DISPLACED", "useHomeAdvantage": False, "verified": True,
                "evidence": "venue country matches neither national team; nominal home boost removed", "venueCountry": country}

    if neutral is False:
        return {"status": "VERIFIED_HOME_AWAY_ESPN_FLAG", "useHomeAdvantage": True, "verified": True,
                "evidence": "ESPN neutralSite=false with no venue-country identity", "venueCountry": None}

    return {"status": "HOME_CONTEXT_UNVERIFIED", "useHomeAdvantage": True, "verified": False,
            "evidence": "no explicit neutral flag and no usable venue-country identity", "venueCountry": country or None}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--date", required=True); args = ap.parse_args()
    target = dt.date.fromisoformat(args.date)
    source_path = INTL / f"hbt_international_challenger_{target.isoformat()}.json"
    base = read(source_path, {})
    scanner = read(SCANNER, {})
    if base.get("targetDate") != target.isoformat() or scanner.get("targetDate") != target.isoformat():
        raise SystemExit("international v1 and scanner must both match target date")

    capture = utc_now()
    event_meta = scoreboard_event_meta(target)
    scanner_index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in scanner.get("fixtures") or []:
        scanner_index[key(row.get("home"), row.get("away"), row.get("kickoff"))] = row

    params_doc = base.get("validation", {}).get("selectedParams") or {}
    params = (
        float(params_doc.get("eloSlope") or 1.0), float(params_doc.get("homeLogit") or 0.0),
        float(params_doc.get("drawIntercept") or 0.0), float(params_doc.get("drawMismatchPenalty") or 0.0),
    )
    prospective = []; post = []; unresolved_timing = []
    xi_attempted = xi_available = xi_confirmed = 0

    for original in base.get("internationalCandidates") or []:
        row = json.loads(json.dumps(original))
        fx = row.get("fixture") or {}
        home, away = str(fx.get("home") or ""), str(fx.get("away") or "")
        ko = parse_dt(fx.get("kickoff"))
        srow = scanner_index.get(key(home, away, fx.get("kickoff"))) or {}
        eid = str(srow.get("sourceFixtureId") or ((srow.get("sourceFixtureIds") or {}).get("ESPN_ALL")) or "")
        meta = event_meta.get(eid, {}) if eid else {}
        neutral = meta.get("neutralSite") if meta else None
        lead_minutes = (ko - capture).total_seconds() / 60.0 if ko else None
        pre = bool(ko and ko > capture)

        state = row.get("state") or {}
        diff_with_home = state.get("eloDiffWithHomeAdvantage")
        vc = venue_context(home, away, meta)
        if isinstance(diff_with_home, (int, float)):
            base_diff = float(diff_with_home) - 65.0
            p_home = v1.probs({"eloDiff": base_diff + 65.0, "homeAdvantage": True}, params)
            p_neutral = v1.probs({"eloDiff": base_diff, "homeAdvantage": False}, params)
            p_final = p_home if vc["useHomeAdvantage"] else p_neutral
            row["probs"] = {"H": p_final[0], "D": p_final[1], "A": p_final[2]}
            row["pick"] = ("H", "D", "A")[max(range(3), key=lambda i: p_final[i])]
            row["pickProbability"] = max(p_final)
            row["derivedMarkets"] = v1.derived_markets(p_final)
            row["venueContext"] = {
                "status": vc["status"], "neutralSite": neutral, "venue": meta.get("venue"),
                "venueCountryEvidence": vc["evidence"],
                "homeAdvantageApplied": vc["useHomeAdvantage"],
                "homeContextProbability": {"H": p_home[0], "D": p_home[1], "A": p_home[2]},
                "noHomeAdvantageProbability": {"H": p_neutral[0], "D": p_neutral[1], "A": p_neutral[2]},
                "probabilityContextVerified": vc["verified"],
            }
        else:
            row["venueContext"] = {"status": "NO_STRUCTURAL_STATE", "neutralSite": neutral, "venue": meta.get("venue"), "probabilityContextVerified": False}

        row["sourceFixtureId"] = eid or None
        row["capture"] = {
            "capturedAt": iso(capture), "kickoffUtc": iso(ko) if ko else None,
            "leadMinutes": lead_minutes, "statusAtCapture": "PRE_KICKOFF" if pre else "POST_KICKOFF_OR_UNVERIFIED",
        }
        row["eventIdentity"] = meta

        if pre and eid:
            xi_attempted += 1
            xi = probe_summary(eid)
            row["officialXI"] = xi
            row["resolvedCompetition"] = xi.get("leagueIdentity") if xi.get("available") else None
            xi_available += int(bool(xi.get("available")))
            xi_confirmed += int(bool(xi.get("confirmedXI")))
        else:
            row["officialXI"] = {"available": False, "reason": "not probed after kickoff or event id unavailable"}
            row["resolvedCompetition"] = None

        # Summary/league identity is authoritative for namespace exclusions.
        # Generic discovery labels such as "playoff-phase---first-round" may hide
        # women's or youth competitions until the event summary is resolved.
        resolved = row.get("resolvedCompetition") or {}
        resolved_text = " ".join(str(resolved.get(k) or "") for k in ("name","slug","abbreviation"))
        resolved_namespace_block = None
        if v1.WOMEN_RE.search(resolved_text):
            resolved_namespace_block = "RESOLVED_WOMENS_COMPETITION"
        elif v1.YOUTH_RE.search(resolved_text):
            resolved_namespace_block = "RESOLVED_YOUTH_COMPETITION"
        row["resolvedNamespaceBlock"] = resolved_namespace_block

        row["cleanProspectiveEligible"] = bool(
            pre and row.get("probs")
            and (row.get("venueContext") or {}).get("probabilityContextVerified") is True
            and resolved_namespace_block is None
        )
        row["execution"] = {
            "class": "R0_SHADOW_RESEARCH", "fundingAllowed": False,
            "reason": (
                resolved_namespace_block
                or "international challenger remains unpromoted; bookmaker odds are not consumed here"
            ),
        }
        if not ko:
            unresolved_timing.append(row)
        elif pre:
            prospective.append(row)
        else:
            post.append(row)

    out = {
        "schemaVersion": "HBT-INTERNATIONAL-PROSPECTIVE-2", "version": VERSION,
        "generatedAt": iso(capture), "targetDate": target.isoformat(), "source": source_path.name,
        "policy": {
            "researchOnly": True, "frozenHBT112Mutated": False, "domesticForecastsMutated": False,
            "bookmakerOddsRead": False, "postKickoffRowsExcludedFromProspectiveEvidence": True,
            "venueContextMustBeVerifiedForCleanProspectiveEvidence": True,
            "thirdCountryVenueRemovesNominalHomeAdvantage": True,
            "officialXIIsContextOnlyUntilValidated": True, "automaticPromotion": False, "automaticFunding": False,
        },
        "validation": base.get("validation"), "historySource": base.get("historySource"),
        "summary": {
            "v1InternationalRows": len(base.get("internationalCandidates") or []),
            "preKickoffProspective": len(prospective), "postKickoffExcluded": len(post),
            "timingUnresolved": len(unresolved_timing),
            "cleanProspectiveEligible": sum(1 for x in prospective if x.get("cleanProspectiveEligible")),
            "verifiedHomeCountry": sum(1 for x in prospective if (x.get("venueContext") or {}).get("status") == "VERIFIED_HOME_COUNTRY"),
            "verifiedThirdCountryOrAway": sum(1 for x in prospective if (x.get("venueContext") or {}).get("status") in {"VERIFIED_THIRD_COUNTRY_NEUTRAL_OR_DISPLACED", "VERIFIED_AWAY_COUNTRY_OR_DISPLACED_HOME"}),
            "venueContextUnresolved": sum(1 for x in prospective if not (x.get("venueContext") or {}).get("probabilityContextVerified")),
            "xiProbeAttempted": xi_attempted, "xiSummaryAvailable": xi_available, "confirmedXI": xi_confirmed,
        },
        "prospectiveCandidates": prospective,
        "postKickoffResearchRows": post,
        "timingUnresolvedRows": unresolved_timing,
    }
    write(INTL / f"hbt_international_prospective_{target.isoformat()}.json", out)
    print(json.dumps({"targetDate": target.isoformat(), "summary": out["summary"], "prospective": [
        {"fixture": x.get("fixture"), "domain": x.get("domain"), "competition": x.get("resolvedCompetition"),
         "pick": x.get("pick"), "p": x.get("pickProbability"), "venue": x.get("venueContext"),
         "xi": {k:(x.get("officialXI") or {}).get(k) for k in ("available","confirmedXI","starterCounts","leagueIdentity")},
         "clean": x.get("cleanProspectiveEligible")} for x in prospective
    ]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
