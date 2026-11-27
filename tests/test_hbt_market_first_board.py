"""Regression checks for HBT market-first research presentation only."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hbt_build_betting_desk_v1 as desk


def market(fixture, key, p, *, is_main, odds=None, ev=None, blocks=None):
    row = desk.make_market(key, "MAIN" if is_main else "EVENT", key, p,
                           mainMarket=is_main)
    row.update({
        "fixture": fixture,
        "observedOdds": odds,
        "expectedProfitPerRand": ev,
        "fundingBlockers": blocks or [],
        "stakeReady": False,
    })
    return row


def fixture(home, away, markets):
    return {
        "fixture": {"home": home, "away": away, "date": "2026-11-07"},
        "started": False,
        "identityBlocked": False,
        "markets": markets,
    }


class MarketFirstShadowChainTests(unittest.TestCase):
    def test_event_market_competes_for_highest_probability(self):
        a = {"home": "Team A", "away": "Team B"}
        c = {"home": "Team C", "away": "Team D"}
        rows = [
            fixture("Team A", "Team B", [
                market(a, "HOME_WIN", .65, is_main=True),
                market(a, "CORNERS_UNDER_13.5", .95, is_main=False),
            ]),
            fixture("Team C", "Team D", [
                market(c, "1X", .90, is_main=True),
            ]),
        ]
        chains = [x for x in desk.chain_candidates(rows)
                  if x["objective"] == "HIGH_PROBABILITY_WATCH"
                  and x["legCount"] == 2]
        self.assertEqual(len(chains), 1)
        self.assertEqual({leg["market"] for leg in chains[0]["legs"]},
                         {"CORNERS_UNDER_13.5", "1X"})
        self.assertFalse(chains[0]["stakeReady"])
        self.assertFalse(chains[0]["dependenceValidated"])

    def test_negative_value_or_unpriced_leg_is_visible_but_not_stake_ready(self):
        a = {"home": "Team A", "away": "Team B"}
        c = {"home": "Team C", "away": "Team D"}
        rows = [
            fixture("Team A", "Team B", [
                market(a, "1X", .92, is_main=True, odds=1.02, ev=-.0616,
                       blocks=["PRICE_BELOW_VALUE_GATE"]),
            ]),
            fixture("Team C", "Team D", [
                market(c, "BTTS_NO", .87, is_main=True, blocks=["CURRENT_BOOKMAKER_QUOTE_MISSING"]),
            ]),
        ]
        chains = [x for x in desk.chain_candidates(rows)
                  if x["objective"] == "HIGH_PROBABILITY_WATCH"]
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0]["legCount"], 2)
        self.assertIsNone(chains[0]["combinedOdds"])
        self.assertFalse(chains[0]["stakeReady"])
        self.assertIn("PRICE_BELOW_VALUE_GATE", chains[0]["fundingBlockers"])
        self.assertIn("CURRENT_BOOKMAKER_QUOTE_MISSING",
                      chains[0]["fundingBlockers"])

    def test_same_fixture_cannot_supply_two_legs(self):
        a = {"home": "Team A", "away": "Team B"}
        rows = [fixture("Team A", "Team B", [
            market(a, "1X", .93, is_main=True),
            market(a, "TOTAL_GOALS_UNDER_4.5", .96, is_main=False),
        ])]
        self.assertEqual(desk.chain_candidates(rows), [])


if __name__ == "__main__":
    unittest.main()
