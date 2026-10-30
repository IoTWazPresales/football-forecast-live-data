"""Immutable HBT Fusion research market watch tests: no odds, stakes or promotions."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hbt_rank_firstadd_markets_v1 as watch

DATE = "2026-10-31"

def card(stage="P1", captured="2026-10-30T15:30:47Z", fusion=None, goal_hda=None):
    return {
        "schemaVersion": "HBT-FUSION-FIRST-ADD-1",
        "targetDate": DATE, "capturedAt": captured,
        "policy": {"immutableFirstAdd": True, "bettingEligible": False},
        "forecast": {
            "fixture": {"date": DATE, "time": "18:00", "league": "en.1",
                        "home": "Home", "away": "Away"},
            "status": "RESEARCH_ONLY", "executionEligible": False,
            "predictionMode": "PRE-XI FUSION" if stage == "P1" else "CONFIRMED-XI FUSION",
            "probs": fusion if fusion is not None else [.7, .2, .1],
            "scoreMarkets": {
                "hda": goal_hda if goal_hda is not None else [.4, .4, .2],
                "oneX": .8, "over25": .6, "bttsYes": .55,
                "homeOver05": .75,
            },
            "diagnostics": {"preKickoff": True, "confirmedXi": stage == "P2"},
        },
    }

class FirstAddMarketWatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.folder = self.root / "captures" / "fusion"
        self.folder.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, doc, stage="P1", suffix="fixture"):
        p = self.folder / f"hbt_fusion_firstadd_{DATE}_{suffix}_{stage}.json"
        p.write_text(json.dumps(doc), encoding="utf-8")
        return p

    def test_derived_double_chance_uses_fusion_not_goal_l4(self):
        self.add(card())
        out = watch.build(DATE, self.root)
        rows = {x["market"]: x for x in out["allRankedMarkets"]}
        self.assertAlmostEqual(rows["1X"]["modelProbability"], .9)
        self.assertAlmostEqual(rows["X2"]["modelProbability"], .3)
        self.assertAlmostEqual(rows["12"]["modelProbability"], .8)
        self.assertEqual(rows["1X"]["probabilitySource"], "FUSION_HDA")
        self.assertEqual(rows["over25"]["probabilitySource"],
                         "L4_POISSON_GOAL_DISTRIBUTION")
        self.assertEqual(rows["over25"]["modelProbability"], .6)
        self.assertEqual(out["summary"]["uniqueFixturesWithFusionOutput"], 1)
        self.assertFalse(out["policy"]["noBettingEligibility"] is False)
        self.assertFalse(rows["1X"]["bettingEligible"])
        self.assertEqual(rows["1X"]["suggestedStakeRand"], 0)

    def test_prefers_p2_without_double_counting_fixture(self):
        self.add(card(), stage="P1", suffix="orig")
        self.add(card(stage="P2", fusion=[.6, .25, .15]), stage="P2", suffix="new")
        out = watch.build(DATE, self.root)
        self.assertEqual(out["summary"]["immutableFirstAddFiles"], 2)
        self.assertEqual(out["summary"]["uniqueFixturesWithFusionOutput"], 1)
        self.assertTrue(all(x["stage"] == "P2" for x in out["allRankedMarkets"]))

    def test_rejects_post_kickoff_capture(self):
        self.add(card(captured="2026-10-31T18:00:01Z"))
        with self.assertRaises(ValueError):
            watch.build(DATE, self.root)

    def test_rejects_invalid_probability_and_unapproved_bet(self):
        self.add(card(fusion=[1.1, -.2, .1]))
        with self.assertRaises(ValueError):
            watch.build(DATE, self.root)
        d = card(); d["policy"]["bettingEligible"] = True
        self.add(d)
        with self.assertRaises(ValueError):
            watch.build(DATE, self.root)

    def test_empty_day_is_not_fabricated(self):
        out = watch.build(DATE, self.root)
        self.assertEqual(out["summary"]["uniqueFixturesWithFusionOutput"], 0)
        self.assertEqual(out["allRankedMarkets"], [])
        self.assertEqual(out["status"], "RESEARCH_ONLY_NOT_BETTING_READY")

    def test_false_fusion_league_rejected(self):
        doc = card()
        doc["forecast"]["fixture"]["league"] = "en.2"
        self.add(doc)
        with self.assertRaises(ValueError):
            watch.build(DATE, self.root)

if __name__ == "__main__":
    unittest.main()
