"""HBT preview dashboard smoke and safety contracts."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hbt_build_market_first_preview_v1 as preview


class PreviewTests(unittest.TestCase):
    def test_self_contained_snapshot_and_controls(self):
        doc = {
            "targetDate": "2026-11-06", "summary": {},
            "fixtures": [], "unscoredFixtures": [], "chains": [],
            "readiness": "NO_EXECUTABLE_BETS",
            "quoteAudit": {"sourceStatus": "PRICE_SOURCE_UNCONFIGURED"},
        }
        html = preview.render_dashboard(doc)
        self.assertIn("Market-first betting desk", html)
        self.assertIn("Highest chance", html)
        self.assertIn("Best quoted EV", html)
        self.assertIn("shadow chains", html.lower())
        self.assertIn("NO_EXECUTABLE_BETS", html)
        self.assertIn("PRICE_SOURCE_UNCONFIGURED", html)
        self.assertNotIn("__HBT_SNAPSHOT_JSON__", html)

    def test_untrusted_fixture_strings_cannot_close_embedded_json_script(self):
        doc = {"fixture": "</script><script>alert('x')</script>&"}
        html = preview.render_dashboard(doc)
        self.assertNotIn("</script><script>", html)
        self.assertIn(r"\u003c/script\u003e", html)
        self.assertIn(r"\u0026", html)

    def test_missing_bookmaker_price_is_explicitly_not_zero(self):
        html = preview.render_dashboard({"fixtures": [], "unscoredFixtures": []})
        self.assertIn("Missing means unavailable, not zero", html)
        self.assertIn("m.observedOdds!=null", html)
        self.assertIn("nonnegative EV", html.lower() if "nonnegative EV" in html.lower() else html)


if __name__ == "__main__":
    unittest.main()
