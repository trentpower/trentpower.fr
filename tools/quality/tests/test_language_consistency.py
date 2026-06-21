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
from _fixture import write_bytes as _write_bytes  # noqa: E402

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

    def test_undecodable_file_is_skipped(self):
        # a scanned file with invalid utf-8 bytes makes repo.read raise
        # UnicodeDecodeError; evaluate() swallows it and moves on rather than
        # crashing, so the tree stays green.
        _write_bytes(self.root, "public/blob.txt", b"\xff\xfe not utf-8 \x80\x81")
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

    def test_main_fails_on_seeded_defect(self):
        # mirror the seeded-defect evaluate() tests, but drive the real main()
        # adapter against a temp fixture so the FAIL-render branch runs.
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root, "public/about.html", "<p>Every page is hand-written.</p>\n")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = vlc.main(root)
        self.assertEqual(rc, 1)
        out = err.getvalue()
        self.assertIn("FAIL", out)
        self.assertIn("about.html:1", out)

    def test_main_truncates_when_over_thirty_fails(self):
        # more than 30 hits exercises the "… and N more" truncation branch in
        # the FAIL-render path; assert the real count is surfaced.
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            body = "".join(f"<p>line {i} hand-written</p>\n" for i in range(35))
            _write(root, "public/many.html", body)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = vlc.main(root)
        self.assertEqual(rc, 1)
        out = err.getvalue()
        self.assertIn("35 authorship-language issue(s)", out)
        self.assertIn("and 5 more", out)


if __name__ == "__main__":
    unittest.main()
