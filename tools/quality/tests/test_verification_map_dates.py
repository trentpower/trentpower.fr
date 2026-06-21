#!/usr/bin/env python3
"""Tests for the verification-map date-freshness gate
(tools/quality/validate_verification_map_dates.py).

Cross `evaluate(text, present, now)` over fixture text at a frozen instant — no
clock mocking. Assert on the Result.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import contextlib
import datetime
import io
import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()
import validate_verification_map_dates as vm  # noqa: E402
from _fixture import write as _write  # noqa: E402

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
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vm.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_main_fails_on_stale_stamp(self):
        # seed a fixture whose only stamp is far older than the 14-day window so
        # main() must take the FAIL branch deterministically.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root, vm.VERIFICATION_DATA_REL, _records("2026-01-01"))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vm.main(repo_root=root, now=NOW)
            out = buf.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("FAIL:", out)
        self.assertIn("days old", out)

    def test_main_truncates_overflow_fail_list(self):
        # more than 20 stale stamps so the "… and N more" overflow line renders.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root, vm.VERIFICATION_DATA_REL, _records(*["2026-01-01"] * 25))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vm.main(repo_root=root, now=NOW)
            out = buf.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("… and 5 more", out)

    def test_main_skips_when_file_absent(self):
        # empty fixture: the data file is absent, so main() prints the skip and exits 0.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vm.main(repo_root=root, now=NOW)
            out = buf.getvalue()
        self.assertEqual(rc, 0, msg=out)
        self.assertIn("absent — skipping", out)

    def test_main_skips_when_no_records(self):
        # file present but carries no validated entries: the no-records OK branch.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root, vm.VERIFICATION_DATA_REL, "var DATA = [];")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vm.main(repo_root=root, now=NOW)
            out = buf.getvalue()
        self.assertEqual(rc, 0, msg=out)
        self.assertIn("no validated entries", out)


if __name__ == "__main__":
    unittest.main()
