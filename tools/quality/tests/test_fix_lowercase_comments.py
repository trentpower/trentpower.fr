#!/usr/bin/env python3
"""Tests for the fixer tools/quality/fix_lowercase_comments.py.

main() walks the declared TARGETS and lowercases comment regions per language.
--dry-run reports counts without writing, so it runs over the real tree
non-destructively — covering the file walk, handler dispatch and summary render.
The writing arm stays out of the unit tier so no tracked file is mutated.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

from __future__ import annotations

import contextlib
import io
import sys
import unittest

import _fixture

_fixture.bootstrap()

import fix_lowercase_comments as flc  # noqa: E402


class MainDryRun(unittest.TestCase):
    def _run(self, argv):
        saved = sys.argv
        sys.argv = argv
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = flc.main()
        finally:
            sys.argv = saved
        return rc, buf.getvalue()

    def test_dry_run_reports_summary_without_writing(self):
        rc, out = self._run(["fix_lowercase_comments.py", "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("summary:", out)
        # dry-run never writes, so the verb is the conditional form.
        self.assertIn("would touch", out)


if __name__ == "__main__":
    unittest.main()
