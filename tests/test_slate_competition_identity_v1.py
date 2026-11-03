"""Offline regression tests for HBT competition identity and honest slate readiness."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hbt_scan_slate_v2 as slate


class CompetitionIdentityTests(unittest.TestCase):
    def generic(self):
        return {"source": "ESPN_ALL", "sourceFixtureId": "401915417",
                "kickoff": "2026-10-13T19:00:00Z", "home": "Arsenal",
                "away": "Lille", "competition": "league-phase",
                "competitionSlug": "league-phase"}

    def specific(self):
        return {"source": "ESPN:uefa.cl", "sourceFixtureId": "401915417",
                "kickoff": "2026-10-13T19:00:00Z", "home": "Arsenal",
                "away": "Lille", "competition": "UEFA Champions League",
                "competitionSlug": "uefa.cl", "leagueHint": "uefa.cl"}

    def test_specific_identity_wins_when_generic_first(self):
        found = slate.merge_sources([self.generic(), self.specific()])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["leagueHint"], "uefa.cl")
        self.assertEqual(found[0]["competition"], "UEFA Champions League")
        self.assertEqual(set(found[0]["fixtureSources"]), {"ESPN_ALL", "ESPN:uefa.cl"})

    def test_specific_identity_remains_when_specific_first(self):
        found = slate.merge_sources([self.specific(), self.generic()])
        self.assertEqual(found[0]["leagueHint"], "uefa.cl")
        self.assertEqual(found[0]["competition"], "UEFA Champions League")

    def test_known_mens_competition_without_prediction_is_not_ready(self):
        row = slate.merge_sources([self.generic(), self.specific()])[0]
        result = slate.classify(row, None, None, {})
        self.assertEqual(result["hbtSupportLevel"], "NOT_YET_READY")
        self.assertFalse(result["rankEligible"])
        self.assertIsNone(result["probabilityOutput"])

    def test_conflicting_specific_sources_fail_closed(self):
        other = {**self.specific(), "source": "ESPN:en.1", "leagueHint": "en.1"}
        row = slate.merge_sources([self.specific(), other])[0]
        result = slate.classify(row, None, None, {})
        self.assertEqual(result["hbtSupportLevel"], "SOURCE_FAILURE")
        self.assertFalse(result["rankEligible"])

    def test_reconciliation_preserves_saved_provider_evidence(self):
        saved = {**self.generic(),
                 "fixtureSources": ["ESPN_ALL", "ESPN:uefa.cl"],
                 "sourceFixtureIds": {"ESPN_ALL": "401915417", "ESPN:uefa.cl": "401915417"}}
        restored = slate.merge_sources([saved])[0]
        self.assertIn("ESPN:uefa.cl", restored["fixtureSources"])
        result = slate.classify(restored, None, None, {})
        self.assertEqual(result["hbtLeague"], "uefa.cl")
        self.assertEqual(result["competition"], "UEFA Champions League")
        self.assertEqual(result["hbtSupportLevel"], "NOT_YET_READY")
        self.assertFalse(result["rankEligible"])

    def test_womens_competition_is_not_promoted_to_mens(self):
        row = {"competition": "2026-womens-international-friendly",
               "home": "Sweden", "away": "Lithuania"}
        result = slate.classify(row, None, None, {})
        self.assertEqual(result["hbtSupportLevel"], "UNSUPPORTED_COMPETITION")
        self.assertFalse(result["rankEligible"])


if __name__ == "__main__":
    unittest.main()
