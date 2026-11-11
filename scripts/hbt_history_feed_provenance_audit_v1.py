#!/usr/bin/env python3
"""Read-only HBT source-availability audit. No forecasting or state mutation.

Cross-checks frozen-bridge season-file failures against a separately retrieved
OpenFootball season directory listing. A missing upstream file is not a
permission to substitute older-season results or invent model coverage.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

UPSTREAM_REPO = "openfootball/football.json"
SEASON_RE = re.compile(r"^(\d{4}-\d{2})/([a-z0-9.]+)$")


def fetch_season_index(season: str, ref: str = "master") -> dict:
    if not re.fullmatch(r"\d{4}-\d{2}", season):
        raise ValueError("Invalid season")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", ref):
        raise ValueError("Invalid ref")
    url = f"https://api.github.com/repos/{UPSTREAM_REPO}/contents/{season}?ref={ref}"
    req = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "HBT-read-only-history-audit/1.0"})
    with urlopen(req, timeout=15) as response:
        listing = json.load(response)
    if not isinstance(listing, list):
        raise ValueError("Upstream directory index is not a list")
    return {"repository": UPSTREAM_REPO, "season": season, "ref": ref,
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "files": sorted({r["name"] for r in listing if isinstance(r, dict) and r.get("type") == "file" and isinstance(r.get("name"), str)}),
            "sourceUrl": url}


def audit(bridge: dict, index: dict) -> dict:
    if not isinstance(bridge, dict) or not isinstance(index, dict):
        raise ValueError("Expected JSON objects")
    if index.get("repository") != UPSTREAM_REPO:
        raise ValueError("Unexpected upstream repository")
    if not re.fullmatch(r"\d{4}-\d{2}", str(index.get("season", ""))):
        raise ValueError("Unverified season index")
    if not isinstance(index.get("files"), list) or any(not isinstance(f, str) for f in index["files"]):
        raise ValueError("Invalid upstream directory file list")
    failures = (bridge.get("stateAdvance") or {}).get("sourceFailures")
    if not isinstance(failures, list):
        raise ValueError("Bridge sourceFailures missing or invalid")
    files = set(index["files"])
    rows = []
    for failure in failures:
        if not isinstance(failure, dict):
            raise ValueError("Malformed failure row")
        source = str(failure.get("source", ""))
        error = str(failure.get("error", ""))
        match = SEASON_RE.fullmatch(source)
        if not match or match.group(1) != index["season"]:
            category = "SOURCE_NOT_COVERED_BY_INDEX"
        elif not re.search(r"\b404\b", error):
            category = "OTHER_SOURCE_FAILURE"
        elif f"{match.group(2)}.json" not in files:
            category = "UPSTREAM_SEASON_FILE_ABSENT"
        else:
            category = "FILE_PRESENT_BUT_REQUEST_FAILED"
        rows.append({"source": source, "error": error, "category": category,
                     "indexFile": f"{match.group(2)}.json" if match else None})
    return {"schemaVersion": "HBT-HISTORY-FEED-PROVENANCE-AUDIT-1",
            "targetDate": bridge.get("targetDate"), "bridgeGeneratedAt": bridge.get("generatedAt"),
            "index": {k: index.get(k) for k in ("repository", "season", "ref", "fetchedAt", "sourceUrl")},
            "failureCount": len(rows), "failures": rows,
            "policy": {"readOnly": True, "backfillAllowed": False, "forecastInferred": False,
                       "stateMutated": False, "missingFilesMeanMissingCoverage": True}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge", default="hbt_live_data/forecast_bridge_status.json")
    parser.add_argument("--season", default="2026-27")
    parser.add_argument("--ref", default="master")
    parser.add_argument("--index-json", help="Previously captured GitHub directory listing; avoids network")
    args = parser.parse_args()
    bridge = json.loads(Path(args.bridge).read_text(encoding="utf-8"))
    index = (json.loads(Path(args.index_json).read_text(encoding="utf-8")) if args.index_json
             else fetch_season_index(args.season, args.ref))
    result = audit(bridge, index)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"HBT history provenance audit failed closed: {exc}", file=sys.stderr)
        sys.exit(2)
