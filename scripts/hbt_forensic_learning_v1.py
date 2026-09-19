#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "hbt_live_data"
FORENSIC = DATA / "forensic"
UA = "Mozilla/5.0 (compatible; HBT-Forensic-Learning/1.0)"
VERSION = "HBT-FORENSIC-LEARNING-1"

LEAGUE_SLUGS = {
    "en.1": "eng.1", "en.2": "eng.2", "es.1": "esp.1", "es.2": "esp.2",
    "de.1": "ger.1", "de.2": "ger.2", "it.1": "ita.1", "it.2": "ita.2",
    "fr.1": "fra.1", "fr.2": "fra.2", "be.1": "bel.1", "nl.1": "ned.1",
    "pt.1": "por.1", "sco.1": "sco.1", "tr.1": "tur.1",
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def http_json(url: str, timeout: int = 20) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def norm(s: Any) -> str:
    x = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    x = re.sub(r"\b(fc|cf|afc|ac|ssc|sc|rc|club|football|futbol|the)\b", " ", x)
    x = re.sub(r"[^a-z0-9]+", " ", x)
    return " ".join(x.split())


def fixture_key(home: Any, away: Any) -> str:
    return f"{norm(home)}|{norm(away)}"


def canonical_hash(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def source_candidates(date: str) -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    d = dt.date.fromisoformat(date)
    mon = d.strftime("%b").lower()
    names = [
        DATA / f"hbt_prospective_card_{date}.json",
        DATA / f"hbt_{d.day:02d}{mon}_resolver_v3_candidates.json",
        DATA / f"hbt_{d.day}{mon}_resolver_v3_candidates.json",
        DATA / f"hbt_broad_test_card_{date}.json",
        DATA / f"hbt_shadow_reconstructed_bets_{date}.json",
    ]
    for p in names:
        if not p.exists():
            continue
        doc = read_json(p, {})
        rows = doc.get("candidates") or doc.get("card") or doc.get("bets") or doc.get("predictions") or []
        if rows:
            return p, doc, rows
    raise SystemExit(f"no prospective HBT card found for {date}")


def row_fixture(row: dict[str, Any]) -> dict[str, Any]:
    fx = row.get("fixture")
    return fx if isinstance(fx, dict) else {
        "home": row.get("home"), "away": row.get("away"), "date": row.get("date"),
        "league": row.get("league"), "sourceFixtureId": row.get("sourceFixtureId")
    }


def probs3(row: dict[str, Any]) -> list[float] | None:
    p = row.get("probs")
    if isinstance(p, dict):
        vals = [p.get("H"), p.get("D"), p.get("A")]
    else:
        vals = p
    if not isinstance(vals, list) or len(vals) != 3:
        return None
    try:
        vals = [float(x) for x in vals]
    except Exception:
        return None
    if any(x < 0 or x > 1 for x in vals) or abs(sum(vals) - 1) > 0.03:
        return None
    return vals


def fetch_scoreboard(date: str) -> dict[str, dict[str, Any]]:
    ds = date.replace("-", "")
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={ds}&limit=1000"
    raw = http_json(url)
    out: dict[str, dict[str, Any]] = {}
    for ev in raw.get("events") or []:
        comp = (ev.get("competitions") or [{}])[0]
        teams = comp.get("competitors") or []
        h = next((x for x in teams if x.get("homeAway") == "home"), None)
        a = next((x for x in teams if x.get("homeAway") == "away"), None)
        if not h or not a:
            continue
        hn = (h.get("team") or {}).get("displayName") or (h.get("team") or {}).get("name")
        an = (a.get("team") or {}).get("displayName") or (a.get("team") or {}).get("name")
        completed = bool((ev.get("status") or {}).get("type", {}).get("completed") or (comp.get("status") or {}).get("type", {}).get("completed"))
        hs = h.get("score", {}).get("value") if isinstance(h.get("score"), dict) else h.get("score")
        as_ = a.get("score", {}).get("value") if isinstance(a.get("score"), dict) else a.get("score")
        rec = {
            "eventId": str(ev.get("id") or ""), "home": hn, "away": an, "completed": completed,
            "homeScore": float(hs) if hs not in (None, "") else None,
            "awayScore": float(as_) if as_ not in (None, "") else None,
            "status": ((ev.get("status") or {}).get("type") or {}).get("description"),
            "competition": ((comp.get("league") or {}).get("name") or (ev.get("season") or {}).get("slug")),
        }
        out[fixture_key(hn, an)] = rec
        if rec["eventId"]:
            out[f"id:{rec['eventId']}"] = rec
    return out


def summary_for(event_id: str, league_code: str | None) -> dict[str, Any]:
    if not event_id:
        return {}
    slugs = []
    if league_code and league_code in LEAGUE_SLUGS:
        slugs.append(LEAGUE_SLUGS[league_code])
    slugs += ["all"]
    for slug in slugs:
        try:
            return http_json(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/summary?event={event_id}")
        except Exception:
            pass
    return {}


def parse_stats(summary: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"teams": {}, "keyEvents": [], "lineups": {}, "dataAvailable": False}
    for team in ((summary.get("boxscore") or {}).get("teams") or []):
        name = ((team.get("team") or {}).get("displayName") or (team.get("team") or {}).get("name") or "Unknown")
        stats = {}
        for s in team.get("statistics") or []:
            k = s.get("name") or s.get("label")
            v = s.get("value") if s.get("value") is not None else s.get("displayValue")
            if k:
                stats[str(k)] = v
        if stats:
            result["teams"][name] = stats
            result["dataAvailable"] = True
    for roster in summary.get("rosters") or []:
        tname = ((roster.get("team") or {}).get("displayName") or "Unknown")
        athletes = roster.get("roster") or roster.get("athletes") or []
        starters = []
        for x in athletes:
            a = x.get("athlete") or x
            if x.get("starter") is True or str(x.get("starter", "")).lower() == "true":
                nm = a.get("displayName") or a.get("fullName")
                if nm:
                    starters.append(nm)
        if starters:
            result["lineups"][tname] = starters
            result["dataAvailable"] = True
    for p in summary.get("plays") or []:
        txt = str(p.get("text") or "")
        low = txt.lower()
        if any(k in low for k in ("red card", "penalty", "own goal", "sent off")):
            result["keyEvents"].append({"clock": (p.get("clock") or {}).get("displayValue"), "text": txt[:300]})
            result["dataAvailable"] = True
    return result


def result_code(hs: float, as_: float) -> str:
    return "H" if hs > as_ else "A" if as_ > hs else "D"


def settle_market(exec_row: dict[str, Any], hs: float, as_: float) -> str:
    market = str(exec_row.get("market") or "").upper()
    side = str(exec_row.get("side") or "").upper()
    rc = result_code(hs, as_)
    if market in {"HOME_WIN", "1X2_HOME"}: return "WIN" if rc == "H" else "LOSS"
    if market in {"AWAY_WIN", "1X2_AWAY"}: return "WIN" if rc == "A" else "LOSS"
    if market == "1X": return "WIN" if rc in {"H", "D"} else "LOSS"
    if market == "X2": return "WIN" if rc in {"D", "A"} else "LOSS"
    if market == "12": return "WIN" if rc in {"H", "A"} else "LOSS"
    if market == "DNB":
        if rc == "D": return "VOID"
        return "WIN" if (side == "HOME" and rc == "H") or (side == "AWAY" and rc == "A") else "LOSS"
    return "UNKNOWN"


def stat_number(stats: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for k, v in stats.items():
        if str(k).lower() in {n.lower() for n in names}:
            try:
                return float(str(v).replace("%", ""))
            except Exception:
                pass
    return None


def process_flags(post: dict[str, Any], home: str, away: str, actual: str, prediction_pick: str) -> list[str]:
    flags = []
    if not post.get("dataAvailable"):
        return ["POSTMATCH_PROCESS_DATA_GAP"]
    if any("red card" in str(x.get("text", "")).lower() or "sent off" in str(x.get("text", "")).lower() for x in post.get("keyEvents") or []):
        flags.append("IN_MATCH_RED_CARD_SHOCK_CANDIDATE")
    teams = post.get("teams") or {}
    hstats = next((v for k, v in teams.items() if norm(k) == norm(home)), {})
    astats = next((v for k, v in teams.items() if norm(k) == norm(away)), {})
    hsot = stat_number(hstats, ("shotsOnTarget", "shots on target")); asot = stat_number(astats, ("shotsOnTarget", "shots on target"))
    hshots = stat_number(hstats, ("totalShots", "shots", "total shots")); ashots = stat_number(astats, ("totalShots", "shots", "total shots"))
    if None not in (hsot, asot, hshots, ashots):
        actual_dominance = (hsot - asot) + 0.25 * (hshots - ashots)
        if actual == "A": actual_dominance *= -1
        if prediction_pick != actual and actual_dominance > 2.5:
            flags.append("SCORELINE_AND_SHOT_PROCESS_AGAINST_FORECAST")
        elif prediction_pick != actual and actual_dominance < -1.5:
            flags.append("RESULT_WRONG_PROCESS_POSSIBLY_RIGHT")
        elif prediction_pick == actual and actual_dominance < -1.5:
            flags.append("RESULT_CORRECT_PROCESS_REVIEW")
    return flags


def load_execution(date: str) -> dict[str, Any]:
    return read_json(DATA / f"hbt_betway_execution_{date}.json", {"singles": [], "multis": []})


def hypothesis_tags(row: dict[str, Any], actual_p: float, market_result: str | None, process: list[str]) -> list[str]:
    tags = list(process)
    if market_result == "LOSS": tags.append("MARKET_OUTCOME_MISS")
    if actual_p <= 0.20: tags.append("VERY_LOW_PROBABILITY_ACTUAL_OUTCOME")
    elif actual_p <= 0.30: tags.append("LOW_PROBABILITY_ACTUAL_OUTCOME")
    if row.get("coveragePack") == "C1": tags.append("C1_TRANSFER_CALIBRATION_REVIEW")
    if "stale" in str(row.get("coverage") or "").lower(): tags.append("STALE_STATE_REVIEW")
    if row.get("statusAtCapture") not in (None, "PRE_KICKOFF"):
        tags.append("CAUSAL_CAPTURE_REVIEW")
    return sorted(set(tags))


def update_hypothesis_registry(audits: list[dict[str, Any]]) -> dict[str, Any]:
    path = FORENSIC / "hbt_learning_hypotheses.json"
    reg = read_json(path, {"schemaVersion": "HBT-LEARNING-HYPOTHESES-1", "version": VERSION, "hypotheses": {}})
    hyp = reg.setdefault("hypotheses", {})
    for a in audits:
        for tag in a.get("learning", {}).get("hypothesisTags", []):
            z = hyp.setdefault(tag, {"status": "OBSERVE", "occurrences": 0, "lossOccurrences": 0, "examples": [], "promotionAllowed": False})
            z["occurrences"] += 1
            if a.get("execution", {}).get("settlement") == "LOSS" or a.get("predictionOutcome", {}).get("topPickCorrect") is False:
                z["lossOccurrences"] += 1
            ex = {"date": a.get("date"), "fixture": a.get("fixture"), "actual": a.get("actual", {}).get("result"), "sourceHash": a.get("preMatch", {}).get("immutableHash")}
            if ex not in z["examples"]:
                z["examples"] = (z["examples"] + [ex])[-12:]
    reg["updatedAt"] = now_iso()
    reg["policy"] = {
        "automaticModelMutation": False,
        "automaticFeaturePromotion": False,
        "promotionRequiresHistoricalBacktest": True,
        "promotionRequiresUnseenHoldoutImprovement": True,
        "preserveExistingIntelligence": True,
    }
    write_json(path, reg)
    return reg


def run(date: str) -> dict[str, Any]:
    source_path, source_doc, rows = source_candidates(date)
    scoreboard = fetch_scoreboard(date)
    execution = load_execution(date)
    exec_idx = {fixture_key(x.get("home"), x.get("away")): x for x in execution.get("singles") or []}
    audits = []
    settled = 0
    for row in rows:
        fx = row_fixture(row); home, away = fx.get("home"), fx.get("away")
        key = fixture_key(home, away)
        event_id = str(fx.get("sourceFixtureId") or "")
        result = scoreboard.get(f"id:{event_id}") if event_id else None
        result = result or scoreboard.get(key)
        p = probs3(row)
        audit = {
            "date": date, "fixture": f"{home} vs {away}", "home": home, "away": away,
            "preMatch": {
                "sourceFile": source_path.name,
                "sourceCapturedAt": source_doc.get("capturedAt") or source_doc.get("generatedAt"),
                "immutableHash": canonical_hash(row),
                "origin": row.get("origin") or source_doc.get("origin"),
                "tier": row.get("tier"), "rawTier": row.get("rawTier"), "quality": row.get("quality"),
                "coverage": row.get("coverage"), "coveragePack": row.get("coveragePack"),
                "predictionMode": row.get("predictionMode"), "probsHDA": p,
                "bookmakerObservedBeforeCapture": bool((source_doc.get("policy") or {}).get("bookmakerPriceObservedBeforeCapture", False)),
            },
            "actual": {"settled": False}, "predictionOutcome": {}, "execution": {}, "processEvidence": {}, "learning": {}
        }
        if not result or not result.get("completed") or result.get("homeScore") is None or result.get("awayScore") is None or not p:
            audit["learning"] = {"hypothesisTags": ["UNSETTLED_OR_RESULT_DATA_GAP"], "researchRequired": True, "modelMutationAllowed": False}
            audits.append(audit); continue
        settled += 1
        hs, as_ = float(result["homeScore"]), float(result["awayScore"])
        rc = result_code(hs, as_); actual_idx = {"H": 0, "D": 1, "A": 2}[rc]
        actual_p = p[actual_idx]; pick_idx = max(range(3), key=lambda i: p[i]); pick = ["H", "D", "A"][pick_idx]
        y = [1.0 if i == actual_idx else 0.0 for i in range(3)]
        brier = sum((p[i] - y[i]) ** 2 for i in range(3))
        logloss = -math.log(max(actual_p, 1e-12))
        audit["actual"] = {"settled": True, "homeScore": hs, "awayScore": as_, "result": rc, "eventId": result.get("eventId"), "competition": result.get("competition")}
        audit["predictionOutcome"] = {
            "topPick": pick, "topPickProbability": p[pick_idx], "topPickCorrect": pick == rc,
            "actualOutcomeProbability": actual_p, "brier": brier, "logLoss": logloss,
        }
        ex = exec_idx.get(key)
        market_result = None
        if ex:
            market_result = settle_market(ex, hs, as_)
            odds = float(ex.get("odds")) if ex.get("odds") is not None else None
            stake = float(ex.get("stake")) if ex.get("stake") is not None else None
            if market_result == "WIN" and odds and stake is not None: ret = stake * odds
            elif market_result == "VOID" and stake is not None: ret = stake
            elif market_result == "LOSS": ret = 0.0
            else: ret = None
            audit["execution"] = {**ex, "settlement": market_result, "return": ret, "profit": (ret - stake) if ret is not None and stake is not None else None}
        summary = summary_for(str(result.get("eventId") or event_id), fx.get("league"))
        post = parse_stats(summary)
        flags = process_flags(post, home, away, rc, pick)
        audit["processEvidence"] = post
        tags = hypothesis_tags(row, actual_p, market_result, flags)
        audit["learning"] = {
            "hypothesisTags": tags,
            "researchRequired": bool(market_result == "LOSS" or pick != rc or tags),
            "modelMutationAllowed": False,
            "featurePromotionAllowed": False,
            "nextStep": "Historical backtest + unseen holdout validation before any promotion" if tags else "Accumulate calibration evidence",
        }
        audits.append(audit)

    settled_rows = [a for a in audits if a.get("actual", {}).get("settled")]
    top_correct = sum(1 for a in settled_rows if a.get("predictionOutcome", {}).get("topPickCorrect"))
    exec_rows = [a for a in settled_rows if a.get("execution", {}).get("settlement")]
    exec_w = sum(1 for a in exec_rows if a["execution"]["settlement"] == "WIN")
    exec_l = sum(1 for a in exec_rows if a["execution"]["settlement"] == "LOSS")
    exec_v = sum(1 for a in exec_rows if a["execution"]["settlement"] == "VOID")
    stake = sum(float(a["execution"].get("stake") or 0) for a in exec_rows)
    ret = sum(float(a["execution"].get("return") or 0) for a in exec_rows)
    out = {
        "schemaVersion": "HBT-FORENSIC-AUDIT-1", "version": VERSION, "generatedAt": now_iso(), "targetDate": date,
        "policy": {
            "preMatchForecastImmutable": True, "postMatchEvidenceMayNotRewriteCapture": True,
            "auditAllSettledForecastsNotOnlyLosses": True, "automaticModelMutation": False,
            "automaticFeaturePromotion": False, "preserveExistingIntelligence": True,
            "hypothesesMustBeBacktested": True, "holdoutValidationRequired": True,
        },
        "source": {"prospectiveCard": source_path.name, "sourceHash": canonical_hash(source_doc)},
        "summary": {
            "forecasts": len(audits), "settled": len(settled_rows), "topPickCorrect": top_correct,
            "topPickAccuracy": top_correct / len(settled_rows) if settled_rows else None,
            "meanBrier": sum(a["predictionOutcome"]["brier"] for a in settled_rows) / len(settled_rows) if settled_rows else None,
            "meanLogLoss": sum(a["predictionOutcome"]["logLoss"] for a in settled_rows) / len(settled_rows) if settled_rows else None,
            "verifiedExecutions": len(exec_rows), "executionWins": exec_w, "executionLosses": exec_l, "executionVoids": exec_v,
            "executionStake": stake, "executionReturn": ret, "executionProfit": ret - stake,
        },
        "audits": audits,
        "multis": execution.get("multis") or [],
    }
    FORENSIC.mkdir(parents=True, exist_ok=True)
    write_json(FORENSIC / f"hbt_forensic_{date}.json", out)
    update_hypothesis_registry(audits)
    return out


def self_test() -> None:
    assert settle_market({"market": "DNB", "side": "HOME"}, 1, 1) == "VOID"
    assert settle_market({"market": "DNB", "side": "AWAY"}, 1, 2) == "WIN"
    assert settle_market({"market": "1X"}, 1, 1) == "WIN"
    assert settle_market({"market": "X2"}, 2, 1) == "LOSS"
    assert settle_market({"market": "12"}, 1, 1) == "LOSS"
    p = [0.6, 0.25, 0.15]; y = [1, 0, 0]
    brier = sum((p[i] - y[i]) ** 2 for i in range(3))
    assert abs(brier - 0.245) < 1e-9
    assert fixture_key("FC Groningen", "PEC Zwolle") == fixture_key("Groningen", "PEC Zwolle")
    print("HBT forensic self-test: PASS")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test(); return 0
    if not args.date:
        raise SystemExit("--date required")
    out = run(args.date)
    print(json.dumps(out["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
