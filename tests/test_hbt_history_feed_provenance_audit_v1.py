"""Offline fail-closed regression tests for history-feed provenance classification."""
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hbt_history_feed_provenance_audit_v1.py"
spec = importlib.util.spec_from_file_location("hbt_history_feed_provenance_audit_v1", SCRIPT)
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


class HistoryFeedProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.bridge = {"targetDate": "2026-10-30", "generatedAt": "2026-10-30T09:34:57Z",
                       "stateAdvance": {"sourceFailures": [
                           {"source": "2026-27/sco.1", "error": "404 Not Found"},
                           {"source": "2026-27/tr.1", "error": "404 Not Found"},
                           {"source": "2026-27/uefa.cl", "error": "404 Not Found"}]}}
        self.index = {"repository": "openfootball/football.json", "season": "2026-27",
                      "ref": "master", "fetchedAt": "2026-10-30T09:00:00Z",
                      "files": ["de.1.json", "en.1.json", "es.1.json", "fr.1.json", "it.1.json", "nl.1.json", "pt.1.json"]}

    def test_three_confirmed_absent(self):
        result = audit_module.audit(self.bridge, self.index)
        self.assertEqual([r["category"] for r in result["failures"]], ["UPSTREAM_SEASON_FILE_ABSENT"] * 3)

    def test_file_present_but_failed_is_not_absent(self):
        self.index["files"].append("sco.1.json")
        self.assertEqual(audit_module.audit(self.bridge, self.index)["failures"][0]["category"], "FILE_PRESENT_BUT_REQUEST_FAILED")

    def test_non_404_failure_not_assumed_absent(self):
        self.bridge["stateAdvance"]["sourceFailures"][0]["error"] = "503 Service Unavailable"
        self.assertEqual(audit_module.audit(self.bridge, self.index)["failures"][0]["category"], "OTHER_SOURCE_FAILURE")

    def test_other_season_not_claimed(self):
        self.bridge["stateAdvance"]["sourceFailures"][0]["source"] = "2025-26/sco.1"
        self.assertEqual(audit_module.audit(self.bridge, self.index)["failures"][0]["category"], "SOURCE_NOT_COVERED_BY_INDEX")

    def test_malformed_source_not_claimed(self):
        self.bridge["stateAdvance"]["sourceFailures"][0]["source"] = "../../sco.1"
        self.assertEqual(audit_module.audit(self.bridge, self.index)["failures"][0]["category"], "SOURCE_NOT_COVERED_BY_INDEX")

    def test_wrong_repository_rejected(self):
        self.index["repository"] = "other/football.json"
        with self.assertRaises(ValueError):
            audit_module.audit(self.bridge, self.index)

    def test_missing_source_failures_rejected(self):
        self.bridge["stateAdvance"] = {}
        with self.assertRaises(ValueError):
            audit_module.audit(self.bridge, self.index)

    def test_bad_index_rejected(self):
        self.index["files"] = "sco.1.json"
        with self.assertRaises(ValueError):
            audit_module.audit(self.bridge, self.index)

    def test_no_mutation(self):
        import copy
        before_bridge, before_index = copy.deepcopy(self.bridge), copy.deepcopy(self.index)
        audit_module.audit(self.bridge, self.index)
        self.assertEqual(self.bridge, before_bridge)
        self.assertEqual(self.index, before_index)

    def test_no_forecast_or_backfill_authorization(self):
        policy = audit_module.audit(self.bridge, self.index)["policy"]
        self.assertFalse(policy["forecastInferred"])
        self.assertFalse(policy["backfillAllowed"])
        self.assertFalse(policy["stateMutated"])

    def test_invalid_season_rejected_before_network(self):
        with self.assertRaises(ValueError):
            audit_module.fetch_season_index("../../etc")

    def test_invalid_ref_rejected_before_network(self):
        with self.assertRaises(ValueError):
            audit_module.fetch_season_index("2026-27", "../bad")


if __name__ == "__main__":
    unittest.main()
