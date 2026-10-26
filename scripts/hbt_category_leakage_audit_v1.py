#!/usr/bin/env python3
"""Read-only HBT fixture-category audit; never changes frozen forecasts.

Supply commit-pinned forecast and same-run scanner JSON copies. The caller
must independently verify the first-add commit and the competition evidence.
A supported league code or a 1X2 probability never overrides an explicitly
excluded competition category. This is a research diagnostic, not a runtime gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

FROZEN_MODEL = "HBT-1.1.2L-R1"
EXCLUDED = {
    "WOMEN": re.compile(r"\b(?:women|womens|woman|female|ladies|vrouwen|vrouw|frauen|femenino|femenina|feminin|feminine|femmes|femmes?\s+league|liga\s+f)\b"),
    "YOUTH": re.compile(r"\b(?:youth|academy|juvenil|junior|juniors|under[ -]?(?:1[5-9]|2[0-3])|u(?:1[5-9]|2[0-3]))\b"),
    "RESERVE": re.compile(r"\b(?:reserve|reserves|b\s+team|second\s+team)\b"),
    "COLLEGE": re.compile(r"\b(?:ncaa|college|collegiate|university\s+soccer)\b"),
}


def git_blob_sha(data: bytes) -> str:
    """SHA-1 of Git's canonical blob object, not a file-content SHA-1."""
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def normalized(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def exclusion_reason(*labels: object) -> str | None:
    text = " ".join(normalized(label) for label in labels if label)
    for reason, pattern in EXCLUDED.items():
        if pattern.search(text):
            return f"EXPLICIT_{reason}_COMPETITION"
    return None


def fixture_key(fixture: dict) -> tuple[str, str, str]:
    return (str(fixture.get("date") or fixture.get("kickoff") or "")[:10],
            normalized(fixture.get("home")), normalized(fixture.get("away")))


def audit(forecast: dict, scanner: dict) -> dict:
    if forecast.get("sourceLabVersion") != FROZEN_MODEL:
        raise ValueError("Frozen model version mismatch")
    target = forecast.get("targetDate")
    if not target or scanner.get("targetDate") != target:
        raise ValueError("Snapshot target dates differ")
    predictions = forecast.get("predictions")
    fixtures = scanner.get("fixtures")
    if not isinstance(predictions, list) or not isinstance(fixtures, list):
        raise ValueError("Predictions or scanner fixtures missing")
    index: dict[tuple[str, str, str], list[dict]] = {}
    for row in fixtures:
        index.setdefault(fixture_key(row), []).append(row)
    blocked, unresolved, no_explicit_block, seen = [], [], [], set()
    for prediction in predictions:
        f = prediction.get("fixture") or {}
        k = fixture_key(f)
        if k in seen or k[0] != target or not k[1] or not k[2]:
            raise ValueError("Duplicate or invalid forecast fixture identity")
        seen.add(k)
        matches = index.get(k, [])
        record = {"fixture": f"{f.get('home')} vs {f.get('away')}", "date": target,
                  "forecastLeague": f.get("league")}
        if len(matches) != 1:
            unresolved.append({**record, "reason": "MISSING_OR_AMBIGUOUS_SCANNER_IDENTITY", "matches": len(matches)})
            continue
        row = matches[0]
        record.update({"competition": row.get("competition"), "competitionSlug": row.get("competitionSlug"),
                       "sourceFixtureIds": row.get("sourceFixtureIds"),
                       "scannerRankEligible": row.get("rankEligible")})
        reason = exclusion_reason(row.get("competition"), row.get("competitionSlug"),
                                  row.get("category"), row.get("gender"))
        if reason:
            blocked.append({**record, "reason": reason})
        elif not row.get("competition") or normalized(row.get("competition")) in ("unknown competition", "regular season", "league phase"):
            unresolved.append({**record, "reason": "COMPETITION_IDENTITY_NOT_ESTABLISHED"})
        else:
            no_explicit_block.append(record)
    return {"targetDate": target, "forecastCount": len(predictions),
            "explicitCategoryBlocks": blocked, "unresolvedIdentity": unresolved,
            "noExplicitCategoryBlock": no_explicit_block,
            "note": "No explicit category block is NOT independent verification of senior-men status; never score or fund without external identity and kickoff evidence."}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--forecast", type=Path, required=True)
    ap.add_argument("--scanner", type=Path, required=True)
    ap.add_argument("--forecast-blob", required=True, help="Expected pinned Git blob SHA")
    ap.add_argument("--scanner-blob", required=True, help="Expected same-run Git blob SHA")
    args = ap.parse_args()
    for path, sha in ((args.forecast, args.forecast_blob), (args.scanner, args.scanner_blob)):
        if not re.fullmatch(r"[0-9a-f]{40}", sha) or git_blob_sha(path.read_bytes()) != sha:
            raise SystemExit(f"Pinned Git blob mismatch: {path}")
    report = audit(json.loads(args.forecast.read_text(encoding="utf-8")),
                   json.loads(args.scanner.read_text(encoding="utf-8")))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
