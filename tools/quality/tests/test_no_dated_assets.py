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


if __name__ == "__main__":
    unittest.main()
