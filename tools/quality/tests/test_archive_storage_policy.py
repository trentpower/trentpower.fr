#!/usr/bin/env python3
"""Tests for the archive-storage-policy guardrail
(tools/quality/validate_archive_storage_policy.py).

`evaluate(tracked_paths)` is a pure function over a list of git-tracked paths,
so the tests inject plain lists — no git repo fixture needed.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import contextlib
import io
import pathlib
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_archive_storage_policy as ap  # noqa: E402

_REL = "public/integrity/releases"


def _run_main(tracked):
    """Drive main() through its injected seam, capturing (rc, stdout)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = ap.main(tracked=tracked)
    return rc, buf.getvalue()


class Evaluate(unittest.TestCase):
    def test_verification_record_is_allowed(self):
        allowed = [
            f"{_REL}/README.md",
            f"{_REL}/index.json",
            f"{_REL}/archive.css",
            f"{_REL}/2026-06-21/trentpower-fr-2026-06-21.zip.sha256",
            f"{_REL}/2026-06-21/trentpower-fr-2026-06-21.tar.gz.sha256",
            f"{_REL}/2026-06-21/trentpower-fr-2026-06-21.zip.sig",
            f"{_REL}/2026-06-21/SHA256SUMS",
            f"{_REL}/2026-06-21/integrity-redistributable.json",
            f"{_REL}/2026-06-21/release.json",
            f"{_REL}/2026-06-21/index.html",
        ]
        self.assertTrue(ap.evaluate(allowed).ok)

    def test_zip_binary_is_forbidden(self):
        r = ap.evaluate([f"{_REL}/2026-06-21/trentpower-fr-2026-06-21.zip"])
        self.assertFalse(r.ok)
        self.assertEqual(r.fails, [f"{_REL}/2026-06-21/trentpower-fr-2026-06-21.zip"])

    def test_targz_binary_is_forbidden(self):
        r = ap.evaluate([f"{_REL}/2026-06-21/trentpower-fr-2026-06-21.tar.gz"])
        self.assertFalse(r.ok)

    def test_other_archive_extensions_forbidden(self):
        for ext in ("tgz", "tar", "7z", "br"):
            with self.subTest(ext=ext):
                r = ap.evaluate([f"{_REL}/2026-06-21/trentpower-fr-2026-06-21.{ext}"])
                self.assertFalse(r.ok)

    def test_nested_archive_forbidden(self):
        r = ap.evaluate([f"{_REL}/2026-06-21/subdir/extra/x.zip"])
        self.assertFalse(r.ok)

    def test_archive_outside_release_tree_is_ignored(self):
        # this gate only governs the release tree; .zip elsewhere is another
        # gate's concern (and the .gitignore/exposure rules handle those).
        self.assertTrue(ap.evaluate(["public/downloads/thing.zip"]).ok)

    def test_mixed_set_reports_only_binaries(self):
        r = ap.evaluate(
            [
                f"{_REL}/README.md",
                f"{_REL}/2026-06-21/trentpower-fr-2026-06-21.zip",
                f"{_REL}/2026-06-21/trentpower-fr-2026-06-21.zip.sha256",
                f"{_REL}/2026-06-21/trentpower-fr-2026-06-21.tar.gz",
            ]
        )
        self.assertEqual(len(r.fails), 2)


class Main(unittest.TestCase):
    def test_clean_tree_returns_zero(self):
        rc, out = _run_main(
            [f"{_REL}/README.md", f"{_REL}/2026-06-21/trentpower-fr-2026-06-21.zip.sha256"]
        )
        self.assertEqual(rc, 0)
        self.assertIn("server-canonical", out)

    def test_committed_binary_returns_one(self):
        rc, out = _run_main([f"{_REL}/2026-06-21/trentpower-fr-2026-06-21.zip"])
        self.assertEqual(rc, 1)
        self.assertIn("must not enter git", out)
        self.assertIn("trentpower-fr-2026-06-21.zip", out)

    def test_many_binaries_are_truncated_in_output(self):
        many = [f"{_REL}/2026-06-21/trentpower-fr-{i:02d}.zip" for i in range(25)]
        rc, out = _run_main(many)
        self.assertEqual(rc, 1)
        self.assertIn("and 5 more", out)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
