#!/usr/bin/env python3
"""Tests for the integrity-signature freshness gate
(tools/quality/validate_integrity_sig.py).

Cross `evaluate(Ctx)` / `load(Repo)` over a fixture repo, setting file mtimes
with os.utime — no clock or process mocking. Assert on the Result.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_integrity_sig as vis  # noqa: E402
from _fixture import set_mtime as _set_mtime  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _write(self.root, vis.MANIFEST_REL, "{}")
        _write(self.root, vis.SIG_REL, "sig")
        self.repo = vis.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_sig_newer_than_manifest_is_current(self):
        _set_mtime(self.root, vis.MANIFEST_REL, 1000.0)
        _set_mtime(self.root, vis.SIG_REL, 1005.0)
        r = vis.evaluate(vis.load(self.repo))
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("current" in o for o in r.oks), r.oks)

    def test_same_second_within_slack_is_current(self):
        _set_mtime(self.root, vis.MANIFEST_REL, 1000.0)
        _set_mtime(self.root, vis.SIG_REL, 1000.0)
        r = vis.evaluate(vis.load(self.repo))
        self.assertTrue(r.ok, msg=r.fails)

    def test_sig_older_than_manifest_fails(self):
        _set_mtime(self.root, vis.MANIFEST_REL, 2000.0)
        _set_mtime(self.root, vis.SIG_REL, 1000.0)
        r = vis.evaluate(vis.load(self.repo))
        self.assertFalse(r.ok)
        self.assertTrue(any("older than integrity.json" in f for f in r.fails), r.fails)

    def test_missing_sig_fails(self):
        (self.root / vis.SIG_REL).unlink()
        r = vis.evaluate(vis.load(self.repo))
        self.assertFalse(r.ok)
        self.assertTrue(any("missing" in f for f in r.fails), r.fails)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vis.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
