"""Regression tests for research-only HBT betting controls (no frozen-model edits)."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import hbt_execution_surface_v1_3 as execution


def ready_row(**overrides):
    row = {
        "fixture": {"home": "Alpha", "away": "Beta", "date": "2026-10-10"},
        "tier": "A",
        "quality": 0.96,
        "coverage": "good",
        "predictionMode": "FULL_MODEL",
        "intelligenceOverlay": {"readinessState": "CONFIRMED_XI_READY", "intelligenceGaps": []},
        "derivedMarkets": {
            "HOME_WIN": {"p": 0.6, "family": "1X2"},
            "DRAW": {"p": 0.2, "family": "1X2"},
            "AWAY_WIN": {"p": 0.2, "family": "1X2"},
            "1X": {"p": 0.8, "family": "DOUBLE_CHANCE"},
            "X2": {"p": 0.4, "family": "DOUBLE_CHANCE"},
            "12": {"p": 0.8, "family": "DOUBLE_CHANCE"},
        },
    }
    row.update(overrides)
    return row


class BetExecutionGovernanceTests(unittest.TestCase):
    def tearDown(self):
        execution._PRICE_INDEX = {}
        execution._MARKET_AUDITS.clear()

    def test_pre_xi_never_funded_even_with_positive_ev(self):
        row = ready_row(intelligenceOverlay={"readinessState": "PRE_XI_PROVISIONAL", "intelligenceGaps": []})
        result = execution.classify_stake(row, 0.6, 1.90, True)
        self.assertEqual(result["stakeRand"], 0)
        self.assertIn("CONFIRMED_XI_NOT_READY", result["fundingBlockers"])

    def test_fallback_never_funded(self):
        row = ready_row(predictionMode="L0 FALLBACK")
        result = execution.classify_stake(row, 0.6, 1.90, True)
        self.assertEqual(result["stakeRand"], 0)
        self.assertIn("UNPROMOTED_L0_FALLBACK", result["fundingBlockers"])

    def test_stale_state_never_funded(self):
        result = execution.classify_stake(ready_row(coverage="stale-ish 1231d"), 0.6, 1.90, True)
        self.assertEqual(result["stakeRand"], 0)
        self.assertIn("STALE_TEAM_STATE", result["fundingBlockers"])

    def test_extreme_raw_ev_does_not_hide_valid_alternative(self):
        execution._PRICE_INDEX = {("alpha", "beta", "HOME_WIN"): 2.50,
                                  ("alpha", "beta", "X2"): 2.75}
        choice = execution.primary_market(ready_row())
        self.assertEqual(choice[0], "X2")
        audit = execution._MARKET_AUDITS[("alpha", "beta")]
        self.assertEqual(len(audit["allMarketAssessments"]), 6)
        self.assertEqual(audit["mostLikelyOutcome"]["market"], "HOME_WIN")
        self.assertEqual(audit["bestProvisionalValue"]["market"], "X2")

    def test_unconfigured_or_unattributable_price_is_not_usable(self):
        self.assertEqual(execution.price_index({"status": "PRICE_SOURCE_UNCONFIGURED"}), {})
        self.assertEqual(execution.price_index({"status": "PRICES_AVAILABLE",
             "generatedAt": "2026-10-10T08:59:00Z", "targetDate": "2026-10-10",
             "primaryBookmaker": "Betway", "prices": [{"home": "Alpha", "away": "Beta",
             "market": "HOME_WIN", "odds": 1.80}]}), {})

    def test_provenance_and_cross_event_price_mixing_are_rejected(self):
        now = datetime.now(timezone.utc).isoformat()
        document = {"status": "PRICES_AVAILABLE", "generatedAt": now,
                    "targetDate": "2026-10-10", "primaryBookmaker": "Betway",
                    "prices": [{"home": "Alpha", "away": "Beta", "market": "HOME_WIN",
                                "odds": 1.90, "eventId": "a", "bookmaker": "Betway"},
                               {"home": "Alpha", "away": "Beta", "market": "DRAW",
                                "odds": 3.50, "eventId": "b", "bookmaker": "Betway"}]}
        with patch.object(execution.base, "read", return_value={"targetDate": "2026-10-10"}):
            self.assertEqual(execution.price_index(document), {})
            document["prices"][1]["eventId"] = "a"
            result = execution.price_index(document)
        self.assertEqual(len(result), 2)

    def test_newer_frozen_export_blocks_old_prospective_card(self):
        row = ready_row()
        timing = {"verified": True, "kickoffUtc": "2026-10-10T18:00:00Z",
                  "source": "ESPN:en.1", "competition": "Premier League",
                  "fixtureSources": ["ESPN:en.1"], "leagueHint": "en.1"}
        refreshed = {"targetDate": "2026-10-10", "sourceExportedAt": "2026-10-10T06:29:07Z"}
        old_card = {"capturedAt": "2026-10-09T14:09:10Z"}
        with patch.object(execution.base, "read", side_effect=[refreshed, old_card]):
            reason = execution.governed_execution_identity_block(row, timing)
        self.assertEqual(reason, "PROSPECTIVE_CARD_BEHIND_NEWER_FROZEN_EXPORT")

    def test_no_independent_kickoff_proof_is_blocked(self):
        row = ready_row()
        timing = {"verified": True, "kickoffUtc": "2026-10-10T18:00:00Z",
                  "source": "ESPN:en.1", "competition": "Premier League",
                  "fixtureSources": ["ESPN:en.1"], "leagueHint": "en.1"}
        with patch.object(execution.base, "read", return_value={}):
            reason = execution.governed_execution_identity_block(row, timing)
        self.assertEqual(reason, "INDEPENDENT_KICKOFF_CONFIRMATION_MISSING")
        self.assertFalse(timing["independentKickoffVerified"])

    def test_disagreeing_official_kickoff_blocks(self):
        row = ready_row()
        timing = {"verified": True, "kickoffUtc": "2026-10-10T21:00:00Z",
                  "source": "ESPN:nl.1", "competition": "Eredivisie",
                  "fixtureSources": ["ESPN:nl.1"], "leagueHint": "nl.1"}
        proof = {"targetDate": "2026-10-10", "confirmations": [{
            "home": "Alpha", "away": "Beta", "kickoffUtc": "2026-10-10T19:00:00Z",
            "independentSource": "Club official", "sourceUrl": "https://example.org/fixture",
            "verifiedAt": "2026-10-10T11:00:00Z"}]}
        with patch.object(execution.base, "read", return_value=proof):
            reason = execution.governed_execution_identity_block(row, timing)
        self.assertEqual(reason, "KICKOFF_INDEPENDENT_SOURCE_DISAGREEMENT")
        self.assertFalse(timing["independentKickoffVerified"])


if __name__ == "__main__":
    unittest.main()
