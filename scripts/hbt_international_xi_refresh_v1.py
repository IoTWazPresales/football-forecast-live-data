#!/usr/bin/env python3
"""Refresh international XI context without mutating frozen research probabilities.

Reads the timing/venue-safe prospective international card and writes a separate
XI context artifact only when roster/lineup state materially changes. The source
prospective file is hashed and never rewritten here. No bookmaker data is read.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import hbt_international_context_v2 as ctx

ROOT = Path(__file__).resolve().parents[1]
INTL = ROOT / "hbt_live_data" / "international"
VERSION = "HBT-1.4-INTERNATIONAL-XI-CONTEXT-1"


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


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(d: dt.datetime) -> str:
    return d.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def probability_fingerprint(row: dict[str, Any]) -> str:
    frozen = {
        "fixture": row.get("fixture"), "domain": row.get("domain"), "predictionMode": row.get("predictionMode"),
        "probs": row.get("probs"), "pick": row.get("pick"), "pickProbability": row.get("pickProbability"),
        "derivedMarkets": row.get("derivedMarkets"), "state": row.get("state"), "venueContext": row.get("venueContext"),
        "capture": row.get("capture"),
    }
    raw = json.dumps(frozen, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def stable_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        xi = r.get("officialXI") or {}
        out.append({
            "sourceFixtureId": r.get("sourceFixtureId"), "fixture": r.get("fixture"),
            "probabilityFingerprint": r.get("probabilityFingerprint"),
            "status": r.get("status"), "leadMinutes": r.get("leadMinutes"),
            "confirmedXI": xi.get("confirmedXI"), "starterCounts": xi.get("starterCounts"),
            "leagueIdentity": xi.get("leagueIdentity"), "rosters": xi.get("rosters"),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--date", required=True); args = ap.parse_args()
    target = dt.date.fromisoformat(args.date)
    src = INTL / f"hbt_international_prospective_{target.isoformat()}.json"
    out_path = INTL / f"hbt_international_xi_context_{target.isoformat()}.json"
    if not src.exists():
        print(f"No international prospective card for {target}; XI refresh skipped")
        return 0
    doc = read(src, {})
    if doc.get("targetDate") != target.isoformat():
        raise SystemExit("international prospective targetDate mismatch")

    source_bytes = src.read_bytes(); source_sha = hashlib.sha256(source_bytes).hexdigest()
    checked = now_utc(); rows = []
    for row in doc.get("prospectiveCandidates") or []:
        fx = row.get("fixture") or {}; ko = ctx.parse_dt(fx.get("kickoff")); eid = str(row.get("sourceFixtureId") or "")
        pre = bool(ko and ko > checked)
        lead = (ko - checked).total_seconds()/60.0 if ko else None
        item = {
            "fixture": fx, "sourceFixtureId": eid or None,
            "probabilityFingerprint": probability_fingerprint(row),
            "status": "PRE_KICKOFF" if pre else "POST_KICKOFF_OR_UNVERIFIED",
            "leadMinutes": lead,
        }
        if pre and eid:
            item["officialXI"] = ctx.probe_summary(eid)
        else:
            item["officialXI"] = {"available": False, "confirmedXI": False, "reason": "not probed after kickoff or event id unavailable"}
        rows.append(item)

    candidate = {
        "schemaVersion": "HBT-INTERNATIONAL-XI-CONTEXT-1", "version": VERSION,
        "generatedAt": iso(checked), "targetDate": target.isoformat(),
        "sourceProspective": src.name, "sourceProspectiveSha256": source_sha,
        "policy": {
            "footballProbabilitiesMutated": False, "sourceProspectiveMutated": False,
            "bookmakerOddsRead": False, "confirmedXIContextOnly": True,
            "automaticPromotion": False, "automaticFunding": False,
        },
        "summary": {
            "rows": len(rows), "preKickoff": sum(r["status"] == "PRE_KICKOFF" for r in rows),
            "summaryAvailable": sum(bool((r.get("officialXI") or {}).get("available")) for r in rows),
            "confirmedXI": sum(bool((r.get("officialXI") or {}).get("confirmedXI")) for r in rows),
        },
        "rows": rows,
    }

    old = read(out_path, {})
    if old and old.get("sourceProspectiveSha256") == source_sha and stable_rows(old.get("rows") or []) == stable_rows(rows):
        print(json.dumps({"changed": False, "summary": candidate["summary"]}, indent=2))
        return 0
    write(out_path, candidate)
    print(json.dumps({"changed": True, "summary": candidate["summary"], "rows": [
        {"fixture": r.get("fixture"), "status": r.get("status"), "leadMinutes": r.get("leadMinutes"),
         "confirmedXI": (r.get("officialXI") or {}).get("confirmedXI"), "starterCounts": (r.get("officialXI") or {}).get("starterCounts")}
        for r in rows
    ]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
