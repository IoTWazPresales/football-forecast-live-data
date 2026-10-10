import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from hbt_watch_results_v1 import settle


class ResultSettlementTests(unittest.TestCase):
    def setUp(self):
        self.final = dict(completed=True, identityVerified=True,
                          regulationFinal=True, homeScore=1, awayScore=1)

    def test_draw_refunds_dnb_but_loses_outright(self):
        self.assertEqual(settle({'market': 'HOME_DNB'}, self.final), 'REFUND')
        self.assertEqual(settle({'market': 'AWAY_DNB'}, self.final), 'REFUND')
        self.assertEqual(settle({'market': 'HOME_WIN'}, self.final), 'LOSS')
        self.assertEqual(settle({'market': 'DRAW'}, self.final), 'WIN')

    def test_goals_and_btts_use_both_final_scores(self):
        for market, result in [('TOTAL_GOALS_OVER_1.5','WIN'), ('TOTAL_GOALS_UNDER_2.5','WIN'),
                               ('BTTS_YES','WIN'), ('BTTS_NO','LOSS')]:
            self.assertEqual(settle({'market': market}, self.final), result)

    def test_live_identity_and_extra_time_do_not_settle(self):
        self.assertEqual(settle({'market':'DRAW'}, {**self.final,'completed':False}), 'PENDING')
        self.assertEqual(settle({'market':'DRAW'}, {**self.final,'identityVerified':False}), 'PENDING')
        self.assertEqual(settle({'market':'DRAW'}, {**self.final,'regulationFinal':False}), 'UNVERIFIED_PERIOD')

    def test_missing_event_stats_are_not_zero(self):
        self.assertEqual(settle({'market':'CORNERS_UNDER_8.5'}, self.final), 'MISSING_EVENT_STATS')
        self.assertEqual(settle({'market':'CORNERS_UNDER_8.5'}, {**self.final,'eventCounts':{'CORNERS':10}}), 'LOSS')


if __name__ == '__main__':
    unittest.main()
