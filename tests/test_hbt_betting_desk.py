"""Financial/causal regression tests with synthetic fixtures and quoted markets."""
import copy
import math
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hbt_build_betting_desk_v1 as desk
import hbt_collect_market_prices_v1 as collector
import hbt_scan_slate_v2 as scanner
import hbt_train_event_models_v4 as trainer
import hbt_forensic_learning_v1 as settlement
import hbt_forensic_learning_v2 as forensic


class DeskTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 10, 14, tzinfo=timezone.utc)
        self.fixture = {"date": "2026-10-10", "home": "Alpha", "away": "Beta", "league": "en.1"}
        self.pred = {"fixture": self.fixture, "probs": [.6, .25, .15], "tier": "A", "predictionMode": "L0 FALLBACK"}
        self.quote = {"home": "Alpha", "away": "Beta", "market": "HOME_WIN", "odds": 1.90,
            "eventId": "e1", "bookmaker": "Betway", "period": "REGULATION_90",
            "collectedAt": "2026-10-10T13:59:00Z", "retrievedAt": "2026-10-10T14:00:00Z",
            "providerKickoff": "2026-10-10T18:00:00Z"}
        self.doc = {"status": "PRICES_AVAILABLE", "targetDate": "2026-10-10", "primaryBookmaker": "Betway",
                    "generatedAt": "2026-10-10T14:00:00Z", "prices": [self.quote]}

    def test_every_main_outcome_and_both_dnb_are_shown(self):
        markets = desk.forecast_markets(self.pred)
        self.assertEqual({m["market"] for m in markets}, set(desk.MAIN_KEYS))
        home = next(m for m in markets if m["market"] == "HOME_DNB")
        self.assertAlmostEqual(home["fairOdds"], 1.25)
        self.assertAlmostEqual(home["profitProbability"], .6)
        self.assertAlmostEqual(home["nonLossProbability"], .85)

    def test_dnb_zero_draw_is_supported(self):
        self.pred["probs"] = [.6, 0, .4]
        self.assertEqual(len(desk.forecast_markets(self.pred)), 8)

    def test_goal_probabilities_are_not_inferred_from_1x2(self):
        self.assertFalse(any(m["family"] == "BTTS" for m in desk.forecast_markets(self.pred)))
        self.pred["scoreMarkets"] = {"bttsYes": .55, "bttsNo": .45, "over25": .52}
        self.assertEqual(len(desk.forecast_markets(self.pred)), 11)

    def test_invalid_nan_and_non_normalized_predictions_rejected(self):
        for probs in ([math.nan, .3, .7], [True, 0, 0], [.6, .3, .2]):
            self.pred["probs"] = probs
            self.assertEqual(desk.forecast_markets(self.pred), [])

    def test_quote_freshness_uses_each_provider_market_time(self):
        self.doc["prices"][0]["collectedAt"] = "2026-10-10T12:00:00Z"
        result, audit = desk.quote_index(self.doc, "2026-10-10", self.now)
        self.assertEqual(result, {})
        self.assertEqual(audit["accepted"], 0)

    def test_wrong_period_and_cross_event_mix_rejected(self):
        altered = copy.deepcopy(self.quote)
        altered.update({"market": "DRAW", "eventId": "e2"})
        self.doc["prices"].append(altered)
        self.assertEqual(desk.quote_index(self.doc, "2026-10-10", self.now)[0], {})
        self.doc["prices"] = [dict(self.quote, period="FIRST_HALF")]
        self.assertEqual(desk.quote_index(self.doc, "2026-10-10", self.now)[0], {})

    def test_conflicting_quotes_not_silently_last_row_wins(self):
        self.doc["prices"].append(dict(self.quote, odds=2.05))
        self.assertEqual(desk.quote_index(self.doc, "2026-10-10", self.now)[0], {})

    def test_draw_refund_ev_and_minimum_price_are_unconditional(self):
        m = next(m for m in desk.forecast_markets(self.pred) if m["market"] == "HOME_DNB")
        q = dict(self.quote, market="HOME_DNB", odds=1.30)
        timing = {"kickoffUtc": q["providerKickoff"]}
        result = desk.assess_market(m, self.pred, timing, [], {("alpha", "beta", "HOME_DNB"): q}, self.now - timedelta(hours=1))
        self.assertAlmostEqual(result["expectedProfitPerRand"], .03)
        self.assertAlmostEqual(result["minimumOddsForValueGate"], 1.3)

    def test_positive_ev_does_not_override_readiness(self):
        m = desk.forecast_markets(self.pred)[0]
        result = desk.assess_market(m, self.pred, {"kickoffUtc": self.quote["providerKickoff"]},
            ["UNPROMOTED_L0_FALLBACK"], {("alpha", "beta", "HOME_WIN"): self.quote}, self.now - timedelta(hours=1))
        self.assertTrue(result["valuePositive"])
        self.assertFalse(result["stakeReady"])

    def test_quoted_before_observation_of_freeze_is_rejected(self):
        m = desk.forecast_markets(self.pred)[0]
        result = desk.assess_market(m, self.pred, {}, [], {("alpha", "beta", "HOME_WIN"): self.quote}, self.now)
        self.assertIn("QUOTE_NOT_AFTER_PREDICTION_FREEZE", result["fundingBlockers"])

    def test_chains_have_frechet_bounds_no_repeated_fixture_and_no_funding(self):
        fixtures = []
        for i in range(3):
            m = desk.make_market("1X", "DOUBLE_CHANCE", "A or draw", .9, mainMarket=True)
            m.update({"fixture": {"home": f"A{i}", "away": f"B{i}"}, "observedOdds": None,
                      "stakeReady": False, "fundingBlockers": ["CURRENT_BOOKMAKER_QUOTE_MISSING"]})
            fixtures.append({"markets": [m]})
        chains = desk.chain_candidates(fixtures)
        c = next(c for c in chains if c["legCount"] == 3)
        self.assertAlmostEqual(c["jointProbabilityIndependenceApprox"], .729)
        self.assertAlmostEqual(c["jointProbabilityBounds"]["lower"], .7)
        self.assertAlmostEqual(c["jointProbabilityBounds"]["upper"], .9)
        self.assertFalse(c["stakeReady"])
        self.assertEqual(len({x["fixture"]["home"] for x in c["legs"]}), 3)

    def test_unvalidated_event_lines_are_not_generated(self):
        params = {"version": "v", "models": {"corners": {"promotionEvidence": {"holdoutNLLDelta": -.05},
                   "holdout": {"lines": {"9.5": {"n": 100, "binaryLogloss": .6}}}}}}
        intel = {"eventMarkets": {"corners": {"validatedMarketModel": True, "calibrationVersion": "v", "totalLambda": 10,
            "history": {k: 5 for k in ("homeForN", "homeAgainstN", "awayForN", "awayAgainstN")}}}}
        ms = desk.event_markets(intel, params)
        self.assertEqual({m["market"] for m in ms}, {"CORNERS_OVER_9.5", "CORNERS_UNDER_9.5"})
        self.assertAlmostEqual(sum(m["winProbability"] for m in ms), 1)

    def test_price_normalizer_retains_update_time_and_ignores_half_and_asian_lines(self):
        raw = [{"name": "ML", "updatedAt": "2026-10-10T13:00:00Z", "odds": [{"home": "1.9", "draw": "3", "away": "4"}]},
               {"name": "Totals HT", "updatedAt": "2026-10-10T13:00:00Z", "odds": [{"hdp": 1.5, "over": 2}]},
               {"name": "Totals", "updatedAt": "2026-10-10T13:00:00Z", "odds": [{"hdp": 2.25, "over": 2}]}]
        rows = collector.normalize_markets(raw, "A", "B", "e", "2026-10-10T18:00:00Z", "2026-10-10T14:00:00Z")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["collectedAt"], "2026-10-10T13:00:00Z")
        self.assertEqual(rows[0]["retrievedAt"], "2026-10-10T14:00:00Z")

    def test_missing_forecast_in_supported_league_is_not_unsupported(self):
        for league, status in (("en.1", "INSUFFICIENT_DATA"), ("nl.1", "NOT_YET_READY")):
            row = scanner.classify({"leagueHint": league, "home": "A", "away": "B"}, None, None, {})
            self.assertEqual(row["hbtSupportLevel"], status)
            self.assertIsNone(row["probabilityOutput"])

    def test_first_target_cannot_supply_own_training_prior(self):
        rows = [{"date": "2026-01-01", "season": 2026, "league": "en.1", "home": "A", "away": "B", "corners": (9, 2)}]
        self.assertEqual(trainer.replay(rows, "corners", (.9, 2, .5), {2026})["n"], 0)

    def test_draw_and_dnb_settlement_uses_canonical_market_keys(self):
        for key, scores, expected in [("DRAW", (1, 1), "WIN"), ("DRAW", (2, 1), "LOSS"),
                                     ("HOME_DNB", (1, 1), "VOID"), ("AWAY_DNB", (0, 2), "WIN"),
                                     ("BTTS_NO", (0, 2), "WIN"), ("TOTAL_GOALS_OVER_2.5", (2, 1), "WIN")]:
            self.assertEqual(settlement.settle_market({"market": key}, *scores), expected)

    def test_missing_surface_or_independent_time_is_not_clean_learning(self):
        self.assertEqual(forensic.clean_capture_guard({}, {}, None), "EXECUTION_SURFACE_MISSING")
        self.assertEqual(forensic.clean_capture_guard({}, {}, {"kickoffVerification": {"verified": True}}),
                         "INDEPENDENT_PREMATCH_IDENTITY_AND_TIME_UNPROVEN")


if __name__ == "__main__":
    unittest.main()
