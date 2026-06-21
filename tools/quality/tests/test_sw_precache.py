#!/usr/bin/env python3
"""Tests for the service-worker precache gate (tools/quality/validate_sw_precache.py).

Cross `evaluate(Repo)` over a fixture repo holding an sw.js plus the files its
precache list references. Assert on the Result.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_sw_precache as vsw  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent


def _sw(crit: list[str], opt: list[str]) -> str:
    c = ", ".join(f"'{u}'" for u in crit)
    o = ", ".join(f"'{u}'" for u in opt)
    return f"var CRITICAL_PRECACHE = [{c}];\nvar OPTIONAL_PRECACHE = [{o}];\n"


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vsw.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_all_urls_resolve_green(self):
        _write(self.root, "public/index.html", "x")
        _write(self.root, "public/styles.css", "x")
        _write(self.root, vsw.SW_REL, _sw(["/", "/styles.css"], []))
        r = vsw.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.count, 2)

    def test_missing_sw_fails(self):
        r = vsw.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(r.sw_missing)

    def test_missing_literals_fails(self):
        _write(self.root, vsw.SW_REL, "var X = 1;\n")
        r = vsw.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(r.literals_missing)

    def test_empty_precache_fails(self):
        _write(self.root, vsw.SW_REL, _sw([], []))
        r = vsw.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(r.empty)

    def test_url_missing_on_disk_fails(self):
        _write(self.root, vsw.SW_REL, _sw(["/gone.css"], []))
        r = vsw.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("missing on disk" in f for f in r.fails), r.fails)

    def test_bad_extension_fails(self):
        _write(self.root, "public/data.bin", "x")
        _write(self.root, vsw.SW_REL, _sw(["/data.bin"], []))
        r = vsw.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("not in allowed precache type set" in f for f in r.fails), r.fails)

    def test_non_rooted_url_fails(self):
        _write(self.root, vsw.SW_REL, _sw(["styles.css"], []))
        r = vsw.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("not server-rooted" in f for f in r.fails), r.fails)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vsw.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


class MainRendersFailures(unittest.TestCase):
    """Drive main() over seeded-defect fixture repos — each defect class trips a
    distinct FAIL-render branch. assert rc==1 plus the printed FAIL line."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_main(self) -> tuple[int, str]:
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vsw.main(self.root)
        return rc, buf.getvalue()

    def test_main_fails_when_sw_missing(self):
        # empty repo — no sw.js at all.
        rc, out = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("FAIL: sw.js missing", out)

    def test_main_fails_when_literals_missing(self):
        _write(self.root, vsw.SW_REL, "var X = 1;\n")
        rc, out = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("FAIL: sw.js missing CRITICAL_PRECACHE", out)

    def test_main_fails_when_precache_empty(self):
        _write(self.root, vsw.SW_REL, _sw([], []))
        rc, out = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("precache list is empty", out)

    def test_main_renders_precache_issue(self):
        # the dominant gap: a precache URL that does not resolve on disk.
        _write(self.root, vsw.SW_REL, _sw(["/gone.css"], []))
        rc, out = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("precache issue(s)", out)
        self.assertIn("missing on disk", out)

    def test_main_truncates_overflow_of_failures(self):
        # >30 failing URLs trips the "… and N more" truncation tail.
        urls = [f"/missing-{i}.css" for i in range(35)]
        _write(self.root, vsw.SW_REL, _sw(urls, []))
        rc, out = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("35 precache issue(s)", out)
        self.assertIn("and 5 more", out)


if __name__ == "__main__":
    unittest.main()
