"""Offline synthetic regressions for German top/second-tier HBT provenance."""
import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hbt_german_tier_provenance_audit_v1 import audit, german_tier, excluded_pair


def fixture(home, away, comp, status="INSUFFICIENT_DATA"):
    return {"home": home, "away": away, "competition": comp,
            "competitionSlug": comp, "hbtSupportLevel": status,
            "rankEligible": status in ("FULL_MODEL", "FALLBACK"), "hbtLeague": None}


class GermanTierTests(unittest.TestCase):
    def setUp(self):
        self.scanner = {"targetDate": "2026-10-30", "fixtures": [
            fixture("Arminia Bielefeld", "TSV Eintracht Braunschweig", "2026-27-german-2-bundesliga"),
            fixture("Energie Cottbus", "VfL Bochum", "2026-27-german-2-bundesliga"),
            fixture("SV Elversberg", "Mainz", "2026-27-german-bundesliga"),
            fixture("Le Havre AC", "Paris Saint-Germain", "2026-27-ligue-1", "FALLBACK"),
        ]}
        self.bridge = {"targetDate": "2026-10-30", "target": {"excluded": [
            {"fixture": "Arminia Bielefeld vs TSV Eintracht Braunschweig", "league": "de.1"},
            {"fixture": "Energie Cottbus vs VfL Bochum", "league": "de.1"},
            {"fixture": "SV Elversberg vs Mainz", "league": "de.1"},
        ]}}
        self.forecast = {"targetDate": "2026-10-30", "predictions": []}

    def run_audit(self):
        return audit(self.scanner, self.bridge, self.forecast)

    def test_reproduces_two_false_supports_and_two_bridge_mislabels(self):
        c = self.run_audit()["counts"]
        self.assertEqual((c["explicitGermanSecondTier"], c["falseSupportedSecondTier"], c["bridgeSecondTierAsDe1"]), (2, 2, 2))

    def test_true_bundesliga_not_flagged(self):
        self.assertFalse(any("Elversberg" in i["fixture"] for i in self.run_audit()["issues"]))

    def test_second_tier_invariant(self):
        self.assertEqual(german_tier({"competitionSlug": "2026-27-german-2-bundesliga"}), 2)
        self.assertEqual(german_tier({"competitionSlug": "2. Bundesliga"}), 2)
        self.assertEqual(german_tier({"competition": "Bundesliga 2"}), 2)

    def test_top_tier_explicit_only(self):
        self.assertEqual(german_tier({"competitionSlug": "2026-27-german-bundesliga"}), 1)
        self.assertIsNone(german_tier({"competition": "Bundesliga"}))

    def test_ambiguous_conflicting_labels_not_inferred(self):
        self.assertIsNone(german_tier({"competition": "German Bundesliga", "competitionSlug": "german-2-bundesliga"}))

    def test_non_german_competitions_not_inferred(self):
        for label in ("Austrian Bundesliga", "Brazilian Serie A", "German 3 Liga", "women's Bundesliga"):
            self.assertIsNone(german_tier({"competition": label}))

    def test_unsupported_second_tier_no_false_support(self):
        for r in self.scanner["fixtures"][:2]:
            r["hbtSupportLevel"] = "UNSUPPORTED_COMPETITION"
        self.assertEqual(self.run_audit()["counts"]["falseSupportedSecondTier"], 0)

    def test_second_tier_forecast_conflict(self):
        self.forecast["predictions"] = [{"fixture": {"home": "Energie Cottbus", "away": "VfL Bochum", "league": "de.1"}}]
        self.assertEqual(self.run_audit()["counts"]["forecastSecondTierAsDe1"], 1)

    def test_no_forecast_conflict_for_genuine_top_tier(self):
        self.forecast["predictions"] = [{"fixture": {"home": "SV Elversberg", "away": "Mainz", "league": "de.1"}}]
        self.assertEqual(self.run_audit()["counts"]["forecastSecondTierAsDe1"], 0)

    def test_duplicate_exclusion_match_is_ambiguous(self):
        self.scanner["fixtures"].append(deepcopy(self.scanner["fixtures"][0]))
        self.assertEqual(self.run_audit()["counts"]["ambiguousExclusionMatches"], 1)

    def test_mismatched_date_rejected(self):
        self.forecast["targetDate"] = "2026-10-29"
        with self.assertRaises(ValueError): self.run_audit()

    def test_missing_input_rejected(self):
        self.bridge["target"].pop("excluded")
        with self.assertRaises(ValueError): self.run_audit()

    def test_malformed_prediction_rejected(self):
        self.forecast["predictions"] = [{"fixture": "bad"}]
        with self.assertRaises(ValueError): self.run_audit()

    def test_inputs_unchanged(self):
        original = deepcopy((self.scanner, self.bridge, self.forecast))
        self.run_audit()
        self.assertEqual((self.scanner, self.bridge, self.forecast), original)

    def test_normalizes_accents(self):
        self.assertEqual(excluded_pair("Köln vs Düsseldorf"), ("koln", "dusseldorf"))


if __name__ == "__main__":
    unittest.main()
