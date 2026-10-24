"""Offline clock-provenance regression tests; no production HBT imports."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from hbt_source_kickoff_guard_v1 import check_row, local_to_utc, verified_utc


class SourceClockGuardTests(unittest.TestCase):
    def test_october_23_dutch_evening_clock_is_not_utc(self):
        self.assertEqual(local_to_utc('2026-10-23', '20:00', 'OPENFOOTBALL:nl.1'),
                         datetime(2026, 10, 23, 18, tzinfo=timezone.utc))

    def test_after_dutch_dst_rollover_offset_is_one_hour(self):
        self.assertEqual(local_to_utc('2026-10-25', '16:45', 'OPENFOOTBALL:nl.1'),
                         datetime(2026, 10, 25, 15, 45, tzinfo=timezone.utc))

    def test_ambiguous_dst_fall_back_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            local_to_utc('2026-10-25', '02:30', 'OPENFOOTBALL:nl.1')

    def test_nonexistent_dst_spring_forward_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'nonexistent'):
            local_to_utc('2026-03-29', '02:30', 'OPENFOOTBALL:nl.1')

    def test_other_league_requires_independent_zone_provenance(self):
        with self.assertRaisesRegex(ValueError, 'not audited'):
            local_to_utc('2026-10-23', '20:00', 'ESPN_ALL')

    def test_verified_utc_requires_explicit_offset_zero(self):
        for v in ('2026-10-23T18:00:00', '2026-10-23T20:00:00+02:00'):
            with self.subTest(v=v), self.assertRaisesRegex(ValueError, 'UTC'):
                verified_utc(v)

    def test_verified_source_and_utc_clock_agree(self):
        row = {'source':'OPENFOOTBALL:nl.1', 'date':'2026-10-23', 'localTime':'20:00',
               'verifiedKickoffUTC':'2026-10-23T18:00:00Z',
               'independentKickoffVerified':True,
               'independentKickoffSource':'https://www.skysports.com/football/go-ahead-eagles-vs-telstar/live/556771'}
        self.assertEqual(check_row(row)['status'], 'CLOCK_VERIFIED')

    def test_disagreeing_verified_clock_fails_closed(self):
        row = {'source':'OPENFOOTBALL:nl.1', 'date':'2026-10-23', 'localTime':'20:00',
               'verifiedKickoffUTC':'2026-10-23T20:00:00Z',
               'independentKickoffVerified':True,
               'independentKickoffSource':'https://www.skysports.com/football/go-ahead-eagles-vs-telstar/live/556771'}
        with self.assertRaisesRegex(ValueError, 'maps to'):
            check_row(row)

    def test_missing_independent_source_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'independent'):
            check_row({'source':'OPENFOOTBALL:nl.1','date':'2026-10-23','localTime':'20:00',
                       'verifiedKickoffUTC':'2026-10-23T18:00:00Z', 'independentKickoffVerified':True})


if __name__ == '__main__':
    unittest.main()
