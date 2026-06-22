#!/usr/bin/env python3
"""Tests for tools/quality/validate_git_metadata.py — the AI-attribution /
authorship-trailer scrubber that gates the tracked tree.

evaluate() runs over an injected fixture Repo, so the forbidden-pattern matching,
line-number reporting and binary-file tolerance are asserted with no real repo.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import _fixture

_fixture.bootstrap()

import validate_git_metadata as vgm  # noqa: E402
from repo import Repo  # noqa: E402


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_forbidden_trailer_reports_line_number(self):
        # pattern on line 3 of a scanned file under a scan root.
        _fixture.write(self.root, "public/note.txt", "one\ntwo\nCo-Authored-By: x <y@z>\nfour\n")
        r = vgm.evaluate(Repo(self.root))
        self.assertFalse(r.ok)
        self.assertTrue(any("public/note.txt:3 [" in f for f in r.fails))

    def test_clean_file_passes_and_is_scanned(self):
        _fixture.write(self.root, "public/clean.txt", "nothing to see here\n")
        r = vgm.evaluate(Repo(self.root))
        self.assertTrue(r.ok)
        self.assertEqual(r.scanned, 1)

    def test_binary_file_skipped_not_crashed(self):
        # invalid UTF-8 → read_text(strict) raises UnicodeDecodeError → skipped.
        _fixture.write_bytes(self.root, "public/blob.txt", b"\xff\xfe\xff\x00")
        _fixture.write(self.root, "public/ok.txt", "fine\n")
        r = vgm.evaluate(Repo(self.root))
        self.assertTrue(r.ok)
        self.assertEqual(r.scanned, 1)  # only ok.txt counted; blob.txt skipped

    def test_vendor_name_caught(self):
        # build the forbidden token at runtime so this test's OWN source does not
        # carry the literal (the real-repo scanner walks tools/, including here).
        vendor = "Chat" + "GPT"
        _fixture.write(self.root, "public/x.md", f"built with {vendor}\n")
        r = vgm.evaluate(Repo(self.root))
        self.assertFalse(r.ok)


if __name__ == "__main__":
    unittest.main()
