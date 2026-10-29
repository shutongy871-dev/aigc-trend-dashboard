import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from builder_feed import normalize_feed, refresh
from render_dashboard import build_html


NOW = datetime(2026, 10, 29, 8, tzinfo=timezone.utc)


def source():
    return {
        "generatedAt": "2026-10-29T06:32:19Z", "lookbackHours": 24,
        "x": [{
            "name": "Example Builder", "handle": "builder", "bio": "Product &amp; engineering",
            "tweets": [{
                "id": "123", "text": "A product observation.\n" + "Evidence matters. " * 10,
                "createdAt": "2026-10-29T01:00:00Z",
                "url": "https://x.com/builder/status/123",
                "likes": 10, "retweets": 2, "replies": 3, "isQuote": False,
            }],
        }],
    }


class BuilderFeedTests(unittest.TestCase):
    def test_preserves_text_deduplicates_and_uses_source_metrics(self):
        raw = source()
        raw["x"][0]["tweets"].append(copy.deepcopy(raw["x"][0]["tweets"][0]))
        result = normalize_feed(raw, NOW)
        self.assertEqual(len(result["posts"]), 1)
        post = result["posts"][0]
        self.assertEqual(post["text"], raw["x"][0]["tweets"][0]["text"])
        self.assertEqual(post["bio"], "Product & engineering")
        self.assertEqual(post["likes"], 10)
        self.assertFalse(post["short_context"])
        self.assertEqual(result["generated_at"], "2026-10-29T06:32:19+00:00")

    def test_rejects_unsafe_or_mismatched_links_and_missing_dates(self):
        for url in ["javascript:alert(1)", "https://evil.test/builder/status/123",
                    "https://x.com/other/status/123", "https://x.com/builder/status/456"]:
            raw = source()
            raw["x"][0]["tweets"][0]["url"] = url
            with self.assertRaises(ValueError):
                normalize_feed(raw, NOW)
        raw = source()
        del raw["x"][0]["tweets"][0]["createdAt"]
        with self.assertRaises(ValueError):
            normalize_feed(raw, NOW)

    def test_short_posts_unknown_metrics_and_partial_source(self):
        raw = source()
        raw["x"][0]["tweets"][0].update(
            text="@someone https://t.co/link", likes=-1, replies=True)
        raw["errors"] = ["one author failed"]
        result = normalize_feed(raw, NOW)
        self.assertTrue(result["posts"][0]["short_context"])
        self.assertIsNone(result["posts"][0]["likes"])
        self.assertIsNone(result["posts"][0]["replies"])
        self.assertEqual(result["status"], "partial")

    def test_download_failure_and_regression_retain_last_good_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feed.json"
            good = refresh(path, lambda: source(), NOW)
            def unavailable():
                raise OSError("Offline")
            failed = refresh(path, unavailable, NOW)
            self.assertEqual(failed["posts"], good["posts"])
            self.assertEqual(failed["fetched_at"], good["fetched_at"])
            self.assertEqual(failed["status"], "error")
            older = source()
            older["generatedAt"] = "2026-10-29T05:00:00Z"
            result = refresh(path, lambda: older, NOW)
            self.assertEqual(result["generated_at"], good["generated_at"])
            self.assertEqual(json.loads(path.read_text())["posts"], good["posts"])

    def test_first_failure_empty_feed_and_invalid_empty_feed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feed.json"
            failed = refresh(path, lambda: {}, NOW)
            self.assertEqual(failed["status"], "error")
            self.assertEqual(failed["posts"], [])
            refresh(path, lambda: source(), NOW)
            empty = source()
            empty["x"] = []
            result = refresh(path, lambda: empty, NOW)
            self.assertEqual(result["posts"], [])
            self.assertEqual(result["status"], "ok")
            empty["errors"] = ["Source API unavailable"]
            with self.assertRaises(ValueError):
                normalize_feed(empty, NOW)

    def test_snapshot_is_embedded_and_script_termination_is_escaped(self):
        result = normalize_feed(source(), NOW)
        result["posts"][0]["text"] = '<!--<script></script><script>alert("x")</script>'
        page = build_html({"window": {"days": 90}, "builder_feed": result})
        self.assertIn('"builder_feed":', page)
        self.assertNotIn('</script><script>alert("x")', page)
        self.assertNotIn('<!--<script>', page)
        self.assertIn(r'\u003c/script>', page)


if __name__ == "__main__":
    unittest.main()
