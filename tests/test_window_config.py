import re
import unittest
import http.client
from pathlib import Path
from unittest.mock import MagicMock, patch

from aigc_trend_brief import WINDOW_DAYS, http_get_json
from render_dashboard import build_html


ROOT = Path(__file__).resolve().parents[1]


class WindowConfigTests(unittest.TestCase):
    @patch("aigc_trend_brief.time.sleep")
    @patch("aigc_trend_brief.urllib.request.urlopen")
    def test_incomplete_response_retries_without_using_partial_data(self, urlopen, sleep):
        broken = MagicMock()
        broken.__enter__.return_value.read.side_effect = http.client.IncompleteRead(b'{"x":', 2)
        complete = MagicMock()
        complete.__enter__.return_value.read.return_value = b'{"x": 1}'
        urlopen.side_effect = [broken, complete]
        self.assertEqual(http_get_json("https://example.invalid/data"), {"x": 1})
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(3)

    def test_real_dataset_ranges_do_not_duplicate_or_offer_unavailable_windows(self):
        for days, expected in [(90, [90, 30, 7]), (30, [30, 7]), (7, [7]), (3, [3])]:
            with self.subTest(days=days):
                html = build_html({"window": {"days": days}})
                select = re.search(r'<select id="windowFilter">(.*?)</select>', html, re.S)[1]
                labels = re.findall(r">近 (\d+) 天</option>", select)
                self.assertEqual(list(map(int, labels)), expected)
                self.assertEqual(len(labels), len(set(labels)))
                self.assertIn('value="full"', select)
                self.assertNotIn('textContent = "本期 "', html)

    def test_every_production_entry_defaults_to_ninety_days(self):
        self.assertEqual(WINDOW_DAYS, 90)
        shell = (ROOT / "run_daily.sh").read_text()
        self.assertEqual(int(re.search(r'DAYS="\$\{1:-(\d+)\}"', shell)[1]), WINDOW_DAYS)
        workflow = (ROOT / ".github/workflows/deploy.yml").read_text()
        days_input = workflow.split("      days:\n")[1].split("      refresh_discovery:")[0]
        self.assertEqual(int(re.search(r'default: "(\d+)"', days_input)[1]), WINDOW_DAYS)
        self.assertEqual(int(re.search(r"WINDOW_DAYS:.*days \|\| '(\d+)'", workflow)[1]),
                         WINDOW_DAYS)


if __name__ == "__main__":
    unittest.main()
