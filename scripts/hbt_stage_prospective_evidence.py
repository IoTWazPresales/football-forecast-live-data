#!/usr/bin/env python3
"""Fail-closed staging of HBT prospective evidence, not a betting action.

Do not publish a 'successful' prospective run when any required forecast,
model-market research, desk, immutable capture or provenance source is missing.
The previous workflow used a broad 'git add ... || true': one nonexistent
optional path could abort the whole staging command without failing the run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "hbt_live_data"

LIVE_OPTIONAL = (
    "slate_scanner.json", "market_prices.json", "forecast_bridge_status.json",
    "manifest.json", "performance.json", "player_features.json",
    "pre_xi_context.json", "market_intelligence.json",
    "hbt_1_4_match_intelligence.json", "_hbt_1_4_live_cache.json",
)

def load(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"HBT expected JSON object: {path}")
    return obj

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def mandatory_names(date: str) -> tuple[str, ...]:
    return (
        f"frozen_control_forecast_{date}.json",
        f"hbt_execution_surface_{date}.json",
        f"hbt_betting_desk_{date}.json",
        f"hbt_betting_desk_{date}.html",
        f"hbt_bet_list_{date}.json",
        f"hbt_bet_list_{date}.md",
        f"slate_scanner_{date}.json",
        f"market_prices_{date}.json",
        f"hbt_independent_kickoffs_{date}.json",
        f"hbt_recovered_fusion_shadow_{date}.json",
        f"hbt_firstadd_market_watch_{date}.json",
        f"hbt_coverage_triage_{date}.json",
        f"hbt_current_capture_{date}.json",
    )

def validate_date(data: Path, date: str) -> list[Path]:
    import datetime as dt
    dt.date.fromisoformat(date)
    mandatory = [data / name for name in mandatory_names(date)]
    missing = [str(path.name) for path in mandatory if not path.is_file() or not path.stat().st_size]
    if missing:
        raise ValueError(f"HBT evidence missing on {date}: {', '.join(missing)}")
    for name in mandatory_names(date):
        if not name.endswith(".json"):
            continue
        if load(data / name).get("targetDate") != date:
            raise ValueError(f"HBT artifact target date mismatch: {name}")
    frozen = data / f"frozen_control_forecast_{date}.json"
    shadow = data / f"hbt_recovered_fusion_shadow_{date}.json"
    desk = data / f"hbt_betting_desk_{date}.json"
    bet = load(data / f"hbt_bet_list_{date}.json")
    hashes = bet.get("sourceHashes") or {}
    expected = {
        "forecast": sha(frozen),
        "recoveredFusion": sha(shadow),
    }
    for key, actual in expected.items():
        if hashes.get(key) != actual:
            raise ValueError(f"HBT {date} bet-list lineage mismatch: {key}")
    if bet.get("deskSha256") != sha(desk):
        raise ValueError(f"HBT {date} desk bytes mismatch bet-list SHA-256")
    shadow_doc = load(shadow)
    if (shadow_doc.get("sourceHashes") or {}).get("control") != sha(frozen):
        raise ValueError(f"HBT {date} Fusion shadow references a missing/mismatched frozen forecast")
    if shadow_doc.get("policy", {}).get("controlForecastUnchanged") is not True:
        raise ValueError(f"HBT {date} Fusion changed frozen forecast")
    if not (data / "captures").is_dir():
        raise ValueError("HBT immutable capture folder missing")
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from hbt_capture_store import capture_path
    capture_path(data, date)  # SHA-256, target date and immutable-policy checks
    if load(data / f"hbt_firstadd_market_watch_{date}.json").get("policy", {}).get("noBettingEligibility") is not True:
        raise ValueError(f"HBT {date} market watch unexpectedly authorizes a bet")
    if load(data / f"hbt_coverage_triage_{date}.json").get("policy", {}).get("createsBettingEligibility") is not False:
        raise ValueError(f"HBT {date} coverage triage unexpectedly authorizes a bet")
    return mandatory

def stage(dates: list[str], root: Path = ROOT) -> dict:
    data = root / "hbt_live_data"
    if not dates:
        raise ValueError("At least one HBT target date is required")
    mandatory = []
    for date in dates:
        mandatory.extend(validate_date(data, date))
    for path in mandatory:
        subprocess.run(["git", "add", "--", str(path.relative_to(root))],
                       cwd=root, check=True)
        subprocess.run(["git", "ls-files", "--error-unmatch", "--",
                        str(path.relative_to(root))], cwd=root,
                       check=True, stdout=subprocess.DEVNULL)
    # An original pre-kickoff card may be absent for newly generated dates:
    # --refresh records a new hash-pinned immutable capture and pointer instead.
    # Never require or fabricate a retroactive original card.
    for date in dates:
        original = data / f"hbt_prospective_card_{date}.json"
        if original.is_file():
            subprocess.run(["git", "add", "--", str(original.relative_to(root))],
                           cwd=root, check=True)
    for name in LIVE_OPTIONAL:
        path = data / name
        if path.is_file():
            subprocess.run(["git", "add", "--", str(path.relative_to(root))],
                           cwd=root, check=True)
    subprocess.run(["git", "add", "--", "hbt_live_data/captures/"],
                   cwd=root, check=True)
    return {"validatedDates": dates, "mandatoryFilesValidated": len(mandatory),
            "optionalFilesStagedIfPresent": True, "failClosed": True}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", nargs="+", required=True)
    args = parser.parse_args()
    print(json.dumps(stage(args.dates), indent=2))

if __name__ == "__main__":
    main()
