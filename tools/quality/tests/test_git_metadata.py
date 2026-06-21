#!/usr/bin/env python3
"""Tests for the git/repo metadata gate
(tools/quality/validate_git_metadata.py).

Cross `evaluate(Repo)` over a fixture repo. Assert on the Result.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_git_metadata as vgm  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

# the seeded-defect fixtures must embed the forbidden tokens, but this test
# file itself lives under tools/ and is scanned by the real-repo gate in
# ExternalInterface. assembling the tokens from fragments keeps the matchable
# strings out of the on-disk bytes so the gate stays green against the repo.
_CHATGPT = "Chat" + "GPT"
_CLAUDE_CODE = "Claude" + " Code"
_ANTHROPIC = "Anthro" + "pic"
_COAUTHOR = "Co-" + "Authored-By"


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vgm.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_tree_green(self):
        _write(self.root, "public/index.html", "<p>a clean page with no attribution</p>\n")
        _write(self.root, "tools/quality/x.py", "x = 1  # nothing here\n")
        r = vgm.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.scanned, 2)

    def test_coauthor_trailer_caught(self):
        _write(self.root, "docs/notes.md", f"summary\n\n{_COAUTHOR}: someone <x@y>\n")
        r = vgm.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("co-authored-by trailer" in f for f in r.fails), r.fails)

    def test_chatgpt_reference_caught(self):
        _write(self.root, "tools/quality/y.py", f"# written with {_CHATGPT} help\n")
        r = vgm.evaluate(self.repo)
        self.assertFalse(r.ok)
        label = f"{_CHATGPT} reference"
        self.assertTrue(any(label in f for f in r.fails), r.fails)

    def test_allowlisted_file_not_flagged(self):
        # the authorship statement is allowed to name the bare vendor terms.
        _write(self.root, "docs/AUTHORSHIP-STATEMENT.md", f"We use {_CLAUDE_CODE} and {_CHATGPT}.\n")
        r = vgm.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_frozen_release_dir_skipped(self):
        _write(self.root, "public/integrity/releases/2026-02/x.txt", f"{_ANTHROPIC}\n")
        r = vgm.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vgm.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def _run_main(self, root):
        # capture both streams; main() renders failures to stderr and the
        # green line to stdout.
        import contextlib
        import io

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = vgm.main(root)
        return rc, out.getvalue(), err.getvalue()

    def test_main_fails_against_a_seeded_defect_fixture(self):
        # main() builds Repo(root) internally, so pointing it at a fixture with
        # a forbidden trailer exercises the FAIL-render branch and rc == 1.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root, "docs/notes.md", f"summary\n\n{_COAUTHOR}: someone <x@y>\n")
            rc, out, err = self._run_main(root)
        self.assertEqual(rc, 1, msg=out + err)
        self.assertIn("FAIL:", err)
        self.assertIn("co-authored-by trailer", err)
        self.assertEqual(out, "")

    def test_main_green_against_a_clean_fixture(self):
        # the clean-fixture path through main() prints the OK line to stdout.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root, "public/index.html", "<p>a clean page</p>\n")
            rc, out, err = self._run_main(root)
        self.assertEqual(rc, 0, msg=out + err)
        self.assertIn("OK:", out)

    def test_main_truncates_when_over_thirty_fails(self):
        # more than 30 fails exercises the truncation summary line.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            line = f"{_COAUTHOR}: someone <x@y>\n"
            _write(root, "docs/many.md", line * 40)
            rc, out, err = self._run_main(root)
        self.assertEqual(rc, 1, msg=out + err)
        self.assertIn("and", err)
        self.assertIn("more", err)


if __name__ == "__main__":
    unittest.main()
