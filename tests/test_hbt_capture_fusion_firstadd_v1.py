import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from hbt_capture_fusion_firstadd_v1 import capture

NOW = dt.datetime(2026, 10, 30, 15, 30, tzinfo=dt.timezone.utc)
DATE = '2026-10-30'

def forecast(time='17:00', mode='PRE-XI FUSION', probs=None):
    return {'fixture': {'date': DATE, 'time': time, 'league': 'en.1',
                        'home': 'Arsenal', 'away': 'Leeds United'},
            'status': 'RESEARCH_ONLY', 'predictionMode': mode,
            'probs': [.5, .3, .2] if probs is None else probs,
            'scoreMarkets': {'hda': [.5, .3, .2]},
            'diagnostics': {'preKickoff': True, 'performanceFeedCurrent': True,
                            'confirmedXi': mode == 'CONFIRMED-XI FUSION'}}

def shadow(predictions):
    return {'schemaVersion': 'HBT-RECOVERED-FUSION-SHADOW-1',
            'targetDate': DATE, 'generatedAt': '2026-10-30T15:29:00Z',
            'policy': {'retrainingPerformed': False, 'controlForecastUnchanged': True,
                       'executionAllowed': False},
            'deploymentCreated': '2026-09-12T11:15:44.195Z', 'predictions': predictions}

class FirstAddTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, doc):
        (self.root / f'hbt_recovered_fusion_shadow_{DATE}.json').write_text(json.dumps(doc))

    def test_first_add_is_immutable(self):
        self.write(shadow([forecast()]))
        self.assertEqual(capture(self.root, DATE, now=NOW)['firstAddWritten'], 1)
        path = next((self.root / 'captures' / 'fusion').glob('*.json'))
        first = path.read_bytes()
        self.write(shadow([forecast(probs=[.6, .2, .2])]))
        self.assertEqual(capture(self.root, DATE, now=NOW)['existingPreserved'], 1)
        self.assertEqual(first, path.read_bytes())

    def test_no_betting_or_clean_evidence_claimed(self):
        self.write(shadow([forecast()]))
        result = capture(self.root, DATE, now=NOW)
        self.assertEqual(result['fundedBetsCreated'], 0)
        self.assertEqual(result['cleanCalibrationObservationsCreated'], 0)
        path = next((self.root / 'captures' / 'fusion').glob('*.json'))
        self.assertFalse(json.loads(path.read_text())['policy']['cleanCalibrationEligible'])

    def test_past_kickoff_excluded(self):
        self.write(shadow([forecast(time='14:00')]))
        self.assertEqual(capture(self.root, DATE, now=NOW)['firstAddWritten'], 0)

    def test_invalid_probability_excluded(self):
        self.write(shadow([forecast(probs=[.7, .7, -.4])]))
        self.assertEqual(capture(self.root, DATE, now=NOW)['excluded'], 1)

    def test_future_source_clock_rejected(self):
        doc = shadow([forecast()]); doc['generatedAt'] = '2026-10-30T20:00:00Z'
        self.write(doc)
        with self.assertRaises(ValueError):
            capture(self.root, DATE, now=NOW)

    def test_stale_source_rejected(self):
        doc = shadow([forecast()]); doc['generatedAt'] = '2026-10-29T20:00:00Z'
        self.write(doc)
        with self.assertRaises(ValueError):
            capture(self.root, DATE, now=NOW)

    def test_pre_xi_and_confirmed_xi_separately_captured(self):
        self.write(shadow([forecast(), forecast(mode='CONFIRMED-XI FUSION')]))
        self.assertEqual(capture(self.root, DATE, now=NOW)['firstAddWritten'], 2)

if __name__ == '__main__':
    unittest.main()
