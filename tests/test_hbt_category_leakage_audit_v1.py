"""Offline, network-free regression tests for explicit category leakage."""
import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hbt_category_leakage_audit_v1 import audit, exclusion_reason, git_blob_sha


class CategoryLeakageTests(unittest.TestCase):
    def setUp(self):
        self.forecast = {"targetDate": "2026-10-25", "sourceLabVersion": "HBT-1.1.2L-R1",
                         "predictions": [{"fixture": {"date": "2026-10-25", "home": "FC Utrecht",
                                                      "away": "ADO Den Haag", "league": "nl.1"}}]}
        self.scanner = {"targetDate": "2026-10-25", "fixtures": [{
            "date": "2026-10-25", "home": "FC Utrecht", "away": "ADO Den Haag",
            "competition": "2026-27-vrouwen-eredivisie", "competitionSlug": "2026-27-vrouwen-eredivisie",
            "hbtLeague": "nl.1", "rankEligible": True, "sourceFixtureIds": {"ESPN_ALL": "401882145"}}]}

    def test_known_womens_eredivisie_row_blocked_even_when_rank_eligible(self):
        r = audit(self.forecast, self.scanner)
        self.assertEqual(len(r["explicitCategoryBlocks"]), 1)
        self.assertEqual(r["explicitCategoryBlocks"][0]["reason"], "EXPLICIT_WOMEN_COMPETITION")
        self.assertTrue(r["explicitCategoryBlocks"][0]["scannerRankEligible"])

    def test_pec_zwolle_womens_row_blocked(self):
        self.forecast["predictions"][0]["fixture"].update(home="PEC Zwolle", away="FC Twente")
        self.scanner["fixtures"][0].update(home="PEC Zwolle", away="FC Twente")
        self.assertEqual(len(audit(self.forecast, self.scanner)["explicitCategoryBlocks"]), 1)

    def test_senior_mens_competition_is_not_explicitly_blocked(self):
        self.scanner["fixtures"][0]["competition"] = "Eredivisie"
        self.scanner["fixtures"][0]["competitionSlug"] = "eredivisie"
        r = audit(self.forecast, self.scanner)
        self.assertEqual(len(r["noExplicitCategoryBlock"]), 1)
        self.assertEqual(len(r["explicitCategoryBlocks"]), 0)

    def test_unknown_competition_is_unresolved_not_mens(self):
        self.scanner["fixtures"][0]["competition"] = "regular-season"
        self.scanner["fixtures"][0]["competitionSlug"] = ""
        self.assertEqual(audit(self.forecast, self.scanner)["unresolvedIdentity"][0]["reason"],
                         "COMPETITION_IDENTITY_NOT_ESTABLISHED")

    def test_missing_scanner_identity_is_unresolved(self):
        self.scanner["fixtures"] = []
        self.assertEqual(len(audit(self.forecast, self.scanner)["unresolvedIdentity"]), 1)

    def test_ambiguous_scanner_identity_is_unresolved(self):
        self.scanner["fixtures"].append(copy.deepcopy(self.scanner["fixtures"][0]))
        self.assertEqual(audit(self.forecast, self.scanner)["unresolvedIdentity"][0]["matches"], 2)

    def test_youth_reserve_college_excluded(self):
        for label, expected in [("UEFA U19", "YOUTH"), ("U21 Premier League", "YOUTH"),
                                ("Bundesliga Reserves", "RESERVE"), ("NCAA Division I Men", "COLLEGE")]:
            with self.subTest(label=label):
                self.assertEqual(exclusion_reason(label), f"EXPLICIT_{expected}_COMPETITION")

    def test_multilingual_womens_markers(self):
        for label in ("Vrouwen Eredivisie", "Frauen Bundesliga", "Liga Femenina", "Women's Super League"):
            with self.subTest(label=label):
                self.assertEqual(exclusion_reason(label), "EXPLICIT_WOMEN_COMPETITION")

    def test_duplicate_forecast_is_rejected(self):
        self.forecast["predictions"].append(copy.deepcopy(self.forecast["predictions"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            audit(self.forecast, self.scanner)

    def test_wrong_target_or_model_rejected(self):
        self.scanner["targetDate"] = "2026-10-26"
        with self.assertRaisesRegex(ValueError, "target"):
            audit(self.forecast, self.scanner)
        self.scanner["targetDate"] = "2026-10-25"
        self.forecast["sourceLabVersion"] = "UNFROZEN"
        with self.assertRaisesRegex(ValueError, "version"):
            audit(self.forecast, self.scanner)

    def test_git_blob_sha_matches_canonical_format(self):
        data = b"test\n"
        self.assertEqual(git_blob_sha(data), hashlib.sha1(b"blob 5\0test\n").hexdigest())


if __name__ == "__main__":
    unittest.main()
