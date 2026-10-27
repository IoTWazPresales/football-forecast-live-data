"""Offline tests for the read-only snapshot readiness diagnostic."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hbt_snapshot_readiness_audit_v1 import audit


class SnapshotReadinessTests(unittest.TestCase):
    def setUp(self):
        self.forecast = {
            "sourceLabVersion": "HBT-1.1.2L-R1", "targetDate": "2026-10-27",
            "sourceExportedAt": "2026-10-27T00:52:13Z", "policy": {"prospectiveExport": True},
            "predictions": []}
        self.scanner = {
            "targetDate": "2026-10-27", "generatedAt": "2026-10-27T00:52:14Z",
            "coverage": {"fixturesDiscovered": 3, "classifiedRows": 3,
                         "INSUFFICIENT_DATA": 3, "forecastRowsAvailable": 0,
                         "forecastRowsMatched": 0},
            "rankingGate": {"discoveryComplete": True, "rankEligibleFixtures": 0},
            "fixtures": [{"hbtSupportLevel": "INSUFFICIENT_DATA", "rankEligible": False} for _ in range(3)]}

    def test_zero_predictions_not_ready_despite_discovery(self):
        r = audit(self.forecast, self.scanner)
        self.assertFalse(r["forecastRowsPresentAndMatched"])
        self.assertFalse(r["fullFusionRowsPresent"])
        self.assertIn("DISCOVERY_COMPLETE_BUT_PREDICTION_EMPTY", r["flags"])
        self.assertEqual(r["supportCounts"]["INSUFFICIENT_DATA"], 3)
        self.assertFalse(r["categoryAndKickoffVerified"])
        self.assertFalse(r["seniorMensPredictionReadinessEstablished"])

    def test_valid_fallback_is_not_full_fusion(self):
        self.forecast["predictions"] = [{"fixture": {"date": "2026-10-27", "league": "tr.1", "home": "A", "away": "B"}, "probs": [.5,.3,.2]}]
        self.scanner["fixtures"][0] = {"hbtSupportLevel": "FALLBACK", "rankEligible": True}
        self.scanner["coverage"].update({"FALLBACK": 1, "INSUFFICIENT_DATA": 2, "forecastRowsAvailable": 1, "forecastRowsMatched": 1})
        self.scanner["rankingGate"]["rankEligibleFixtures"] = 1
        r = audit(self.forecast, self.scanner)
        self.assertTrue(r["forecastRowsPresentAndMatched"])
        self.assertFalse(r["fullFusionRowsPresent"])

    def test_mismatched_date_rejected(self):
        self.scanner["targetDate"] = "2026-10-26"
        with self.assertRaises(ValueError): audit(self.forecast, self.scanner)

    def test_scanner_too_late_rejected(self):
        self.scanner["generatedAt"] = "2026-10-27T01:00:00Z"
        with self.assertRaises(ValueError): audit(self.forecast, self.scanner)

    def test_scanner_before_forecast_rejected(self):
        self.scanner["generatedAt"] = "2026-10-27T00:52:12Z"
        with self.assertRaises(ValueError): audit(self.forecast, self.scanner)

    def test_invalid_counts_rejected(self):
        self.scanner["coverage"]["fixturesDiscovered"] = 4
        with self.assertRaises(ValueError): audit(self.forecast, self.scanner)

    def test_ranked_count_inconsistency_rejected(self):
        self.scanner["rankingGate"]["rankEligibleFixtures"] = 1
        with self.assertRaises(ValueError): audit(self.forecast, self.scanner)

    def test_missing_frozen_version_rejected(self):
        self.forecast["sourceLabVersion"] = "HBT-2.0"
        with self.assertRaises(ValueError): audit(self.forecast, self.scanner)

    def test_invalid_probability_rejected(self):
        self.forecast["predictions"] = [{"fixture": {"date": "2026-10-27", "league": "tr.1", "home": "A", "away": "B"}, "probs": [.5,.5,.5]}]
        with self.assertRaises(ValueError): audit(self.forecast, self.scanner)

    def test_duplicate_forecast_rejected(self):
        row = {"fixture": {"date": "2026-10-27", "league": "tr.1", "home": "A", "away": "B"}, "probs": [.5,.3,.2]}
        self.forecast["predictions"] = [row, copy.deepcopy(row)]
        with self.assertRaises(ValueError): audit(self.forecast, self.scanner)

    def test_non_utc_clock_rejected(self):
        self.forecast["sourceExportedAt"] = "2026-10-27T02:52:13+02:00"
        with self.assertRaises(ValueError): audit(self.forecast, self.scanner)


if __name__ == "__main__":
    unittest.main()
