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
        self.assertIn("available_markets", out)
        self.assertIn("hkjc_all_odds_url", out)
        self.assertNotIn("markets", out)


    def test_last_seen_market_is_carried_as_stale_not_current(self):
        previous = {
            "frozen_at_hkt": "2026-09-26T02:30:00+08:00",
            "matches": [{
                "id": "m1",
                "had": {
                    "odds": {"home": 1.27, "draw": 5.5, "away": 9.0},
                    "updated_at": "2026-09-26T02:29:00+08:00",
                },
                "hdc": None,
                "hil": None,
            }],
        }
        current = {
            "frozen_at_hkt": "2026-09-26T02:50:00+08:00",
            "matches": [{
                "id": "m1",
                "had": {"odds": {}, "updated_at": None},
                "hdc": {"lines": [{"condition": "-1.0", "main": True, "odds": {"H": 1.8, "A": 1.9}}]},
                "hil": None,
            }],
        }
        out = feed.attach_last_seen_markets(current, previous)
        stale = out["matches"][0]["last_seen_markets"]["HAD"]
        self.assertEqual(stale["status"], "STALE_LAST_SEEN")
        self.assertEqual(stale["payload"]["odds"]["home"], 1.27)
        self.assertEqual(stale["age_minutes_at_freeze"], 20.0)
        self.assertNotIn("HDC", out["matches"][0]["last_seen_markets"])

    def test_last_seen_market_expires(self):
        previous = {
            "frozen_at_hkt": "2026-09-25T18:00:00+08:00",
            "matches": [{
                "id": "m1",
                "had": {"odds": {"home": 1.5, "draw": 4.0, "away": 6.0}},
                "hdc": None,
                "hil": None,
            }],
        }
        current = {
            "frozen_at_hkt": "2026-09-26T02:50:00+08:00",
            "matches": [{
                "id": "m1",
                "had": {"odds": {}, "updated_at": None},
                "hdc": None,
                "hil": None,
            }],
        }
        out = feed.attach_last_seen_markets(current, previous)
        self.assertNotIn("last_seen_markets", out["matches"][0])

    def test_invalid_odds_are_not_published(self):
        self.assertIsNone(feed.decimal_odds("---"))
        self.assertIsNone(feed.decimal_odds("1.00"))
        self.assertEqual(feed.decimal_odds("1.23"), 1.23)


if __name__ == "__main__":
    unittest.main()
