from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_hkjc_feed.py"
SPEC = importlib.util.spec_from_file_location("feed", SCRIPT)
assert SPEC and SPEC.loader
feed = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(feed)


class FeedTests(unittest.TestCase):
    def test_had_no_vig(self):
        pools = [{
            "oddsType": "HAD",
            "inplay": False,
            "updateAt": "2026-09-26T02:00:00+08:00",
            "lines": [{
                "combinations": [
                    {"str": "H", "currentOdds": "2.00", "selections": []},
                    {"str": "D", "currentOdds": "4.00", "selections": []},
                    {"str": "A", "currentOdds": "4.00", "selections": []},
                ]
            }],
        }]
        out = feed.flatten_had(pools)
        self.assertEqual(out["odds"], {"home": 2.0, "draw": 4.0, "away": 4.0})
        self.assertAlmostEqual(sum(out["no_vig_prob"].values()), 1.0, places=7)
        self.assertAlmostEqual(out["no_vig_prob"]["home"], 0.5, places=7)

    def test_only_preevent_is_published(self):
        base = {
            "frontEndId": "FB1",
            "matchDate": "2026-09-26",
            "kickOffTime": "2026-09-26T03:00:00+08:00",
            "updateAt": "2026-09-26T02:00:00+08:00",
            "homeTeam": {"id": "h", "name_en": "Home", "name_ch": "主"},
            "awayTeam": {"id": "a", "name_en": "Away", "name_ch": "客"},
            "tournament": {"id": "t", "name_en": "Test", "name_ch": "測試"},
            "foPools": [],
        }
        matches = [
            dict(base, id="pre", status="PREEVENT"),
            dict(base, id="live", status="INPLAY"),
        ]
        out = feed.build_feed(matches, "2026-09-26", "2026-10-03", ["HAD"])
        self.assertEqual(out["match_count"], 1)
        self.assertEqual(out["matches"][0]["id"], "pre")
        feed.validate_feed(out)

    def test_sanitizer_drops_running_result_and_private_model_fields(self):
        match = {
            "id": "m1",
            "frontEndId": "FB2",
            "matchDate": "2026-09-26",
            "kickOffTime": "2026-09-26T04:00:00+08:00",
            "status": "PREEVENT",
            "updateAt": "2026-09-26T02:05:00+08:00",
            "homeTeam": {"id": "h", "name_en": "Home", "name_ch": "主"},
            "awayTeam": {"id": "a", "name_en": "Away", "name_ch": "客"},
            "tournament": {"id": "t", "name_en": "Test", "name_ch": "測試"},
            "runningResult": {"homeScore": 9, "awayScore": 9},
            "ggs": {"home": 0.99},
            "pps": {"pick": "HOME"},
            "foPools": [],
        }
        out = feed.sanitize_match(match, {"HAD"})
        self.assertNotIn("running_result", out)
        self.assertNotIn("runningResult", out)
        self.assertNotIn("ggs", out)
        self.assertNotIn("pps", out)

    def test_invalid_odds_are_not_published(self):
        self.assertIsNone(feed.decimal_odds("---"))
        self.assertIsNone(feed.decimal_odds("1.00"))
        self.assertEqual(feed.decimal_odds("1.23"), 1.23)


if __name__ == "__main__":
    unittest.main()
