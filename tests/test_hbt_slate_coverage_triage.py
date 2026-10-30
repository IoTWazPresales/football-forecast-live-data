"""Read-only fixture universe triage keeps unknowns visible and bets unchanged."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hbt_slate_coverage_triage as triage


def fixture(comp, status):
    return {"home": "Home", "away": "Away", "competition": comp,
            "competitionSlug": comp, "hbtSupportLevel": status}

class CoverageTriageTests(unittest.TestCase):
    def test_clearly_out_of_scope(self):
        for label in ("2026-ncaa-division-i-men", "2026-ncaa-division-i-women",
                      "2026-27-english-womens-super-league", "2026-27-spanish-liga-f"):
            with self.subTest(label=label):
                self.assertEqual(triage.group_status(fixture(
                    label, "UNSUPPORTED_COMPETITION")), "EXPLICIT_OUT_OF_SCOPE")

    def test_opaque_competition_requires_identity(self):
        for label in ("regular-season", "apertura-2026", "torneo-clausura",
                      "playoffs---quarterfinals", "league-phase"):
            with self.subTest(label=label):
                self.assertEqual(triage.group_status(fixture(
                    label, "UNSUPPORTED_COMPETITION")), "COMPETITION_IDENTITY_NEEDS_PROOF")

    def test_model_gap_is_not_equivalent_to_missing_training(self):
        self.assertEqual(triage.group_status(fixture(
            "Ligue 1", "INSUFFICIENT_DATA")), "CURRENT_MODEL_COVERAGE_GAP")
        self.assertEqual(triage.group_status(fixture(
            "Bundesliga", "NOT_YET_READY")), "CURRENT_MODEL_COVERAGE_GAP")

    def test_distinguishes_league_expansion_from_unknown_predictions(self):
        self.assertEqual(triage.group_status(fixture(
            "2026-27-saudi-pro-league", "UNSUPPORTED_COMPETITION")),
            "UNMODELLED_COMPETITION_RESEARCH")
        self.assertEqual(triage.group_status(fixture(
            "Ekstraklasa", "UNSUPPORTED_COMPETITION")),
            "UNMODELLED_COMPETITION_RESEARCH")

    def test_read_only_counts_and_no_promoted_bets(self):
        doc = {"targetDate": "2026-10-30",
               "fixtures": [fixture("Ligue 1", "INSUFFICIENT_DATA"),
                            fixture("League of Ireland Premier Division", "UNSUPPORTED_COMPETITION"),
                            fixture("regular-season", "UNSUPPORTED_COMPETITION"),
                            fixture("2026-ncaa-division-i-women", "UNSUPPORTED_COMPETITION"),
                            fixture("Premier League", "FALLBACK")]}
        out = triage.triage(doc)
        self.assertEqual(sum(v for k,v in out["summary"].items() if k != "fixturesDiscovered"), 5)
        self.assertTrue(out["policy"]["descriptiveOnly"])
        self.assertFalse(out["policy"]["createsModelForecasts"])
        self.assertFalse(out["policy"]["createsBettingEligibility"])

if __name__ == "__main__":
    unittest.main()
