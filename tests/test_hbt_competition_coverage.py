"""Competition-scoped HBT coverage checks; no promotion or betting paths."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hbt_scan_slate_v2 as scanner


class CompetitionCoverageTests(unittest.TestCase):
    def test_exact_senior_model_competition_slugs(self):
        for label in [
            "2026-27-ligue-1", "2026-27-german-bundesliga",
            "2026-27-laliga", "french ligue 1", "italian serie a",
            "English Premier League", "German Bundesliga",
        ]:
            with self.subTest(label=label):
                self.assertTrue(scanner.full_model_comp(
                    {"competitionSlug": label}, None, None
                ))

    def test_no_substring_league_or_tier_confusion(self):
        for label in [
            "2026-27-german-2-bundesliga",
            "2026-27-russian-premier-league",
            "2026-brasileiro-serie-a",
            "2026-27-saudi-pro-league",
            "2026-27-spanish-liga-f",
            "2026-27-english-womens-super-league",
            "2026-27-ligue-2",
            "2026-ncaa-division-i-men",
            "2026-ncaa-division-i-women",
            "regular-season",
            "Premier League",
            "Serie A",
            "Bundesliga",
        ]:
            with self.subTest(label=label):
                self.assertFalse(scanner.full_model_comp(
                    {"competitionSlug": label}, None, None
                ))

    def test_explicit_competition_code_overrides_ambiguous_name(self):
        self.assertFalse(scanner.full_model_comp(
            {"leagueHint": "en.2", "competition": "Premier League"}, None, None
        ))
        self.assertFalse(scanner.full_model_comp(
            {"leagueHint": "it.2", "competition": "Serie A"}, None, None
        ))
        self.assertTrue(scanner.full_model_comp(
            {"leagueHint": "en.1", "competition": "Premier League"}, None, None
        ))
        self.assertTrue(scanner.full_model_comp(
            {"leagueHint": "it.1", "competition": "Serie A"}, None, None
        ))

    def test_known_intelligence_competition_code(self):
        hit = {"rows": {"HBT14": {"league": "fr.1"}}}
        self.assertTrue(scanner.full_model_comp(
            {"competition": "Ligue 1"}, hit, None
        ))

    def test_only_coverage_status_changes_not_forecast_or_betting(self):
        fixture = {
            "home": "Team A", "away": "Team B",
            "kickoff": "2026-10-31T18:00:00Z",
            "competitionSlug": "2026-27-russian-premier-league",
        }
        row = scanner.classify(fixture, None, None, {})
        self.assertEqual(row["hbtSupportLevel"], "UNSUPPORTED_COMPETITION")
        self.assertFalse(row["rankEligible"])
        self.assertIsNone(row["probabilityOutput"])
        self.assertFalse(row["rankEligibleFullModel"])
        self.assertFalse(row["rankEligibleFallback"])


if __name__ == "__main__":
    unittest.main()
