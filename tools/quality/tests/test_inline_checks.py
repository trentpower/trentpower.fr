#!/usr/bin/env python3
"""Tests for tools/quality/inline_checks.py — frozen-archive immutability.

`_hash_archive_tree` + `check_frozen_archives_immutable` are the gate that
catches a generator silently rewriting historical release bytes. They read the
module globals ROOT (public/) and ARCHIVE_BASELINE directly, so these tests
redirect those globals to a fixture tree (restored in tearDown) and assert the
seal / no-drift / drift / auto-seal / bad-baseline outcomes. (`check_gpg` needs
a real gpg and lives in the integration tier.)

NOTE: pinning module globals is a short-term coverage move; if this grows,
introduce a small root seam on these functions (ADR-0002) instead.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import _fixture

_fixture.bootstrap()

import inline_checks as ic  # noqa: E402


def _quiet(fn, *a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(*a)
    return rc, buf.getvalue()


class InlineChecksBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self._saved = (ic.ROOT, ic.ARCHIVE_BASELINE)
        ic.ROOT = self.root
        ic.ARCHIVE_BASELINE = self.root / "archive-baseline.json"
        self.addCleanup(self._restore)

    def _restore(self):
        ic.ROOT, ic.ARCHIVE_BASELINE = self._saved

    def _rel(self, rel, data=b"bytes"):
        _fixture.write_bytes(self.root, rel, data)


class HashArchiveTree(InlineChecksBase):
    def test_empty_when_no_releases(self):
        self.assertEqual(ic._hash_archive_tree(), {})

    def test_legacy_edition_locks_whole_dir(self):
        self._rel("integrity/releases/2026-02/a.txt")
        self._rel("integrity/releases/2026-02/b.txt")
        out = ic._hash_archive_tree()
        self.assertEqual(
            set(out),
            {"integrity/releases/2026-02/a.txt", "integrity/releases/2026-02/b.txt"},
        )

    def test_full_date_locks_canonical_only(self):
        base = "integrity/releases/2026-05-09"
        # the .zip binary itself is server-canonical and NOT committed to git,
        # so it is not locked; its committed .sha256 sidecar is the seal.
        self._rel(f"{base}/trentpower-fr-2026-05-09.zip")  # excluded (server-canonical)
        self._rel(f"{base}/trentpower-fr-2026-05-09.zip.sha256")  # locked (the seal)
        self._rel(f"{base}/release.json")
        self._rel(f"{base}/trentpower-fr-2026-05-09.zip.sig")  # excluded (.sig)
        self._rel(f"{base}/builds.json")  # excluded
        out = ic._hash_archive_tree()
        self.assertEqual(
            set(out),
            {
                f"{base}/trentpower-fr-2026-05-09.zip.sha256",
                f"{base}/release.json",
            },
        )


class FrozenArchivesImmutable(InlineChecksBase):
    def _seed_legacy(self, data=b"one"):
        self._rel("integrity/releases/2026-02/a.txt", data)

    def test_no_archives_present_is_ok(self):
        rc, out = _quiet(ic.check_frozen_archives_immutable)
        self.assertEqual(rc, 0)
        self.assertIn("no frozen archives", out)

    def test_first_run_seals_baseline(self):
        self._seed_legacy()
        rc, out = _quiet(ic.check_frozen_archives_immutable)
        self.assertEqual(rc, 0)
        self.assertIn("sealed initial baseline", out)
        self.assertTrue(ic.ARCHIVE_BASELINE.exists())

    def test_second_run_no_drift_is_ok(self):
        self._seed_legacy()
        _quiet(ic.check_frozen_archives_immutable)  # seal
        rc, out = _quiet(ic.check_frozen_archives_immutable)
        self.assertEqual(rc, 0)
        self.assertIn("immutable", out)

    def test_drift_fails(self):
        self._seed_legacy(b"one")
        _quiet(ic.check_frozen_archives_immutable)  # seal
        self._rel("integrity/releases/2026-02/a.txt", b"TAMPERED")  # rewrite bytes
        rc, out = _quiet(ic.check_frozen_archives_immutable)
        self.assertEqual(rc, 1)
        self.assertIn("drift", out)

    def test_bad_baseline_json_fails(self):
        self._seed_legacy()
        ic.ARCHIVE_BASELINE.write_text("{ not valid json", encoding="utf-8")
        rc, out = _quiet(ic.check_frozen_archives_immutable)
        self.assertEqual(rc, 1)
        self.assertIn("invalid JSON", out)

    def test_new_canonical_auto_sealed(self):
        self._seed_legacy()
        _quiet(ic.check_frozen_archives_immutable)  # seal a.txt
        self._rel("integrity/releases/2026-02/c.txt", b"new")  # new file on disk
        rc, out = _quiet(ic.check_frozen_archives_immutable)
        self.assertEqual(rc, 0)
        self.assertIn("auto-sealed", out)
        baseline = json.loads(ic.ARCHIVE_BASELINE.read_text())
        self.assertIn("integrity/releases/2026-02/c.txt", baseline)


class CheckGpgGuards(unittest.TestCase):
    """check_gpg's pre-gpg guard arms (missing manifest/sig, missing published
    key) read ic.ROOT directly. The full gpg verification path needs a real key
    + signature and stays in the integration tier."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self._saved = ic.ROOT
        ic.ROOT = self.root
        self.addCleanup(self._restore)

    def _restore(self):
        ic.ROOT = self._saved

    def test_missing_manifest_and_sig(self):
        rc, out = _quiet(ic.check_gpg)
        self.assertEqual(rc, 1)
        self.assertIn("missing", out)

    def test_missing_published_key(self):
        (self.root / "integrity.json").write_text("{}", encoding="utf-8")
        (self.root / "integrity.json.sig").write_text("sig", encoding="utf-8")
        rc, out = _quiet(ic.check_gpg)
        self.assertEqual(rc, 1)
        self.assertIn("published key", out)


if __name__ == "__main__":
    unittest.main()
