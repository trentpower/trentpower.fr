#!/usr/bin/env python3
"""Tests for the lowercase-comments gate
(tools/quality/validate_lowercase_comments.py).

Cross `evaluate(Repo)` over a fixture repo. Assert on the Result.

The real repo returns 1 (this is an advisory lint with a known, frozen
violation backlog), so the ExternalInterface case asserts rc == 1 with
violations present — never rc == 0.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_lowercase_comments as vlc  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vlc.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_all_lowercase_comments_green(self):
        # a python tool under a scanned pillar (tools/quality/) whose comment
        # prose is already lowercase — the handler reports no change, so the
        # gate is green.
        _write(
            self.root,
            "tools/quality/sample_tool.py",
            "#!/usr/bin/env python3\n# a lowercase comment about widgets\nx = 1\n",
        )
        # a css source file, also clean.
        _write(self.root, "styles/styles.src.css", "/* lowercase css note */\nbody{}\n")
        r = vlc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.fails, [])

    def test_uppercase_comment_caught(self):
        # a seeded UPPERCASE comment in a scanned python tool must be flagged.
        _write(
            self.root,
            "tools/quality/sample_tool.py",
            "#!/usr/bin/env python3\n# This Has Uppercase Prose\nx = 1\n",
        )
        r = vlc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any(
                f.startswith("tools/quality/sample_tool.py:2:")
                and "uppercase comment prose" in f
                for f in r.fails
            ),
            msg=r.fails,
        )
        self.assertEqual(r.files_with_diff, 1)

    def test_skip_set_excludes_self(self):
        # the validator and the fixer are in the py skip set — even seeded with
        # uppercase prose they must not be scanned.
        _write(
            self.root,
            "tools/quality/validate_lowercase_comments.py",
            "# UPPERCASE Prose Here\n",
        )
        _write(
            self.root,
            "tools/quality/fix_lowercase_comments.py",
            "# More UPPERCASE Prose\n",
        )
        r = vlc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)


class ExternalInterface(unittest.TestCase):
    def test_main_against_real_repo_reports_violations(self):
        # advisory lint over a known backlog: rc is 1, not 0. assert the
        # contract (non-zero + violations surfaced), matching the baseline.
        import contextlib
        import io

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = vlc.main(REPO_ROOT)
        self.assertEqual(rc, 1, msg=err.getvalue())
        self.assertIn("lowercase-comments violation(s)", err.getvalue())


if __name__ == "__main__":
    unittest.main()
