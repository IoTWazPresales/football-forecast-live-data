"""Research manifest invariants; does not independently fetch match sources."""
import json
import unittest
from datetime import datetime
from pathlib import Path
DATA=json.loads((Path(__file__).resolve().parents[1]/'docs/evidence/hbt_2026_10_31_settlement_manifest.json').read_text(encoding='utf-8'))
def utc(s):
    if not isinstance(s,str) or not s.endswith('Z'): raise ValueError('explicit UTC required')
    return datetime.fromisoformat(s.replace('Z','+00:00'))
class EvidenceManifestTests(unittest.TestCase):
    def test_fixed_scope(self):
        self.assertEqual(DATA['targetDate'],'2026-10-31')
        self.assertEqual(DATA['frozenVersion'],'HBT-1.1.2L-R1')
        self.assertEqual(DATA['authorityBranch'],'research/hbt-1.4-match-intelligence')
    def test_no_false_clean_or_roi_claim(self):
        self.assertFalse(DATA['cleanCalibrationEligible'])
        self.assertFalse(DATA['contemporaneousVerifiedBookmakerPrices'])
    def test_original_forecast_coverage(self):
        self.assertEqual(len(DATA['records']),20)
        self.assertEqual(sum(r['status']=='FT_90' for r in DATA['records']),19)
        self.assertEqual(sum(r['status']=='POSTPONED' for r in DATA['records']),1)
        self.assertEqual(sum(r['fusionP1'] is not None for r in DATA['records']),13)
    def test_no_duplicate_fixtures(self):
        keys=[(r['fixture']['date'],r['fixture']['league'],r['fixture']['home'].casefold(),r['fixture']['away'].casefold()) for r in DATA['records']]
        self.assertEqual(len(keys),len(set(keys)))
    def test_senior_men_only(self):
        self.assertEqual(DATA['category'],'senior_men')
        self.assertTrue(all(r['category']=='senior_men' for r in DATA['records']))
    def test_cited_independent_results_and_kickoffs(self):
        for r in DATA['records']:
            self.assertTrue(r['resultEvidenceUrl'].startswith('https://'))
            if r['status']=='FT_90':
                self.assertTrue(r['regulationTimeVerified'])
                self.assertTrue(r['kickoffEvidenceUrl'].startswith('https://'))
                self.assertEqual(len(r['result']),2)
                self.assertTrue(all(type(n) is int and n>=0 for n in r['result']))
                utc(r['kickoffUtc'])
            else:
                self.assertIsNone(r['result'])
                self.assertIsNone(r['kickoffUtc'])
                self.assertFalse(r['regulationTimeVerified'])
    def test_immutable_p1_committed_before_kickoff(self):
        first=utc(DATA['fusionFirstAdd']['committedAtUtc'])
        for r in DATA['records']:
            if r['fusionP1']:
                self.assertLess(first,utc(r['kickoffUtc']))
                self.assertEqual(len(r['fusionP1']['gitBlobSha']),40)
                self.assertTrue(r['fusionP1']['path'].endswith('_P1.json'))
    def test_l0_firstadd_before_all_settled_kickoffs(self):
        first=utc(DATA['l0FirstAdd']['committedAtUtc'])
        self.assertEqual(len(DATA['l0FirstAdd']['gitBlobSha']),40)
        self.assertTrue(all(first<utc(r['kickoffUtc']) for r in DATA['records'] if r['status']=='FT_90'))
    def test_dutch_clock_discrepancy_attested(self):
        psv=next(r for r in DATA['records'] if r['fixture']['home']=='PSV')
        self.assertEqual(psv['kickoffUtc'],'2026-10-31T17:45:00Z')
        self.assertIn('18:45',psv['sourceKickoffClockMismatch'])
    def test_postponed_fixture_not_scored(self):
        pp=[r for r in DATA['records'] if r['status']=='POSTPONED']
        self.assertEqual([(r['fixture']['home'],r['fixture']['away']) for r in pp],[('Dundee United','Heart of Midlothian')])
        self.assertIsNone(pp[0]['fusionP1'])
if __name__=='__main__': unittest.main()
