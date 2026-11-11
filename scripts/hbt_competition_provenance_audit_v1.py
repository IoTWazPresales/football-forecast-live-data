#!/usr/bin/env python3
"""Read-only HBT bridge/scanner competition provenance audit.

Detects *explicit* Brazilian-vs-Italian Serie A conflicts. It never guesses
competition identity from the unqualified phrase 'Serie A', never creates
predictions, and never changes the frozen bridge or any stored artifacts.
Use same-run, commit-pinned scanner, bridge-status and forecast JSON inputs.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any


def normalized(value: Any) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = value.encode("ascii", "ignore").decode().casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def competition_country(row: dict[str, Any]) -> str | None:
    """Only explicitly country-qualified Serie A labels are sufficient."""
    name = normalized(row.get("competition"))
    slug = normalized(row.get("competitionSlug"))
    labels = f"{name} {slug}"
    brazil = bool(re.search(r"\bbrasileiro serie a\b|\bbrazilian serie a\b", labels))
    italy = bool(re.search(r"\bitalian serie a\b|\bitaly serie a\b", labels))
    return "BRAZIL" if brazil and not italy else "ITALY" if italy and not brazil else None


def pair(home: Any, away: Any) -> tuple[str, str]:
    return normalized(home), normalized(away)


def excluded_pair(fixture: Any) -> tuple[str, str] | None:
    if not isinstance(fixture, str):
        return None
    pieces = re.split(r"\s+vs\.?\s+", fixture, maxsplit=1, flags=re.I)
    return pair(*pieces) if len(pieces) == 2 else None


def audit(scanner: dict[str, Any], bridge: dict[str, Any], forecast: dict[str, Any]) -> dict[str, Any]:
    dates = [doc.get("targetDate") for doc in (scanner, bridge, forecast)]
    if not all(isinstance(d, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in dates) or len(set(dates)) != 1:
        raise ValueError("Same targetDate required for all three snapshots")
    fixtures = scanner.get("fixtures")
    exclusions = (bridge.get("target") or {}).get("excluded")
    predictions = forecast.get("predictions")
    if not isinstance(fixtures, list) or not isinstance(exclusions, list) or not isinstance(predictions, list):
        raise ValueError("Scanner fixtures, bridge exclusions and forecast predictions must be lists")

    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    issues: list[dict[str, Any]] = []
    brazil_rows = 0
    false_supported = 0
    conflicts = 0
    ambiguous = 0
    unmatched = 0
    for row in fixtures:
        if not isinstance(row, dict):
            raise ValueError("Malformed scanner fixture")
        by_pair[pair(row.get("home"), row.get("away"))].append(row)
        if competition_country(row) != "BRAZIL":
            continue
        brazil_rows += 1
        if row.get("hbtSupportLevel") in {"INSUFFICIENT_DATA", "NOT_YET_READY", "FULL_MODEL", "FALLBACK"}:
            false_supported += 1
            issues.append({"code": "BRAZIL_SERIE_A_FALSE_MODEL_SUPPORT", "fixture": f"{row.get('home')} vs {row.get('away')}",
                           "competition": row.get("competition"), "status": row.get("hbtSupportLevel"),
                           "rankEligible": bool(row.get("rankEligible")), "sourceFixtureIds": row.get("sourceFixtureIds")})

    for row in exclusions:
        if not isinstance(row, dict):
            raise ValueError("Malformed bridge exclusion")
        k = excluded_pair(row.get("fixture"))
        matches = by_pair.get(k, []) if k else []
        if len(matches) != 1:
            ambiguous += int(len(matches) > 1)
            unmatched += int(len(matches) == 0)
            continue
        country = competition_country(matches[0])
        league = row.get("league")
        if country == "BRAZIL" and league == "it.1" or country == "ITALY" and league != "it.1":
            conflicts += 1
            issues.append({"code": "BRIDGE_EXCLUSION_COMPETITION_CONFLICT", "fixture": row.get("fixture"),
                           "bridgeLeague": league, "scannerCompetition": matches[0].get("competition"),
                           "scannerSourceFixtureIds": matches[0].get("sourceFixtureIds")})

    prediction_conflicts = 0
    for pred in predictions:
        if not isinstance(pred, dict):
            raise ValueError("Malformed forecast prediction")
        fx = pred.get("fixture") or {}
        matches = by_pair.get(pair(fx.get("home"), fx.get("away")), [])
        if len(matches) != 1:
            continue
        country = competition_country(matches[0])
        league = fx.get("league")
        if country == "BRAZIL" and league == "it.1" or country == "ITALY" and league != "it.1":
            prediction_conflicts += 1
            issues.append({"code": "FORECAST_COMPETITION_CONFLICT", "fixture": f"{fx.get('home')} vs {fx.get('away')}",
                           "forecastLeague": league, "scannerCompetition": matches[0].get("competition")})

    return {"targetDate": dates[0], "status": "PROVENANCE_CONFLICT" if issues else "NO_EXPLICIT_CONFLICT_FOUND",
            "counts": {"scannerFixtures": len(fixtures), "explicitBrazilSerieAFixtures": brazil_rows,
                       "brazilFalseSupported": false_supported, "bridgeExclusions": len(exclusions),
                       "bridgeExclusionConflicts": conflicts, "forecastCompetitionConflicts": prediction_conflicts,
                       "ambiguousExclusionMatches": ambiguous, "unmatchedExclusions": unmatched},
            "issues": sorted(issues, key=lambda x: (x["code"], x["fixture"])),
            "limitations": ["Explicit country-qualified Serie A identity only; ambiguous leagues are not inferred.",
                            "Same-run snapshots must be independently authenticated to Git commit and source clocks.",
                            "No model training-lineage, fixture results, bookmaker prices or betting readiness is asserted."]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("scanner", "bridge", "forecast"):
        ap.add_argument(f"--{name}", type=Path, required=True)
    args = ap.parse_args()
    documents = [json.loads(getattr(args, name).read_text(encoding="utf-8")) for name in ("scanner", "bridge", "forecast")]
    print(json.dumps(audit(*documents), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
