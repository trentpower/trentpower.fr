#!/usr/bin/env python3
"""Tests for the local-path leakage gate
(tools/quality/validate_local_path_leakage.py).

Cross `evaluate(Repo)` over a fixture repo. Assert on the Result.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_local_path_leakage as vl  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vl.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_tree_green(self):
        _write(self.root, "public/index.html", "<p>clean</p>\n")
        _write(self.root, "public/styles.css", "body{color:#000}\n")
        r = vl.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_home_path_leak_fails(self):
        _write(self.root, "public/index.html", "<!-- /home/trentpower/Desktop/x -->\n")
        r = vl.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("index.html:1" in f for f in r.fails), r.fails)

    def test_server_path_leak_fails(self):
        _write(self.root, "public/app.js", "var p='/srv/data/web/vhosts/site';\n")
        r = vl.evaluate(self.repo)
        self.assertFalse(r.ok)

    def test_excluded_htaccess_mirror_is_skipped(self):
        _write(self.root, "public/source/htaccess.txt", "RedirectMatch htdocs/htdocs\n")
        r = vl.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_frozen_release_dir_is_skipped(self):
        _write(self.root, "public/integrity/releases/2026-02/x.txt", "/home/trentpower/old\n")
        r = vl.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_undecodable_file_is_skipped(self):
        # a non-utf8 public file raises UnicodeDecodeError on read; the scan
        # swallows it and moves on, leaving the tree clean.
        target = self.root / "public" / "blob.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\xff\xfe/home/trentpower/secret\n")
        r = vl.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vl.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_main_fails_and_prints_on_leak_fixture(self):
        import contextlib
        import io
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            _write(root, "public/index.html", "<!-- /home/trentpower/Desktop/x -->\n")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vl.main(root)
        out = buf.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("FAIL", out)
        self.assertIn("local-path leak", out)
        self.assertIn("index.html:1", out)


if __name__ == "__main__":
    unittest.main()
