import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from hbt_watch_results_v1 import settle, enrich_final_event_counts
from unittest.mock import patch


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

    def test_abandoned_match_is_not_scored_as_a_draw_or_refund(self):
        obs = {**self.final, 'completed':False, 'regulationFinal':False, 'statusName':'STATUS_ABANDONED'}
        self.assertEqual(settle({'market':'DRAW'},obs), 'NO_REGULATION_RESULT')
        self.assertEqual(settle({'market':'HOME_DNB'},obs), 'NO_REGULATION_RESULT')

    def test_summary_stats_require_same_final_result_and_both_teams(self):
        obs = {**self.final,'eventId':'123','league':'es.1','home':'Home FC','away':'Away FC','kickoff':'2026-10-10T19:00Z'}
        teams = [{'team':{'displayName':name},'statistics':[{'name':'wonCorners','displayValue':value}]} for name,value in [('Home FC','4'),('Away FC','6')]]
        summary = {'header':{'id':'123','competitions':[{'date':obs['kickoff'],'status':{'type':{'completed':True},'period':2},'competitors':[
            {'homeAway':'home','score':'1','team':{'displayName':'Home FC'}}, {'homeAway':'away','score':'1','team':{'displayName':'Away FC'}}]}]},'boxscore':{'teams':teams}}
        with patch('hbt_watch_results_v1.common.http_json',return_value=summary):
            out = enrich_final_event_counts(obs)
            self.assertEqual(out['eventCounts']['CORNERS'],10)
            self.assertNotIn('YELLOW_CARDS',out['eventCounts'])
            self.assertEqual(settle({'market':'CORNERS_UNDER_8.5'},out),'LOSS')
        with patch('hbt_watch_results_v1.common.http_json',return_value=summary):
            out = enrich_final_event_counts({**obs,'homeScore':2})
            self.assertNotIn('eventCounts',out)
            self.assertEqual(out['eventStatsAudit']['status'],'UNVERIFIED')


if __name__ == '__main__':
    unittest.main()
