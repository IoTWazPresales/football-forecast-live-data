#!/usr/bin/env python3
"""HBT-1.4 international/domain challenger v1.

Research-only extension of HBT. It does NOT alter the frozen HBT-1.1.2 runtime,
domestic probabilities, tiers, or betting records, and it never reads bookmaker
odds. It reclassifies generic discovered fixtures into explicit football domains
and builds a causal senior-men's international structural/recent-performance
challenger from historical full internationals.

The international probability model remains R0/shadow until its chronological
backtest gates pass AND clean prospective confirmation is accumulated.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
import re
import unicodedata
import urllib.request
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "hbt_live_data"
INTL = DATA / "international"
SCANNER = DATA / "slate_scanner.json"
VERSION = "HBT-1.4-INTERNATIONAL-CHALLENGER-1"
SCHEMA = "HBT-INTERNATIONAL-CHALLENGER-1"
SOURCE_COMMIT = "394fe81893b062fbc2cf6257e988ac7cc4c039a1"
HISTORY_URL = f"https://raw.githubusercontent.com/martj42/international_results/{SOURCE_COMMIT}/results.csv"
ESPN_ALL = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={date}&limit=1000"
UA = "Mozilla/5.0 (compatible; HBT-1.4-International/1.0)"

YOUTH_RE = re.compile(r"\bu(?:17|18|19|20|21|22|23)\b|under[- ]?(?:17|18|19|20|21|22|23)|youth|olympic", re.I)
WOMEN_RE = re.compile(r"women|women's|womens|femen|feminin|vrouwen", re.I)
FRIENDLY_RE = re.compile(r"friendly", re.I)
CUP_RE = re.compile(r"cup|trophy|shield|qualif|round|knockout|play[- ]?off", re.I)

ALIASES = {
    "czechia": "czech republic",
    "ivory coast": "cote d ivoire",
    "cote divoire": "cote d ivoire",
    "cote d ivoire": "cote d ivoire",
    "cape verde islands": "cape verde",
    "usa": "united states",
    "us": "united states",
    "south korea": "korea republic",
    "korea south": "korea republic",
    "north korea": "korea dpr",
    "korea north": "korea dpr",
    "congo dr": "dr congo",
    "congo democratic republic": "dr congo",
    "ireland republic": "republic of ireland",
    "turkiye": "turkey",
    "swaziland": "eswatini",
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def norm(v: Any) -> str:
    x = unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode().lower()
    x = x.replace("&", " and ")
    x = " ".join(re.sub(r"[^a-z0-9]+", " ", x).split())
    return ALIASES.get(x, x)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def http_bytes(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/csv,application/json,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load_history() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw = http_bytes(HISTORY_URL, 45)
    rows: list[dict[str, Any]] = []
    for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig", "replace"))):
        try:
            day = dt.date.fromisoformat(str(r.get("date") or "")[:10])
            hg = int(float(r.get("home_score") or ""))
            ag = int(float(r.get("away_score") or ""))
        except Exception:
            continue
        home = str(r.get("home_team") or "").strip()
        away = str(r.get("away_team") or "").strip()
        if not home or not away:
            continue
        rows.append({
            "date": day, "home": home, "away": away, "hg": hg, "ag": ag,
            "tournament": str(r.get("tournament") or "").strip(),
            "neutral": str(r.get("neutral") or "").strip().lower() == "true",
            "source": "martj42-pinned",
        })
    rows.sort(key=lambda x: x["date"])
    return rows, {
        "url": HISTORY_URL, "commit": SOURCE_COMMIT, "sha256": hashlib.sha256(raw).hexdigest(),
        "rows": len(rows), "firstDate": rows[0]["date"].isoformat() if rows else None,
        "lastDate": rows[-1]["date"].isoformat() if rows else None,
    }


def parse_espn_day(day: dt.date) -> list[dict[str, Any]]:
    raw = json.loads(http_bytes(ESPN_ALL.format(date=day.strftime("%Y%m%d")), 25).decode("utf-8", "replace"))
    out = []
    for event in raw.get("events") or []:
        comps = event.get("competitions") or []
        comp = comps[0] if comps else {}
        if not (((event.get("status") or {}).get("type") or {}).get("completed")):
            continue
        teams = comp.get("competitors") or []
        home = next((x for x in teams if x.get("homeAway") == "home"), None)
        away = next((x for x in teams if x.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        hn = str((home.get("team") or {}).get("displayName") or (home.get("team") or {}).get("name") or "").strip()
        an = str((away.get("team") or {}).get("displayName") or (away.get("team") or {}).get("name") or "").strip()
        try:
            hg = int(float(home.get("score"))); ag = int(float(away.get("score")))
        except Exception:
            continue
        league = comp.get("league") or {}; season = event.get("season") or {}
        label = str(league.get("name") or league.get("abbreviation") or season.get("slug") or "").strip()
        out.append({"date": day, "home": hn, "away": an, "hg": hg, "ag": ag, "tournament": label, "neutral": False, "source": "ESPN-supplement"})
    return out


def supplement_recent(history: list[dict[str, Any]], target: dt.date, countries: set[str], max_days: int = 45) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not history:
        return history, {"attemptedDays": 0, "loadedDays": 0, "failedDays": 0, "addedMatches": 0}
    start = max(history[-1]["date"] + dt.timedelta(days=1), target - dt.timedelta(days=max_days))
    end = target - dt.timedelta(days=1)
    existing = {(r["date"], norm(r["home"]), norm(r["away"])) for r in history}
    added = []; attempted = loaded = failed = 0
    day = start
    while day <= end:
        attempted += 1
        try:
            rows = parse_espn_day(day); loaded += 1
        except Exception:
            failed += 1; day += dt.timedelta(days=1); continue
        for r in rows:
            text = f"{r['home']} {r['away']} {r['tournament']}"
            if WOMEN_RE.search(text) or YOUTH_RE.search(text):
                continue
            if norm(r["home"]) not in countries or norm(r["away"]) not in countries:
                continue
            key = (r["date"], norm(r["home"]), norm(r["away"]))
            if key not in existing:
                existing.add(key); added.append(r)
        day += dt.timedelta(days=1)
    return sorted(history + added, key=lambda x: x["date"]), {
        "attemptedDays": attempted, "loadedDays": loaded, "failedDays": failed, "addedMatches": len(added),
        "from": start.isoformat() if start <= end else None, "through": end.isoformat() if start <= end else None,
    }


def domain(row: dict[str, Any], countries: set[str]) -> dict[str, Any]:
    home, away = str(row.get("home") or ""), str(row.get("away") or "")
    comp = " ".join(str(row.get(k) or "") for k in ("competition", "competitionSlug", "leagueHint"))
    text = f"{home} {away} {comp}"
    if WOMEN_RE.search(text):
        return {"domain": "NATIONAL_WOMEN" if norm(home) in countries or norm(away) in countries else "CLUB_WOMEN", "seniorMens": False, "reason": "women namespace"}
    if YOUTH_RE.search(text):
        return {"domain": "NATIONAL_YOUTH" if norm(home) in countries or norm(away) in countries else "CLUB_YOUTH", "seniorMens": False, "reason": "youth namespace"}
    both_country = norm(home) in countries and norm(away) in countries
    if both_country:
        if FRIENDLY_RE.search(comp):
            return {"domain": "NATIONAL_FRIENDLY", "seniorMens": True, "reason": "both teams resolve to senior national-team history and competition is friendly"}
        return {"domain": "NATIONAL_COMPETITIVE", "seniorMens": True, "reason": "both teams resolve to senior national-team history"}
    if FRIENDLY_RE.search(comp):
        return {"domain": "CLUB_FRIENDLY", "seniorMens": False, "reason": "club/non-national friendly"}
    if CUP_RE.search(comp):
        return {"domain": "CLUB_CUP", "seniorMens": False, "reason": "club/non-national cup or knockout context"}
    return {"domain": "CLUB_LEAGUE_OR_UNRESOLVED", "seniorMens": False, "reason": "not both senior national teams"}


def tournament_weight(name: str) -> float:
    s = norm(name)
    if "fifa world cup" in s and "qualification" not in s and "qualifying" not in s:
        return 45.0
    if any(x in s for x in ("uefa euro", "copa america", "africa cup of nations", "afc asian cup", "concacaf gold cup", "ofc nations cup")) and not any(x in s for x in ("qualif", "preliminary")):
        return 40.0
    if any(x in s for x in ("qualification", "qualifying", "preliminary")):
        return 30.0
    if "nations league" in s or any(x in s for x in ("cosafa", "cecafa", "gulf cup")):
        return 25.0
    if "friendly" in s:
        return 12.0
    return 20.0


def result_code(hg: int, ag: int) -> str:
    return "H" if hg > ag else "A" if hg < ag else "D"


def softmax(values: list[float]) -> list[float]:
    m = max(values); ex = [math.exp(v - m) for v in values]; total = sum(ex)
    return [v / total for v in ex]


def probs(feature: dict[str, Any], params: tuple[float, float, float, float]) -> list[float]:
    slope, home_logit, draw_intercept, draw_mismatch = params
    d = float(feature["eloDiff"]) / 400.0
    home = 1.0 if feature.get("homeAdvantage") else 0.0
    return softmax([slope * d + home_logit * home, draw_intercept - draw_mismatch * abs(d), -slope * d])


def metrics(rows: list[dict[str, Any]], params: tuple[float, float, float, float] | None = None, base: list[float] | None = None) -> dict[str, Any]:
    n = correct = 0; logloss = brier = 0.0; bins = defaultdict(lambda: [0, 0.0, 0.0])
    for row in rows:
        p = probs(row, params) if params else list(base or [1/3, 1/3, 1/3])
        y = {"H": 0, "D": 1, "A": 2}[row["result"]]
        n += 1; correct += int(max(range(3), key=lambda i: p[i]) == y)
        logloss += -math.log(max(p[y], 1e-15))
        one = [0.0, 0.0, 0.0]; one[y] = 1.0
        brier += sum((p[i] - one[i]) ** 2 for i in range(3))
        top = max(p); hit = 1.0 if max(range(3), key=lambda i: p[i]) == y else 0.0
        z = bins[min(9, int(top * 10))]; z[0] += 1; z[1] += top; z[2] += hit
    if not n:
        return {"n": 0, "logLoss": None, "brier": None, "accuracy": None, "topPickECE": None}
    ece = sum((bn / n) * abs(conf / bn - hit / bn) for bn, conf, hit in bins.values())
    return {"n": n, "logLoss": logloss / n, "brier": brier / n, "accuracy": correct / n, "topPickECE": ece}


def build_features(history: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, float], dict[str, deque], dict[str, dt.date]]:
    ratings: dict[str, float] = defaultdict(lambda: 1500.0)
    recent: dict[str, deque] = defaultdict(lambda: deque(maxlen=8))
    last_seen: dict[str, dt.date] = {}
    features = []
    for row in history:
        hk, ak = norm(row["home"]), norm(row["away"])
        if not hk or not ak or hk == ak:
            continue
        rh, ra = ratings[hk], ratings[ak]
        home_adv = not bool(row.get("neutral"))
        diff = rh - ra + (65.0 if home_adv else 0.0)
        features.append({
            "date": row["date"], "home": row["home"], "away": row["away"],
            "result": result_code(row["hg"], row["ag"]), "eloDiff": diff,
            "homeAdvantage": home_adv, "tournament": row.get("tournament"), "source": row.get("source"),
        })
        expected = 1.0 / (1.0 + 10 ** (-diff / 400.0))
        actual = 1.0 if row["hg"] > row["ag"] else 0.0 if row["hg"] < row["ag"] else 0.5
        margin = abs(int(row["hg"]) - int(row["ag"]))
        mult = math.sqrt((margin + 1.0) / 2.0) if margin > 1 else 1.0
        delta = tournament_weight(str(row.get("tournament") or "")) * mult * (actual - expected)
        ratings[hk] = rh + delta; ratings[ak] = ra - delta
        recent[hk].append({"date": row["date"], "gf": row["hg"], "ga": row["ag"], "oppRating": ra, "result": actual})
        recent[ak].append({"date": row["date"], "gf": row["ag"], "ga": row["hg"], "oppRating": rh, "result": 1.0 - actual})
        last_seen[hk] = row["date"]; last_seen[ak] = row["date"]
    return features, ratings, recent, last_seen


def select_params(rows: list[dict[str, Any]]) -> tuple[tuple[float, float, float, float], dict[str, Any]]:
    best = None; best_metrics = None
    for slope in (0.8, 1.0, 1.2, 1.4, 1.6):
        for home in (0.0, 0.15, 0.30, 0.45):
            for draw in (0.0, 0.2, 0.4, 0.6, 0.8):
                for mismatch in (0.0, 0.2, 0.4, 0.6):
                    p = (slope, home, draw, mismatch); m = metrics(rows, p)
                    if m["n"] and (best_metrics is None or m["logLoss"] < best_metrics["logLoss"]):
                        best, best_metrics = p, m
    return best or (1.0, 0.2, 0.4, 0.2), best_metrics or metrics([])


def recent_profile(team: str, recent: dict[str, deque], ratings: dict[str, float], last_seen: dict[str, dt.date], target: dt.date) -> dict[str, Any]:
    key = norm(team); rows = list(recent.get(key) or [])
    if rows:
        gf = sum(x["gf"] for x in rows) / len(rows); ga = sum(x["ga"] for x in rows) / len(rows)
        pts = sum(3 if x["result"] == 1 else 1 if x["result"] == .5 else 0 for x in rows) / (3 * len(rows))
        opp = sum(x["oppRating"] for x in rows) / len(rows)
    else:
        gf = ga = pts = opp = None
    last = last_seen.get(key)
    return {"elo": ratings.get(key, 1500.0), "recentN": len(rows), "goalsForMean": gf, "goalsAgainstMean": ga,
            "pointsShare": pts, "recentOpponentEloMean": opp, "daysSinceMatch": (target - last).days if last else None}


def derived_markets(p: list[float]) -> dict[str, Any]:
    H, D, A = p
    def m(value: float) -> dict[str, float]:
        return {"p": value, "fairOdds": 1.0 / value if value > 0 else None}
    return {
        "1X": m(H + D), "X2": m(A + D), "12": m(H + A),
        "HOME_DNB": {"winP": H, "pushP": D, "lossP": A, "conditionalP": H/(H+A) if H+A else None, "fairOdds": (H+A)/H if H > 0 else None},
        "AWAY_DNB": {"winP": A, "pushP": D, "lossP": H, "conditionalP": A/(H+A) if H+A else None, "fairOdds": (H+A)/A if A > 0 else None},
    }


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--date", required=True); args = parser.parse_args()
    target = dt.date.fromisoformat(args.date)
    scanner = read_json(SCANNER, {})
    if scanner.get("targetDate") != target.isoformat():
        raise SystemExit(f"slate_scanner targetDate {scanner.get('targetDate')} != {target}")

    pinned, source_meta = load_history()
    countries = {norm(r["home"]) for r in pinned} | {norm(r["away"]) for r in pinned}
    history, supplement = supplement_recent(pinned, target, countries)
    history = [r for r in history if r["date"] < target]
    features, ratings, recent, last_seen = build_features(history)

    selection = [r for r in features if dt.date(2023,1,1) <= r["date"] <= dt.date(2024,12,31)]
    holdout = [r for r in features if dt.date(2025,1,1) <= r["date"] < target]
    earlier = [r for r in features if dt.date(2018,1,1) <= r["date"] < dt.date(2023,1,1)]
    counts = [sum(r["result"] == x for r in earlier) for x in ("H", "D", "A")]
    total = sum(counts) or 1; baseline = [x / total for x in counts]
    params, selection_metrics = select_params(selection)
    holdout_metrics = metrics(holdout, params); baseline_metrics = metrics(holdout, base=baseline)
    competitive = [r for r in holdout if not FRIENDLY_RE.search(str(r.get("tournament") or ""))]
    friendly = [r for r in holdout if FRIENDLY_RE.search(str(r.get("tournament") or ""))]
    competitive_metrics = metrics(competitive, params); friendly_metrics = metrics(friendly, params)
    improves = bool(holdout_metrics["n"] and holdout_metrics["logLoss"] < baseline_metrics["logLoss"] and holdout_metrics["brier"] < baseline_metrics["brier"])

    domain_rows = []; candidates = []
    for row in scanner.get("fixtures") or []:
        d = domain(row, countries)
        fixture = {"home": row.get("home"), "away": row.get("away"), "kickoff": row.get("kickoff"), "competition": row.get("competition"), "competitionSlug": row.get("competitionSlug")}
        domain_rows.append({"fixture": fixture, **d, "scannerSupportLevel": row.get("hbtSupportLevel")})
        if not d["seniorMens"]:
            continue
        hp = recent_profile(str(row.get("home") or ""), recent, ratings, last_seen, target)
        ap = recent_profile(str(row.get("away") or ""), recent, ratings, last_seen, target)
        known = norm(row.get("home")) in ratings and norm(row.get("away")) in ratings
        diff = hp["elo"] - ap["elo"] + 65.0
        p = probs({"eloDiff": diff, "homeAdvantage": True}, params) if known else None
        fail_rate = supplement["failedDays"] / supplement["attemptedDays"] if supplement.get("attemptedDays") else 0.0
        recent_ok = hp["recentN"] >= 4 and ap["recentN"] >= 4
        fresh_ok = hp["daysSinceMatch"] is not None and hp["daysSinceMatch"] <= 180 and ap["daysSinceMatch"] is not None and ap["daysSinceMatch"] <= 180
        quality = min(1.0, (0.45 if known else 0) + (0.25 if recent_ok else 0) + (0.15 if fresh_ok else 0) + (0.10 if fail_rate <= 0.15 else 0) + (0.05 if d["domain"] == "NATIONAL_COMPETITIVE" else 0))
        candidates.append({
            "fixture": fixture, "domain": d["domain"],
            "predictionMode": "INTERNATIONAL_STRUCTURAL_CHALLENGER_V1" if p else "INSUFFICIENT_INTERNATIONAL_STATE",
            "probs": {"H": p[0], "D": p[1], "A": p[2]} if p else None,
            "pick": ("H", "D", "A")[max(range(3), key=lambda i: p[i])] if p else None,
            "pickProbability": max(p) if p else None, "derivedMarkets": derived_markets(p) if p else {}, "quality": quality,
            "state": {"home": hp, "away": ap, "eloDiffWithHomeAdvantage": diff if known else None},
            "intelligenceCoverage": {
                "structuralInternationalState": known, "recentInternationalPerformance": recent_ok, "freshInternationalState": fresh_ok,
                "clubToCountryPlayerTransfer": False, "confirmedXI": False, "tacticalMatchup": False,
                "shotStoppingGoalkeeper": False, "setPieces": False, "referee": False, "weatherVenue": False,
                "motivationCompetition": d["domain"] == "NATIONAL_COMPETITIVE",
            },
            "execution": {"class": "R0_SHADOW_RESEARCH", "fundingAllowed": False, "reason": "international challenger requires clean prospective confirmation before promotion"},
        })

    validation = {
        "selectionWindow": ["2023-01-01", "2024-12-31"], "holdoutWindow": ["2025-01-01", target.isoformat()],
        "selectedParams": {"eloSlope": params[0], "homeLogit": params[1], "drawIntercept": params[2], "drawMismatchPenalty": params[3]},
        "selection": selection_metrics, "holdout": holdout_metrics, "holdoutBaseline": baseline_metrics,
        "competitiveHoldout": competitive_metrics, "friendlyHoldout": friendly_metrics,
        "beatsFixedHistoricalBaseRateOnLogLossAndBrier": improves, "promotionAllowed": False,
        "promotionBlock": "requires clean prospective confirmation plus broader HBT-1.4 interaction/ablation validation",
    }
    output = {
        "schemaVersion": SCHEMA, "version": VERSION, "generatedAt": now(), "targetDate": target.isoformat(),
        "policy": {"researchOnly": True, "frozenHBT112Mutated": False, "domesticForecastsMutated": False,
                   "bookmakerOddsRead": False, "pointInTimeCausality": True, "missingIsZero": False,
                   "unsupportedRelabelledAsSupportedWithoutEvidence": False, "automaticPromotion": False,
                   "automaticFunding": False, "cleanProspectiveConfirmationRequired": True},
        "historySource": source_meta, "recentSupplement": supplement, "validation": validation,
        "domainSummary": dict(sorted(Counter(x["domain"] for x in domain_rows).items())),
        "domainRows": domain_rows, "internationalCandidates": candidates,
        "summary": {"discoveredFixtures": len(domain_rows), "seniorMensInternationalCandidates": len(candidates), "pricedOrFunded": 0, "r0Shadow": len(candidates)},
    }
    INTL.mkdir(parents=True, exist_ok=True)
    write_json(INTL / f"hbt_international_challenger_{target.isoformat()}.json", output)
    write_json(INTL / "hbt_international_validation.json", {"version": VERSION, "generatedAt": output["generatedAt"], "historySource": source_meta, "validation": validation})
    print(json.dumps({"targetDate": target.isoformat(), "domainSummary": output["domainSummary"], "summary": output["summary"], "validation": validation}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
