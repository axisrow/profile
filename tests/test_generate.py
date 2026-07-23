from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jinja2 import Environment

from sync.generate import chart_data, make_env, write_output


class MakeEnvTests(unittest.TestCase):
    def test_shares_common_options(self) -> None:
        env = make_env(
            Path(__file__).resolve().parent.parent / "sync" / "templates",
            autoescape=False,
        )
        self.assertIsInstance(env, Environment)
        self.assertTrue(env.keep_trailing_newline)
        self.assertTrue(env.trim_blocks)
        self.assertTrue(env.lstrip_blocks)

    def test_autoescape_off_by_default(self) -> None:
        env = make_env(Path("."), autoescape=False)
        self.assertFalse(env.autoescape)

    def test_autoescape_on(self) -> None:
        env = make_env(Path("."), autoescape=True)
        self.assertTrue(env.autoescape)


class WriteOutputTests(unittest.TestCase):
    def test_creates_nested_parent_dirs(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "deep" / "nested" / "out.md"
            result = write_output(path, "hello\n")
            self.assertEqual(result, path)
            self.assertEqual(path.read_text(), "hello\n")

    def test_overwrites_existing_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.md"
            path.write_text("old")
            write_output(path, "new")
            self.assertEqual(path.read_text(), "new")


class ChartDataTests(unittest.TestCase):
    def _history(self, entries: list[dict]) -> dict:
        return {
            "scope": "test",
            "start_date": "2026-03-01",
            "opening_balance": 0,
            "entries": entries,
        }

    def test_points_string_one_point_per_entry(self) -> None:
        entries = [
            {"date": "2026-03-01", "gained": 0, "total": 0},
            {"date": "2026-03-02", "gained": 5, "total": 5},
            {"date": "2026-03-03", "gained": 3, "total": 8},
        ]
        chart = chart_data(self._history(entries))
        self.assertEqual(len(chart["points"].split()), 3)

    def test_ticks_include_zero_and_ceiling(self) -> None:
        entries = [
            {"date": "2026-03-01", "gained": 0, "total": 0},
            {"date": "2026-03-02", "gained": 12, "total": 12},
        ]
        chart = chart_data(self._history(entries))
        values = [tick["value"] for tick in chart["ticks"]]
        self.assertEqual(values[0], 0)
        # ceiling rounds the max (12) up to the next multiple of 10 → 20.
        self.assertEqual(values[-1], 20)
        self.assertEqual(values[1], 10)

    def test_months_label_on_first_day_of_month(self) -> None:
        entries = [
            {"date": "2026-03-01", "gained": 0, "total": 0},
            {"date": "2026-03-15", "gained": 2, "total": 2},
            {"date": "2026-04-01", "gained": 1, "total": 3},
        ]
        chart = chart_data(self._history(entries))
        labels = [m["label"] for m in chart["months"]]
        # 2026-03-01 (first index) + 2026-04-01; mid-month 03-15 is skipped.
        self.assertEqual(labels, ["Mar", "Apr"])

    def test_latest_total_and_end_point_match_last_entry(self) -> None:
        entries = [
            {"date": "2026-03-01", "gained": 0, "total": 0},
            {"date": "2026-03-02", "gained": 7, "total": 7},
        ]
        chart = chart_data(self._history(entries))
        self.assertEqual(chart["latest_total"], 7)
        self.assertEqual(chart["latest_date"], "2026-03-02")
        # end_x is the x-projection of the last index: left + plot_width.
        self.assertEqual(chart["end_x"], "936.0")


if __name__ == "__main__":
    unittest.main()
