#!/usr/bin/env python3
"""Tests for the authorship-language consistency gate
(tools/quality/validate_language_consistency.py).

Cross `evaluate(Repo)` over a fixture repo. Assert on the Result.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

import _fixture

_fixture.bootstrap()

import validate_language_consistency as vlc  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vlc.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_consistent_tree_green(self):
        _write(
            self.root,
            "public/index.html",
            "<p>All content and code are reviewed manually before publication.</p>\n",
        )
        _write(self.root, "public/styles.css", "body{color:#000}\n")
        r = vlc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_handwritten_phrase_fails(self):
        _write(self.root, "public/about.html", "<p>Every page is hand-written.</p>\n")
        r = vlc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("about.html:1" in f for f in r.fails), r.fails)

    def test_fully_manual_phrase_fails(self):
        _write(self.root, "public/notes.md", "This site is fully manual end to end.\n")
        r = vlc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("notes.md:1" in f for f in r.fails), r.fails)

    def test_engineer_warning_line_is_allowlisted(self):
        _write(self.root, "public/sw.js", "//  do not edit by hand.\n")
        r = vlc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_frozen_release_dir_is_skipped(self):
        _write(
            self.root,
            "public/integrity/releases/2026-05/snap.html",
            "<p>hand-crafted prose</p>\n",
        )
        r = vlc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vlc.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
