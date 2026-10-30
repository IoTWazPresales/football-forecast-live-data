#!/usr/bin/env python3
"""Read-only HBT fixture-coverage triage. Never creates predictions or bets."""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1] / "hbt_live_data"
OPAQUE_LABEL = re.compile(
    r"^(?:regular-season|(?:torneo-)?apertura(?:-20\d{2})?|"
    r"(?:torneo-)?clausura(?:-20\d{2})?|league-phase|"
    r"fall-season|final-stage|second-round|"
    r"(?:eastern-conference-|western-conference-)?playoffs.*|"
    r"semifinals|clausura-quadrangular)$", re.IGNORECASE)
EXPLICIT_OUT_OF_SCOPE = re.compile(
    r"(?:ncaa|women|womens|women's|liga-f|girls|youth|under-\d+|under \d+|"
    r"\bu(?:17|18|19|20|21|23)\b|reserves?)", re.IGNORECASE)

def group_status(row: dict) -> str:
    support = row.get("hbtSupportLevel")
    if support == "FULL_MODEL":
        return "MODEL_OUTPUT_AVAILABLE"
    if support == "FALLBACK":
        return "FALLBACK_OUTPUT_AVAILABLE"
    label = str(row.get("competitionSlug") or row.get("competition") or "").strip()
    if EXPLICIT_OUT_OF_SCOPE.search(label):
        return "EXPLICIT_OUT_OF_SCOPE"
    # A label like 'regular-season' says nothing about the country's league.
    if not label or OPAQUE_LABEL.fullmatch(label):
        return "COMPETITION_IDENTITY_NEEDS_PROOF"
    if support in ("INSUFFICIENT_DATA", "NOT_YET_READY"):
        return "CURRENT_MODEL_COVERAGE_GAP"
    return "UNMODELLED_COMPETITION_RESEARCH"

def triage(doc: dict) -> dict:
    rows = doc.get("fixtures") or []
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[group_status(row)].append(row)
    by_group = {}
    for category, members in sorted(grouped.items()):
        comps = collections.Counter(str(x.get("competition") or "unknown") for x in members)
        by_group[category] = {
            "count": len(members),
            "competitions": [
                {"name": name, "fixtures": count}
                for name, count in comps.most_common()
            ],
            "examples": [
                {"home": x.get("home"), "away": x.get("away"),
                 "competition": x.get("competition"),
                 "kickoff": x.get("kickoff"),
                 "scannerSupport": x.get("hbtSupportLevel")}
                for x in members[:12]
            ],
        }
    return {
        "schemaVersion": "HBT-COVERAGE-TRIAGE-1",
        "targetDate": doc.get("targetDate"),
        "sourceGeneratedAt": doc.get("generatedAt"),
        "summary": {
            "fixturesDiscovered": len(rows),
            "modelOutputs": len(grouped["MODEL_OUTPUT_AVAILABLE"]),
            "fallbackOutputs": len(grouped["FALLBACK_OUTPUT_AVAILABLE"]),
            "currentModelGaps": len(grouped["CURRENT_MODEL_COVERAGE_GAP"]),
            "researchExpansionCandidates": len(grouped["UNMODELLED_COMPETITION_RESEARCH"]),
            "identityUnproven": len(grouped["COMPETITION_IDENTITY_NEEDS_PROOF"]),
            "explicitOutOfScope": len(grouped["EXPLICIT_OUT_OF_SCOPE"]),
        },
        "groups": by_group,
        "policy": {
            "descriptiveOnly": True,
            "confidenceFromClassification": False,
            "provesSeniorMensIdentity": False,
            "createsModelForecasts": False,
            "createsBettingEligibility": False,
            "changesTraining": False,
            "bookmakerDataUsed": False,
        },
    }

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--input", type=pathlib.Path)
    p.add_argument("--output", type=pathlib.Path)
    a = p.parse_args()
    date = dt.date.fromisoformat(a.date).isoformat()
    source = a.input or ROOT / f"slate_scanner_{date}.json"
    doc = json.loads(source.read_text(encoding="utf-8"))
    if doc.get("targetDate") != date:
        raise SystemExit("Date mismatch: refusing cross-date HBT coverage triage")
    out = triage(doc)
    destination = a.output or ROOT / f"hbt_coverage_triage_{date}.json"
    destination.write_text(json.dumps(out, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps(out["summary"], indent=2))

if __name__ == "__main__":
    main()
