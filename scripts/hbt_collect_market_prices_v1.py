#!/usr/bin/env python3
"""Collect bookmaker prices as a downstream sidecar for HBT.

Critical separation contract:
- bookmaker prices NEVER enter HBT football probabilities, simulation, tiers or feature state;
- a missing/poor price NEVER changes the football forecast or R1 experiment eligibility;
- prices exist only for display, fair-price comparison, CLV/value analysis and audit.

Primary provider: Odds-API.io, configured with ODDS_API_IO_KEY. Betway is the
primary bookmaker because that is the execution venue for the live experiments.
If no key is configured the script writes an explicit PRICE_SOURCE_UNCONFIGURED
sidecar instead of silently inventing or reusing stale prices.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hbt_live_data"
SLATE = OUT / "slate_scanner.json"
OUTPUT = OUT / "market_prices.json"
VERSION = "HBT-MARKET-PRICES-1"
BASE = "https://api.odds-api.io/v3"
BOOKMAKER = os.getenv("HBT_PRIMARY_BOOKMAKER", "Betway").strip() or "Betway"
API_KEY = os.getenv("ODDS_API_IO_KEY", "").strip()


def read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write(path: Path, obj: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def nkey(value: Any) -> str:
    s = unicodedata.normalize("NFKD", str(value or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r"\b(fc|cf|afc|sc|club|deportivo|ud|cd|rc|ac|as)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def similarity(a: Any, b: Any) -> float:
    x, y = nkey(a), nkey(b)
    if not x or not y:
        return 0.0
    if x == y:
        return 1.0
    sx, sy = set(x.split()), set(y.split())
    jac = len(sx & sy) / max(1, len(sx | sy))
    seq = SequenceMatcher(None, x, y).ratio()
    return max(jac, seq)


def parse_dt(value: Any) -> datetime | None:
    try:
        s = str(value or "").strip().replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return None


def http_json(path: str, params: dict[str, Any]) -> Any:
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{BASE}{path}?{q}",
        headers={"User-Agent": "HBT-Market-Prices/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8-sig", "replace"))


def fixture_match_score(slate_row: dict[str, Any], event: dict[str, Any]) -> tuple[float, float | None]:
    hs = similarity(slate_row.get("home"), event.get("home"))
    aw = similarity(slate_row.get("away"), event.get("away"))
    team_score = (hs + aw) / 2.0
    a, b = parse_dt(slate_row.get("kickoff")), parse_dt(event.get("date"))
    diff_h: float | None = None
    if a and b:
        diff_h = abs((a - b).total_seconds()) / 3600.0
        if diff_h > 12.0:
            return 0.0, diff_h
        time_factor = max(0.0, 1.0 - diff_h / 12.0)
        team_score = 0.9 * team_score + 0.1 * time_factor
    return team_score, diff_h


def best_matches(slate_rows: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    used: set[str] = set()
    for row in slate_rows:
        best: tuple[float, dict[str, Any] | None, float | None] = (0.0, None, None)
        for ev in events:
            eid = str(ev.get("id") or "")
            if not eid or eid in used:
                continue
            score, diff_h = fixture_match_score(row, ev)
            if score > best[0]:
                best = (score, ev, diff_h)
        if best[1] is not None and best[0] >= 0.78:
            ev = best[1]
            eid = str(ev.get("id"))
            used.add(eid)
            key = str(row.get("sourceFixtureId") or row.get("sourceFixtureIds") or f"{row.get('home')}|{row.get('away')}|{row.get('kickoff')}")
            out[key] = {
                "slateFixture": {"home": row.get("home"), "away": row.get("away"), "kickoff": row.get("kickoff"), "competition": row.get("competition")},
                "providerEvent": {"id": ev.get("id"), "home": ev.get("home"), "away": ev.get("away"), "date": ev.get("date"), "league": ev.get("league"), "status": ev.get("status")},
                "identityMatchScore": round(best[0], 6),
                "kickoffDifferenceHours": best[2],
            }
    return out


def main() -> int:
    slate = read(SLATE, {})
    target = str(slate.get("targetDate") or date.today().isoformat())
    rows = list(slate.get("fixtures") or [])
    base_payload: dict[str, Any] = {
        "schemaVersion": "HBT-MARKET-PRICES-1",
        "version": VERSION,
        "generatedAt": now_iso(),
        "targetDate": target,
        "primaryBookmaker": BOOKMAKER,
        "provider": "Odds-API.io",
        "policy": {
            "bookmakerOddsUsedAsFootballModelFeature": False,
            "bookmakerOddsUsedInSimulation": False,
            "bookmakerOddsMayChangeFootballForecast": False,
            "bookmakerOddsMayChangeR1ExperimentEligibility": False,
            "priceAssessmentOnly": True,
            "missingPriceIsNotZero": True,
            "stalePriceIsNotCurrentPrice": True,
            "testAImmutable": True,
        },
        "status": None,
        "fixturesDiscovered": len(rows),
        "providerEvents": 0,
        "fixturesMatched": 0,
        "fixtures": {},
    }

    if not API_KEY:
        base_payload["status"] = "PRICE_SOURCE_UNCONFIGURED"
        base_payload["reason"] = "ODDS_API_IO_KEY is not configured. Football forecasts remain valid; price assessment is unavailable."
        write(OUTPUT, base_payload)
        print("HBT market prices: provider unconfigured")
        return 0

    try:
        d = date.fromisoformat(target)
        start = datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc) - timedelta(hours=3)
        end = start + timedelta(days=1, hours=6)
        events = http_json("/events", {
            "apiKey": API_KEY,
            "sport": "football",
            "bookmaker": BOOKMAKER,
            "status": "pending,live",
            "from": start.isoformat().replace("+00:00", "Z"),
            "to": end.isoformat().replace("+00:00", "Z"),
        })
        if not isinstance(events, list):
            raise RuntimeError(f"unexpected events response type: {type(events).__name__}")
        base_payload["providerEvents"] = len(events)
        matches = best_matches(rows, events)
        ids = [str(v["providerEvent"]["id"]) for v in matches.values()]
        odds_by_id: dict[str, dict[str, Any]] = {}
        for i in range(0, len(ids), 10):
            chunk = ids[i:i+10]
            if not chunk:
                continue
            data = http_json("/odds/multi", {"apiKey": API_KEY, "eventIds": ",".join(chunk), "bookmakers": BOOKMAKER})
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("id") is not None:
                        odds_by_id[str(item.get("id"))] = item
            elif isinstance(data, dict) and data.get("id") is not None:
                odds_by_id[str(data.get("id"))] = data

        for k, m in matches.items():
            eid = str(m["providerEvent"]["id"])
            snap = odds_by_id.get(eid) or {}
            book = (snap.get("bookmakers") or {}).get(BOOKMAKER)
            m["bookmaker"] = BOOKMAKER
            m["priceStatus"] = "CURRENT_PRICE_AVAILABLE" if isinstance(book, list) and book else "PRICE_UNAVAILABLE"
            m["markets"] = book if isinstance(book, list) else []
            m["providerUrls"] = snap.get("urls") or {}
            base_payload["fixtures"][k] = m

        base_payload["fixturesMatched"] = len(matches)
        priced = sum(1 for x in base_payload["fixtures"].values() if x.get("priceStatus") == "CURRENT_PRICE_AVAILABLE")
        base_payload["pricedFixtures"] = priced
        base_payload["status"] = "PRICES_AVAILABLE" if priced else "PRICE_UNAVAILABLE"
        if not priced:
            base_payload["reason"] = "Provider was reachable but returned no current Betway markets for matched HBT fixtures."
    except Exception as exc:
        base_payload["status"] = "PRICE_SOURCE_FAILURE"
        base_payload["reason"] = f"{type(exc).__name__}: {exc}"

    write(OUTPUT, base_payload)
    print("HBT market prices", {"status": base_payload["status"], "events": base_payload["providerEvents"], "matched": base_payload["fixturesMatched"], "priced": base_payload.get("pricedFixtures", 0)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
