#!/usr/bin/env python3
"""Tests for tools/lib/public_tree.py — the signed-surface walker.

`iter_public_files` decides which files under public/ enter the signed integrity
manifest. A silent mistake here either signs something it should not or drops a
real artefact, so every exclusion rule is exercised over a crafted fixture tree.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import _fixture

_fixture.bootstrap()

import public_tree as pt  # noqa: E402


class IterPublicFiles(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _w(self, rel, data=b"x"):
        _fixture.write_bytes(self.root, rel, data)

    def test_includes_real_artefacts_excludes_everything_else(self):
        # survivors
        self._w("index.html")
        self._w("styles.css")
        self._w("sub/page.html")
        # exact-name / path / template / prefix / ext / pattern / paired-sig
        self._w(".DS_Store")
        self._w("integrity.json")
        self._w("package.json")
        self._w("README.txt")  # EXCLUDE_PATHS (root readme)
        self._w("app.template.js")
        self._w("_audit-note.txt")  # EXCLUDE_PREFIXES filename
        self._w("bundle.zip")  # excluded extension
        self._w("gen.py")
        self._w("styles.v22.css")  # EXCLUDE_PATTERNS (numbered rollback)
        self._w("integrity/releases/2026-05-09/trentpower-fr-2026-05-09.zip.sig")  # paired sig
        # excluded directories
        self._w("node_modules/pkg/index.js")
        self._w(".git/config")
        self._w("_archives/old.html")  # EXCLUDE_PREFIXES dir

        rels = {rel for rel, _full in pt.iter_public_files(self.root)}
        self.assertEqual(rels, {"index.html", "styles.css", "sub/page.html"})

    def test_extra_exclude_files_honoured(self):
        self._w("keep.html")
        self._w("file-metadata.json")
        rels = {
            rel
            for rel, _ in pt.iter_public_files(
                self.root, extra_exclude_files={"file-metadata.json"}
            )
        }
        self.assertEqual(rels, {"keep.html"})

    def test_fullpath_opens_the_file(self):
        self._w("a.html", b"hello")
        (rel, full) = next(iter(pt.iter_public_files(self.root)))
        self.assertEqual(rel, "a.html")
        self.assertEqual(Path(full).read_bytes(), b"hello")


if __name__ == "__main__":
    unittest.main()
