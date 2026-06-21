#!/usr/bin/env python3
"""Tests for the dated-asset gate (tools/quality/validate_no_dated_assets.py).

Cross `evaluate(Repo)` over a fixture repo. Assert on the Result, never stdout.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_no_dated_assets as vnda  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vnda.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_asset_names_green(self):
        _write(self.root, "public/index.html", "<p>clean</p>\n")
        _write(self.root, "public/styles.css", "body{color:#000}\n")
        _write(self.root, "public/app.js", "console.log(1)\n")
        r = vnda.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_dated_asset_is_flagged(self):
        _write(self.root, "public/styles.2026-01-01.deadbeef.css", "body{}\n")
        r = vnda.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("styles.2026-01-01.deadbeef.css" in f for f in r.fails), r.fails
        )

    def test_frozen_archive_dated_asset_is_exempt(self):
        _write(
            self.root,
            "public/integrity/releases/2026-01/styles.2026-01-01.deadbeef.css",
            "body{}\n",
        )
        r = vnda.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vnda.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_main_fails_on_seeded_dated_asset(self):
        # seed a fixture root with a public/ dir (passes the is_dir guard) plus a
        # dated+hashed asset that the gate must flag, then exercise main()'s
        # fail-render branch and assert it exits 1 with a printed fail line.
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root, "public/styles.2026-01-01.deadbeef.css", "body{}\n")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vnda.main(root)
        out = buf.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("FAIL", out)
        self.assertIn("styles.2026-01-01.deadbeef.css", out)

    def test_main_fails_when_public_is_not_a_directory(self):
        # a root with no public/ dir trips the is_dir guard before evaluate() runs;
        # main() must print a FAIL line and exit 1.
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vnda.main(root)
        out = buf.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("FAIL", out)
        self.assertIn("not a directory", out)


if __name__ == "__main__":
    unittest.main()
