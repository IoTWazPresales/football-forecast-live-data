import copy
import math
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hbt_settlement_metrics_v1 import score_settled


class SettlementMetricsTests(unittest.TestCase):
    def setUp(self):
        self.forecast = {
            "sourceLabVersion": "HBT-1.1.2L-R1", "sourceExportedAt": "2026-10-23T23:32:27Z",
            "targetDate": "2026-10-24", "policy": {"prospectiveExport": True},
            "predictions": [{"fixture": {"date":"2026-10-24", "league":"en.1", "home":"A", "away":"B"},
                             "probs":[0.6,0.25,0.15]}]}
        self.provenance = {"firstAddVerified":True, "commitSha":"a"*40, "blobSha":"b"*40,
                           "committedAtUtc":"2026-10-23T23:32:30Z"}
        self.evidence = {"results":[{"date":"2026-10-24", "league":"en.1", "home":"A", "away":"B",
            "competition":"English Premier League", "category":"SENIOR_MEN", "status":"FT_REGULATION",
            "homeGoals":1, "awayGoals":0, "kickoffUtc":"2026-10-24T11:30:00Z",
            "resultSource":"https://www.skysports.com/football/score", "kickoffSource":"https://www.skysports.com/football/schedule"}]}

    def run_score(self):
        return score_settled(self.forecast,self.evidence,self.provenance)

    def test_exact_metrics_and_dc(self):
        r=self.run_score()
        self.assertEqual((r["verifiedSettled"],r["forecastCount"]),(1,1))
        self.assertEqual(r["accuracy"],1)
        self.assertAlmostEqual(r["multiclassBrierUnhalved"],0.245)
        self.assertAlmostEqual(r["multiclassLogLoss"],-math.log(.6))
        self.assertAlmostEqual(r["doubleChance"]["1X"]["brier"],.15**2)
        self.assertAlmostEqual(r["doubleChance"]["X2"]["brier"],.4**2)
        self.assertAlmostEqual(r["doubleChance"]["12"]["brier"],.25**2)

    def test_no_goal_or_roi_inference(self):
        r=self.run_score()
        self.assertIn("UNAVAILABLE",r["bttsAndGoalTotals"])
        self.assertIn("UNAVAILABLE",r["r5HypotheticalROI"])

    def test_missing_result_not_fabricated(self):
        self.evidence["results"]=[]
        r=self.run_score()
        self.assertEqual(r["verifiedSettled"],0)
        self.assertIsNone(r["accuracy"])

    def test_post_kickoff_commit_rejected(self):
        self.provenance["committedAtUtc"]="2026-10-24T12:00:00Z"
        with self.assertRaises(ValueError): self.run_score()

    def test_post_kickoff_export_rejected(self):
        self.forecast["sourceExportedAt"]="2026-10-24T12:00:00Z"
        self.provenance["committedAtUtc"]="2026-10-24T12:00:01Z"
        with self.assertRaises(ValueError): self.run_score()

    def test_non_utc_kickoff_rejected(self):
        self.evidence["results"][0]["kickoffUtc"]="2026-10-24T13:30:00+02:00"
        with self.assertRaises(ValueError): self.run_score()

    def test_youth_or_women_rejected(self):
        for cat in ("WOMEN", "YOUTH", "RESERVES", "COLLEGE"):
            with self.subTest(cat=cat):
                self.evidence["results"][0]["category"]=cat
                with self.assertRaises(ValueError): self.run_score()

    def test_extra_time_or_unfinished_rejected(self):
        for status in ("LIVE", "FT_AFTER_EXTRA_TIME", "ABANDONED"):
            with self.subTest(status=status):
                self.evidence["results"][0]["status"]=status
                with self.assertRaises(ValueError): self.run_score()

    def test_duplicate_result_rejected(self):
        self.evidence["results"].append(copy.deepcopy(self.evidence["results"][0]))
        with self.assertRaises(ValueError): self.run_score()

    def test_duplicate_forecast_rejected(self):
        self.forecast["predictions"].append(copy.deepcopy(self.forecast["predictions"][0]))
        with self.assertRaises(ValueError): self.run_score()

    def test_unknown_fixture_rejected(self):
        self.evidence["results"][0]["home"]="C"
        with self.assertRaises(ValueError): self.run_score()

    def test_invalid_probability_rejected(self):
        self.forecast["predictions"][0]["probs"]=[.6,.25,.2]
        with self.assertRaises(ValueError): self.run_score()

    def test_independent_source_required(self):
        self.evidence["results"][0]["resultSource"]="https://github.com/model/results"
        with self.assertRaises(ValueError): self.run_score()

    def test_first_add_attestation_required(self):
        self.provenance["firstAddVerified"]=False
        with self.assertRaises(ValueError): self.run_score()

    def test_wrong_model_rejected(self):
        self.forecast["sourceLabVersion"]="HBT-2.0"
        with self.assertRaises(ValueError): self.run_score()

    def test_invalid_regulation_goals_rejected(self):
        self.evidence["results"][0]["homeGoals"]=-1
        with self.assertRaises(ValueError): self.run_score()

if __name__ == "__main__": unittest.main()
