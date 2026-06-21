#!/usr/bin/env python3
"""Tests for the verification-map date-freshness gate
(tools/quality/validate_verification_map_dates.py).

Cross `evaluate(text, present, now)` over fixture text at a frozen instant — no
clock mocking. Assert on the Result.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import datetime
import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_verification_map_dates as vm  # noqa: E402

REPO_ROOT = TOOLS.parent
NOW = datetime.datetime(2026, 6, 21, 12, 0, tzinfo=datetime.UTC)


def _records(*dates: str) -> str:
    return "var DATA = [" + ",".join(f'{{"validated":"{d}"}}' for d in dates) + "];"


class Evaluate(unittest.TestCase):
    def test_fresh_stamps_green(self):
        r = vm.evaluate(_records("2026-06-20", "2026-06-14"), True, NOW)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.seen, 2)

    def test_absent_file_skips(self):
        r = vm.evaluate("", False, NOW)
        self.assertTrue(r.ok)
        self.assertFalse(r.present)

    def test_no_records_skips(self):
        r = vm.evaluate("var DATA = [];", True, NOW)
        self.assertTrue(r.ok)
        self.assertEqual(r.seen, 0)

    def test_stale_stamp_fails(self):
        r = vm.evaluate(_records("2026-01-01"), True, NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("days old" in f for f in r.fails), r.fails)

    def test_future_stamp_fails(self):
        r = vm.evaluate(_records("2099-01-01"), True, NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("in the future" in f for f in r.fails), r.fails)

    def test_boundary_exactly_max_age_is_green(self):
        edge = (NOW.date() - datetime.timedelta(days=vm.VERIFICATION_MAP_MAX_AGE_DAYS)).isoformat()
        r = vm.evaluate(_records(edge), True, NOW)
        self.assertTrue(r.ok, msg=r.fails)

    def test_invalid_iso_fails(self):
        r = vm.evaluate('x = [{"validated":"2026-13-99"}];', True, NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("not a valid ISO date" in f for f in r.fails), r.fails)


class ExternalInterface(unittest.TestCase):
    def test_load_absent_in_empty_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            text, present = vm.load(vm.Repo(pathlib.Path(tmp)))
            self.assertFalse(present)
            self.assertEqual(text, "")

    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vm.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
