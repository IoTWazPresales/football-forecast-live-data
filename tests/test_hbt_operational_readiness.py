"""Point-in-time official proofs, cross-date isolation and publication races."""
from datetime import datetime, timezone
import hashlib
import json
import os
import io
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import hbt_collect_independent_kickoffs_v1 as official
import hbt_execution_surface_v1_3 as execution
import hbt_build_betting_desk_v1 as desk
import hbt_publish_research_outputs as publisher
import hbt_scan_slate_v2 as scanner
import hbt_scan_slate_v2_1 as source
import hbt_capture_store as capture_store
import hbt_build_prospective_from_frozen as capture_builder
import hbt_forensic_learning_v2 as forensic


class OfficialProofTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 10, 17, tzinfo=timezone.utc)
        self.fx = {'date': '2026-10-10', 'home': 'Ajax', 'away': 'NEC'}
        self.timing = {'kickoffUtc': '2026-10-10T19:00:00Z', 'source': 'ESPN:nl.1'}
        self.row = dict(self.fx, kickoffUtc=self.timing['kickoffUtc'], independentSource='Ajax official',
                        sourceUrl='https://www.ajax.nl/wedstrijden/', verifiedAt='2026-10-10T16:59:00Z')

    def check(self, row):
        return execution.independent_kickoff_block(self.fx, self.timing, {'targetDate': self.fx['date'], 'confirmations': [row]}, self.now)

    def test_valid_official_proof_and_future_clock(self):
        self.assertIsNone(self.check(self.row))
        self.assertTrue(self.timing['independentKickoffVerified'])
        self.assertEqual(self.check(dict(self.row, verifiedAt='2026-10-10T17:01:00Z')), 'KICKOFF_PROOF_CLOCK_IN_FUTURE')

    def test_label_cannot_disguise_same_provider(self):
        self.assertEqual(self.check(dict(self.row, sourceUrl='https://www.espn.com/soccer/fixture')),
                         'INDEPENDENT_KICKOFF_CONFIRMATION_MISSING_OR_AMBIGUOUS')
        self.assertEqual(self.check(dict(self.row, sourceUrl='https://[broken')),
                         'INDEPENDENT_KICKOFF_CONFIRMATION_MISSING_OR_AMBIGUOUS')

    def test_conflicting_and_post_start_evidence_block(self):
        self.assertEqual(self.check(dict(self.row, kickoffUtc='2026-10-10T21:00:00Z')), 'KICKOFF_INDEPENDENT_SOURCE_DISAGREEMENT')
        reason = execution.independent_kickoff_block(self.fx, self.timing,
            {'targetDate': self.fx['date'], 'confirmations': [dict(self.row, verifiedAt='2026-10-10T19:01:00Z')]},
            datetime(2026, 10, 10, 20, tzinfo=timezone.utc))
        self.assertEqual(reason, 'KICKOFF_PROOF_CAPTURED_AFTER_START')

    def test_dutch_local_time_converted_once_and_duplicates_collapsed(self):
        block = '<li class="matches-block__match"><span class="matches-block__date">za. 10 oktober 2026 21:00</span><span class="matches-block__participants">Ajax <span>-</span> NEC</span></li>'
        rows = official.parse_ajax(block * 2, '2026-10-10')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['kickoffUtc'], '2026-10-10T19:00:00Z')
        self.assertEqual(official.parse_ajax(block, '2026-10-11'), [])

    def test_archived_madrid_announcement_not_reused_next_year(self):
        body = '<script type="application/ld+json">' + json.dumps({'@type': 'NewsArticle',
            'datePublished': '2026-09-10T10:00:00Z',
            'headline': 'The Real Madrid-Villarreal game will take place on Saturday, October 10, at 9:00 pm CEST'}) + '</script>'
        self.assertEqual(official.parse_madrid(body, '2026-10-10')[0]['kickoffUtc'], '2026-10-10T19:00:00Z')
        self.assertEqual(official.parse_madrid(body, '2027-10-10'), [])

    def test_runner_timezone_never_assigned_to_unknown_timestamp(self):
        self.assertEqual(scanner.iso_kickoff('2026-10-10T21:00:00'), '2026-10-10T21:00:00')
        self.assertEqual(scanner.key('Ajax Amsterdam'), scanner.key('AFC Ajax'))
        self.assertEqual(scanner.key('NEC Nijmegen'), scanner.key('NEC'))

    def test_provider_display_aliases_do_not_cross_competition_domains(self):
        self.assertEqual(source.model_display_name('Ajax Amsterdam', 'nl.1'), 'AFC Ajax')
        self.assertEqual(source.model_display_name('NEC Nijmegen', 'nl.1'), 'NEC')
        self.assertEqual(source.model_display_name('Ajax Amsterdam', 'women'), 'Ajax Amsterdam')

    def test_historical_forecast_wrong_kickoff_is_blocked(self):
        row = {'fixture': dict(self.fx, time='21:00')}
        timing = dict(self.timing, verified=True)
        self.assertEqual(execution.base.execution_identity_block(row, timing), 'FORECAST_KICKOFF_DISAGREEMENT')

    def test_future_global_scanner_does_not_replace_todays_saved_feed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in [('slate_scanner.json', {'targetDate': '2026-10-12'}),
                               ('slate_scanner_2026-10-10.json', {'targetDate': '2026-10-10', 'rankingGate': {'discoveryComplete': True}})]:
                (root / name).write_text(json.dumps(data))
            output = desk.build('2026-10-10', root, self.now)
            self.assertNotIn('SCANNER_TARGET_MISMATCH', output['globalBlockers'])
            self.assertEqual(output['sourceFiles']['scanner'], 'slate_scanner_2026-10-10.json')


class CaptureTests(unittest.TestCase):
    def test_refreshed_versions_preserve_original_and_detect_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = '2100-10-10'
            old = root / f'hbt_prospective_card_{target}.json'
            old.write_text('{"original":"retain these exact bytes"}')
            frozen = {'targetDate': target, 'bridge': {'goldenMaxAbsError': 0}, 'predictions': [
                {'fixture': {'date': target, 'time': '22:00', 'league': 'en.1', 'home': 'Alpha', 'away': 'Beta'},
                 'probs': [.6, .25, .15], 'predictionMode': 'L0 FALLBACK'}]}
            (root / f'frozen_control_forecast_{target}.json').write_text(json.dumps(frozen))
            with redirect_stdout(io.StringIO()), patch.object(capture_builder, 'ROOT', root), patch.object(sys, 'argv', ['capture', '--date', target, '--refresh']):
                capture_builder.main(); first = capture_store.capture_path(root, target)
                capture_builder.main(); second = capture_store.capture_path(root, target)
            self.assertNotEqual(first, second)
            self.assertTrue(first.exists())
            self.assertEqual(old.read_text(), '{"original":"retain these exact bytes"}')
            second.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                capture_store.capture_path(root, target)

    def test_capture_pointer_cannot_escape_hbt_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'hbt_current_capture_2026-10-10.json').write_text(json.dumps(
                {'targetDate': '2026-10-10', 'path': '../some-other-project.json'}))
            with self.assertRaisesRegex(ValueError, 'invalid current capture pointer'):
                capture_store.capture_path(root, '2026-10-10')

    def test_refresh_surface_cannot_make_older_capture_clean_learning(self):
        doc = {'capturedAt': '2026-10-10T16:00:00Z', 'policy': {'preMatchCaptureImmutable': True,
               'bookmakerPriceObservedBeforeCapture': False, 'bookmakerOddsUsedAsPredictiveFeature': False}}
        surface = {'predictionFrozenAt': '2026-10-10T17:00:00Z', 'kickoffVerification': {
            'verified': True, 'independentKickoffVerified': True, 'kickoffUtc': '2026-10-10T19:00:00Z'}}
        self.assertEqual(forensic.clean_capture_guard({'statusAtCapture': 'PRE_KICKOFF'}, doc, surface),
                         'SURFACE_BELONGS_TO_DIFFERENT_FORECAST_CAPTURE')
        surface['predictionFrozenAt'] = doc['capturedAt']
        self.assertIsNone(forensic.clean_capture_guard({'statusAtCapture': 'PRE_KICKOFF'}, doc, surface))


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.previous = Path.cwd()
        self.remote = self.root / 'remote.git'
        self.a = self.root / 'a'; self.b = self.root / 'b'
        self.g(self.root, 'init', '--bare', str(self.remote))
        self.g(self.root, 'clone', str(self.remote), str(self.a))
        self.configure(self.a)
        self.g(self.a, 'checkout', '-b', publisher.BRANCH)
        (self.a / 'hbt_live_data').mkdir()
        (self.a / 'hbt_live_data/feed.json').write_text('{}')
        (self.a / 'hbt_live_data/hbt_prospective_card_2026-10-10.json').write_text('{}')
        self.g(self.a, 'add', '.'); self.g(self.a, 'commit', '-m', 'seed')
        self.g(self.a, 'push', '-u', 'origin', publisher.BRANCH)
        self.g(self.root, 'clone', '--branch', publisher.BRANCH, str(self.remote), str(self.b))
        self.configure(self.b)
        os.chdir(self.a)

    @staticmethod
    def g(cwd, *args):
        return subprocess.check_output(['git', *args], cwd=cwd, text=True, stderr=subprocess.PIPE).strip()

    def configure(self, cwd):
        self.g(cwd, 'config', 'user.name', 'HBT test'); self.g(cwd, 'config', 'user.email', 'hbt@example.invalid')

    def tearDown(self):
        os.chdir(self.previous); self.temp.cleanup()

    def advance(self, name, body):
        (self.b / name).write_text(body)
        self.g(self.b, 'add', name); self.g(self.b, 'commit', '-m', 'concurrent')
        self.g(self.b, 'push', 'origin', publisher.BRANCH)
        return self.g(self.b, 'rev-parse', 'HEAD')

    def stage(self, name, body):
        (self.a / name).write_text(body); self.g(self.a, 'add', name)

    def test_disjoint_branch_advance_publishes_without_losing_runner_work(self):
        self.advance('README.md', 'upstream documentation')
        self.stage('hbt_live_data/feed.json', '{"new":true}')
        (self.a / 'untracked-evidence.txt').write_text('retain')
        sha = publisher.publish('generated evidence')
        self.assertEqual(self.g(self.remote, 'rev-parse', publisher.BRANCH), sha)
        self.assertEqual((self.a / 'untracked-evidence.txt').read_text(), 'retain')
        self.assertEqual(self.g(self.remote, 'show', sha + ':README.md'), 'upstream documentation')

    def test_overlapping_generated_output_never_overwrites_newer_evidence(self):
        sha = self.advance('hbt_live_data/feed.json', '{"remote":true}')
        self.stage('hbt_live_data/feed.json', '{"local":true}')
        with self.assertRaisesRegex(ValueError, 'concurrent HBT output changed'):
            publisher.publish('must not overwrite')
        self.assertEqual(self.g(self.remote, 'rev-parse', publisher.BRANCH), sha)
        self.assertEqual((self.a / 'hbt_live_data/feed.json').read_text(), '{"local":true}')

    def test_parameter_and_existing_capture_changes_are_rejected(self):
        self.stage('hbt_live_data/event_model_params.json', '{}')
        with self.assertRaisesRegex(ValueError, 'generated HBT output only'):
            publisher.publish('no auto promotion')
        self.g(self.a, 'reset', 'HEAD', 'hbt_live_data/event_model_params.json')
        self.stage('hbt_live_data/hbt_prospective_card_2026-10-10.json', '{"rewrite":true}')
        with self.assertRaisesRegex(ValueError, 'immutable prospective capture'):
            publisher.publish('no backfill')

    def test_disjoint_source_change_cannot_publish_incoherent_desk(self):
        sha = self.advance('hbt_live_data/feed.json', '{"remote":true}')
        d = {'sourceFiles': {'scanner': 'feed.json'}, 'sourceHashes': {'scanner': hashlib.sha256(b'{}').hexdigest()}}
        self.stage('hbt_live_data/hbt_betting_desk_2026-10-10.json', json.dumps(d))
        with self.assertRaisesRegex(ValueError, 'desk input changed during publication'):
            publisher.publish('wrong provenance')
        self.assertEqual(self.g(self.remote, 'rev-parse', publisher.BRANCH), sha)


if __name__ == '__main__':
    unittest.main()
