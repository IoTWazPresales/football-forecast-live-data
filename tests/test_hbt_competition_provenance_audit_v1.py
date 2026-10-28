"""Offline, synthetic regressions for explicit competition provenance conflicts."""
import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hbt_competition_provenance_audit_v1 import audit, competition_country, excluded_pair


def scanner_row(home, away, competition, status="INSUFFICIENT_DATA"):
    return {"home": home, "away": away, "competition": competition,
            "competitionSlug": competition, "hbtSupportLevel": status,
            "rankEligible": status in ("FALLBACK", "FULL_MODEL"),
            "sourceFixtureIds": {"ESPN_ALL": "fixture-id"}}


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.scanner = {"targetDate": "2026-10-28", "fixtures": [
            scanner_row("Fluminense", "Internacional", "2026-brasileiro-serie-a"),
            scanner_row("Red Bull Bragantino", "Chapecoense", "2026-brasileiro-serie-a"),
            scanner_row("Santos", "Palmeiras", "2026-brasileiro-serie-a"),
            scanner_row("Bahia", "São Paulo", "2026-brasileiro-serie-a"),
            scanner_row("Remo", "Botafogo", "2026-brasileiro-serie-a"),
            scanner_row("Parma", "Udinese", "2026-27-italian-serie-a"),
        ]}
        self.bridge = {"targetDate": "2026-10-28", "target": {"excluded": [
            {"fixture": "Fluminense vs Internacional", "league": "it.1"},
            {"fixture": "Red Bull Bragantino vs Chapecoense", "league": "it.1"},
            {"fixture": "Santos vs Palmeiras", "league": "it.1"},
            {"fixture": "Parma vs Udinese", "league": "it.1"},
        ]}}
        self.forecast = {"targetDate": "2026-10-28", "predictions": []}

    def run_audit(self):
        return audit(self.scanner, self.bridge, self.forecast)

    def test_28_oct_reproduction(self):
        c = self.run_audit()["counts"]
        self.assertEqual((c["explicitBrazilSerieAFixtures"], c["brazilFalseSupported"], c["bridgeExclusionConflicts"]), (5, 5, 3))

    def test_true_italian_exclusion_not_flagged(self):
        self.assertFalse(any(x["fixture"] == "Parma vs Udinese" for x in self.run_audit()["issues"]))

    def test_ambiguous_serie_a_not_inferred(self):
        self.assertIsNone(competition_country({"competition": "Serie A", "competitionSlug": "serie-a"}))

    def test_explicit_country_classification(self):
        self.assertEqual(competition_country({"competitionSlug": "2026-brasileiro-serie-a"}), "BRAZIL")
        self.assertEqual(competition_country({"competitionSlug": "2026-27-italian-serie-a"}), "ITALY")

    def test_conflicting_source_country_is_not_inferred(self):
        self.assertIsNone(competition_country({"competition": "Italian Serie A", "competitionSlug": "2026-brasileiro-serie-a"}))

    def test_italian_mislabelled_exclusion(self):
        self.bridge["target"]["excluded"][-1]["league"] = "br.1"
        self.assertEqual(self.run_audit()["counts"]["bridgeExclusionConflicts"], 4)

    def test_detect_predicted_cross_league(self):
        self.forecast["predictions"] = [{"fixture": {"home": "Fluminense", "away": "Internacional", "league": "it.1"}}]
        self.assertEqual(self.run_audit()["counts"]["forecastCompetitionConflicts"], 1)

    def test_no_false_alarm_for_italian_forecast(self):
        self.forecast["predictions"] = [{"fixture": {"home": "Parma", "away": "Udinese", "league": "it.1"}}]
        self.assertEqual(self.run_audit()["counts"]["forecastCompetitionConflicts"], 0)

    def test_wrong_dates_fail_closed(self):
        self.forecast["targetDate"] = "2026-10-27"
        with self.assertRaises(ValueError): self.run_audit()

    def test_missing_scanner_fixtures_fail_closed(self):
        self.scanner.pop("fixtures")
        with self.assertRaises(ValueError): self.run_audit()

    def test_duplicate_fixture_is_ambiguous(self):
        self.scanner["fixtures"].append(deepcopy(self.scanner["fixtures"][0]))
        self.assertEqual(self.run_audit()["counts"]["ambiguousExclusionMatches"], 1)

    def test_no_mutation(self):
        original = deepcopy((self.scanner, self.bridge, self.forecast))
        self.run_audit()
        self.assertEqual((self.scanner, self.bridge, self.forecast), original)

    def test_accent_normalization(self):
        self.assertEqual(excluded_pair("Bahía vs São Paulo"), ("bahia", "sao paulo"))

    def test_unsupported_brazil_not_misflagged(self):
        for row in self.scanner["fixtures"][:5]:
            row["hbtSupportLevel"] = "UNSUPPORTED_COMPETITION"
        self.assertEqual(self.run_audit()["counts"]["brazilFalseSupported"], 0)


if __name__ == "__main__": unittest.main()
