"""HBT publication guard: no silently partial green builds."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hbt_stage_prospective_evidence as staging

DAY = "2026-10-31"

def jwrite(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")

class StagingEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "hbt_live_data"
        self.data.mkdir()
        for name in staging.mandatory_names(DAY):
            path = self.data / name
            if name.endswith(".json"):
                jwrite(path, {"targetDate": DAY})
            else:
                path.write_text("HBT original research only\n")
        self.original = self.data / "captures" / f"hbt_prospective_card_{DAY}_capture.json"
        jwrite(self.original, {"targetDate": DAY, "policy": {"preMatchCaptureImmutable": True}})
        jwrite(self.data / f"hbt_current_capture_{DAY}.json", {
            "targetDate": DAY,
            "path": f"captures/{self.original.name}",
            "sha256": staging.sha(self.original),
        })
        frozen = self.data / f"frozen_control_forecast_{DAY}.json"
        jwrite(self.data / f"hbt_recovered_fusion_shadow_{DAY}.json", {
            "targetDate": DAY,
            "sourceHashes": {"control": staging.sha(frozen)},
            "policy": {"controlForecastUnchanged": True},
        })
        jwrite(self.data / f"hbt_firstadd_market_watch_{DAY}.json", {
            "targetDate": DAY, "policy": {"noBettingEligibility": True},
        })
        jwrite(self.data / f"hbt_coverage_triage_{DAY}.json", {
            "targetDate": DAY, "policy": {"createsBettingEligibility": False},
        })
        jwrite(self.data / f"hbt_bet_list_{DAY}.json", {
            "targetDate": DAY,
            "deskSha256": staging.sha(self.data / f"hbt_betting_desk_{DAY}.json"),
            "sourceHashes": {
                "forecast": staging.sha(frozen),
                "recoveredFusion": staging.sha(self.data / f"hbt_recovered_fusion_shadow_{DAY}.json"),
            },
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_date_needs_hashed_pointer_not_missing_root_original(self):
        self.assertFalse((self.data / f"hbt_prospective_card_{DAY}.json").exists())
        mandatory = staging.validate_date(self.data, DAY)
        self.assertEqual(len(mandatory), len(staging.mandatory_names(DAY)))

    def test_missing_full_desk_blocks_staging(self):
        (self.data / f"hbt_betting_desk_{DAY}.json").unlink()
        with self.assertRaisesRegex(ValueError, "HBT evidence missing"):
            staging.validate_date(self.data, DAY)

    def test_frozen_control_sha_mismatch_blocks(self):
        jwrite(self.data / f"frozen_control_forecast_{DAY}.json", {"targetDate":DAY, "changed":True})
        with self.assertRaisesRegex(ValueError, "lineage mismatch"):
            staging.validate_date(self.data, DAY)

    def test_shadow_control_mismatch_blocks(self):
        shadow=self.data / f"hbt_recovered_fusion_shadow_{DAY}.json"
        jwrite(shadow, {"targetDate":DAY,"policy":{"controlForecastUnchanged":True},"sourceHashes":{"control":"broken"}})
        bet=self.data / f"hbt_bet_list_{DAY}.json"
        obj=json.loads(bet.read_text())
        obj["sourceHashes"]["recoveredFusion"]=staging.sha(shadow)
        jwrite(bet,obj)
        with self.assertRaisesRegex(ValueError, "Fusion shadow references"):
            staging.validate_date(self.data, DAY)

    def test_hbt_market_research_must_remain_unfunded(self):
        jwrite(self.data / f"hbt_firstadd_market_watch_{DAY}.json", {
            "targetDate":DAY,"policy":{"noBettingEligibility":False},
        })
        with self.assertRaisesRegex(ValueError, "unexpectedly authorizes a bet"):
            staging.validate_date(self.data, DAY)

    def test_immutable_capture_integrity(self):
        self.original.write_text(self.original.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            staging.validate_date(self.data, DAY)


if __name__ == "__main__":
    unittest.main()
