"""Fail-closed, offline invariants for 1 Nov category-aware HBT settlement.

These tests validate the pinned evidence structure and P1 Git blobs present in
this checkout; they do NOT independently fetch external result sources or
certify historical feature as-of lineage. Never authorize betting.
"""
import hashlib
import json
import math
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/evidence/hbt_2026_11_01_category_aware_settlement_manifest.json"
DATA = json.loads(MANIFEST.read_text(encoding="utf-8"))


def utc(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("explicit UTC required")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def score(records, field):
    n = len(records)
    correct = 0
    brier = logloss = 0.0
    dc = [0.0, 0.0, 0.0]
    for r in records:
        p = r["l0Probs"] if field == "l0Probs" else r["fusionP1"]["probs"]
        home, away = r["result"]
        outcome = 0 if home > away else (1 if home == away else 2)
        correct += int(p.index(max(p)) == outcome)
        brier += sum((v - int(i == outcome)) ** 2 for i, v in enumerate(p))
        logloss -= math.log(p[outcome])
        for j, (q, event) in enumerate([
            (p[0] + p[1], outcome != 2),
            (p[1] + p[2], outcome != 0),
            (p[0] + p[2], outcome != 1),
        ]):
            dc[j] += (q - int(event)) ** 2
    return (n, correct, brier / n, logloss / n, [v / n for v in dc])


class HbtNovember1EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.records = DATA["records"]
        self.paired = [r for r in self.records if r["fusionP1"]]

    def test_fixed_authority_and_frozen_version(self):
        self.assertEqual(DATA["authorityBranch"], "research/hbt-1.4-match-intelligence")
        self.assertEqual(DATA["frozenVersion"], "HBT-1.1.2L-R1")
        self.assertEqual(DATA["targetDate"], "2026-11-01")
        self.assertEqual(DATA["l0FirstAdd"]["commit"], "736adb22b33d6093b4568dd5aaf89974609d98c7")
        self.assertEqual(DATA["fusionFirstAdd"]["commit"], "a4c8c8931a30d6284e185f73a81f52e44d492fc6")

    def test_no_false_clean_or_betting_claim(self):
        self.assertFalse(DATA["cleanCalibrationEligible"])
        self.assertFalse(DATA["contemporaneousVerifiedBookmakerPrices"])
        self.assertFalse(DATA["bettingEligible"])
        self.assertIn("UNVERIFIED", DATA["evidenceState"])

    def test_original_coverage_and_exclusion(self):
        self.assertEqual(DATA["l0FirstAdd"]["originalPredictions"], 17)
        self.assertEqual(len(self.records), 14)
        self.assertEqual(len(DATA["excludedWrongCategory"]), 3)
        self.assertEqual(len(self.paired), 6)
        self.assertEqual(14 + 3, 17)

    def test_womens_rows_explicitly_quarantined(self):
        self.assertEqual(
            {(r["fixture"]["home"], r["fixture"]["away"]) for r in DATA["excludedWrongCategory"]},
            {("ADO Den Haag", "Feyenoord Rotterdam"),
             ("AZ Alkmaar", "PEC Zwolle"),
             ("FC Utrecht", "De Graafschap")},
        )
        self.assertTrue(all(r["category"] == "women" and
                            r["status"] == "EXCLUDED_WRONG_CATEGORY" and
                            r["evidenceUrl"].startswith("https://")
                            for r in DATA["excludedWrongCategory"]))
        self.assertTrue(all(r["category"] == "senior_men" for r in self.records))

    def test_unique_fixtures_across_both_categories(self):
        all_rows = self.records + DATA["excludedWrongCategory"]
        keys = [(r["fixture"]["date"], r["fixture"]["league"],
                 r["fixture"]["home"].casefold(), r["fixture"]["away"].casefold())
                for r in all_rows]
        self.assertEqual(len(keys), len(set(keys)))

    def test_regulation_time_and_independent_links(self):
        for r in self.records:
            self.assertEqual(r["status"], "FT_90")
            self.assertTrue(r["regulationTimeVerified"])
            self.assertEqual(r["fixture"]["date"], DATA["targetDate"])
            self.assertTrue(r["resultEvidenceUrl"].startswith("https://"))
            self.assertTrue(r["kickoffEvidenceUrl"].startswith("https://"))
            self.assertEqual(len(r["result"]), 2)
            self.assertTrue(all(type(n) is int and n >= 0 for n in r["result"]))
            utc(r["kickoffUtc"])

    def test_original_commit_before_every_verified_kickoff(self):
        l0 = utc(DATA["l0FirstAdd"]["committedAtUtc"])
        p1 = utc(DATA["fusionFirstAdd"]["committedAtUtc"])
        for r in self.records:
            self.assertLess(l0, utc(r["kickoffUtc"]))
            if r["fusionP1"]:
                self.assertLess(p1, utc(r["kickoffUtc"]))
                self.assertLess(utc(r["fusionP1"]["capturedAtUtc"]), utc(r["kickoffUtc"]))

    def test_all_probabilities_are_valid(self):
        for r in self.records + DATA["excludedWrongCategory"]:
            self.assertEqual(len(r["l0Probs"]), 3)
            self.assertAlmostEqual(sum(r["l0Probs"]), 1.0, places=9)
            self.assertTrue(all(0 < v < 1 for v in r["l0Probs"]))
            if r.get("fusionP1"):
                p = r["fusionP1"]["probs"]
                self.assertEqual(len(p), 3)
                self.assertAlmostEqual(sum(p), 1.0, places=9)
                self.assertTrue(all(0 < v < 1 for v in p))

    def test_p1_git_blob_and_forecast_match_original_capture(self):
        for r in self.paired:
            pinned = r["fusionP1"]
            path = ROOT / pinned["path"]
            raw = path.read_bytes()
            git_blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            self.assertEqual(git_blob, pinned["gitBlobSha"])
            source = json.loads(raw)
            self.assertEqual(source["fixtureIdentityKey"].split("|")[0], "2026-11-01")
            self.assertEqual(source["forecast"]["fixture"]["home"], r["fixture"]["home"])
            self.assertEqual(source["forecast"]["fixture"]["away"], r["fixture"]["away"])
            self.assertEqual(source["forecast"]["probs"], pinned["probs"])
            self.assertEqual(source["sourceSha256"], pinned["sourceSha256"])
            self.assertEqual(source["capturedAt"], pinned["capturedAtUtc"])
            self.assertFalse(source["policy"]["cleanCalibrationEligible"])
            self.assertFalse(source["forecast"]["executionEligible"])
            for market, prob in pinned["scoreMarkets"].items():
                self.assertAlmostEqual(source["forecast"]["scoreMarkets"][market], prob, places=12)

    def test_original_l0_blob_is_pinned_not_mutable_latest(self):
        self.assertEqual(DATA["l0FirstAdd"]["gitBlobSha"], "2e8488e16bbf871833b1d513b8acea2af61c039a")
        self.assertTrue(DATA["l0FirstAdd"]["path"].endswith("frozen_control_forecast_2026-11-01.json"))

    def test_l0_mens_scores(self):
        n, correct, brier, logloss, dc = score(self.records, "l0Probs")
        expected = DATA["metrics"]["l0Men"]
        self.assertEqual((n, correct), (14, 8))
        self.assertAlmostEqual(brier, expected["multiclassBrier"], places=12)
        self.assertAlmostEqual(logloss, expected["logLoss"], places=12)
        for got, key in zip(dc, ("oneX", "x2", "twelve")):
            self.assertAlmostEqual(got, expected["dcBrier"][key], places=12)

    def test_paired_l0_and_fusion_scoring(self):
        for field, name, hits in [("l0Probs", "pairedL0", 3), ("fusionP1", "fusionP1", 4)]:
            n, correct, brier, logloss, dc = score(self.paired, field)
            expected = DATA["metrics"][name]
            self.assertEqual((n, correct), (6, hits))
            self.assertAlmostEqual(brier, expected["multiclassBrier"], places=12)
            self.assertAlmostEqual(logloss, expected["logLoss"], places=12)
            for got, key in zip(dc, ("oneX", "x2", "twelve")):
                self.assertAlmostEqual(got, expected["dcBrier"][key], places=12)

    def test_l4_goals_are_separate_from_fusion_1x2(self):
        for key, event in (
            ("bttsYes", lambda h, a: h > 0 and a > 0),
            ("over15", lambda h, a: h + a > 1),
            ("over25", lambda h, a: h + a > 2),
            ("over35", lambda h, a: h + a > 3),
        ):
            brier = sum((r["fusionP1"]["scoreMarkets"][key] -
                         int(event(*r["result"]))) ** 2 for r in self.paired) / 6
            self.assertAlmostEqual(brier, DATA["metrics"]["l4GoalBrier"][key], places=12)

    def test_reliability_bins_are_descriptive_only(self):
        for name in ("l0Men", "pairedL0", "fusionP1"):
            metric = DATA["metrics"][name]
            self.assertEqual(sum(b["n"] for b in metric["reliabilityBins"]), metric["n"])
            self.assertTrue(all(0 <= b["meanTopConfidence"] <= 1 and
                                0 <= b["topPickAccuracy"] <= 1
                                for b in metric["reliabilityBins"]))

    def test_source_clock_notes_and_missing_roi(self):
        noted = {(r["fixture"]["home"], r["fixture"]["away"])
                 for r in self.records if r.get("sourceClockNote")}
        self.assertIn(("SBV Excelsior", "FC Twente '65"), noted)
        self.assertIn(("Telstar 1963", "FC Utrecht"), noted)
        self.assertFalse(DATA["contemporaneousVerifiedBookmakerPrices"])


if __name__ == "__main__":
    unittest.main()
