#!/usr/bin/env python3
"""Tests for the repository-hygiene gate
(tools/quality/validate_repository_hygiene.py).

Cross `evaluate(Repo)` over a fixture repo. Assert on the Result.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import contextlib
import io
import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_repository_hygiene as vrh  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vrh.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_tree_green(self):
        _write(self.root, "public/index.html", "<!doctype html><p>hello</p>")
        r = vrh.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_dotenv_forbidden_name_flagged(self):
        _write(self.root, "public/.env", "SECRET=1")
        r = vrh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("forbidden filename '.env'" in f for f in r.fails), r.fails)

    def test_key_material_flagged(self):
        _write(self.root, "public/sub/id_ed25519", "key")
        r = vrh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("id_ed25519" in f for f in r.fails), r.fails)

    def test_stale_generated_db_flagged(self):
        _write(self.root, "public/data/observatory.sqlite", "binary")
        r = vrh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("forbidden extension '.sqlite'" in f for f in r.fails), r.fails)

    def test_inline_secret_in_text_file_flagged(self):
        _write(self.root, "public/leak.json", 'api_key = "supersecretvalue123"')
        r = vrh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("inline credential assignment" in f for f in r.fails), r.fails)

    def test_published_pgp_key_skipped(self):
        # the *public* pgp key carries a PRIVATE KEY-shaped header in practice
        # only via its block label; the skip list keeps it green even if its
        # content trips a signature. seed a benign published asset to prove the
        # skip path does not itself fail.
        _write(self.root, "public/.well-known/pgp-key.asc", "-----BEGIN PGP PUBLIC KEY")
        r = vrh.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_forbidden_path_fragment_flagged(self):
        # a private/ fragment anywhere in the relpath is forbidden even when the
        # basename and suffix are otherwise innocuous. covers the fragment branch.
        _write(self.root, "public/private/notes.html", "<p>internal</p>")
        r = vrh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("forbidden path fragment 'private/'" in f for f in r.fails), r.fails)

    def test_undecodable_text_file_skipped(self):
        # a file with a text suffix but non-utf-8 bytes raises UnicodeDecodeError
        # in the content scan; the gate swallows it and moves on rather than
        # crashing, leaving the tree green. covers the decode-failure branch.
        from _fixture import write_bytes as _write_bytes

        _write_bytes(self.root, "public/broken.txt", b"\xff\xfe\x00\x01not utf8")
        r = vrh.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)


class ExternalInterface(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_main_passes_against_the_real_repo(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vrh.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())
        out = buf.getvalue()
        self.assertIn("OK: no forbidden artefacts in release inputs", out)
        self.assertIn(f"repository-hygiene: scanning {REPO_ROOT / 'public'}", out)

    def test_main_fails_and_renders_violations(self):
        # seed a forbidden artefact in a fixture public/ tree, then drive main()
        # over that root. main() must print the FAIL header, list each violation
        # with the ✗ marker and the remediation note, and return 1.
        _write(self.root, "public/.env", "SECRET=1")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vrh.main(self.root)
        out = buf.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("FAIL: 1 hygiene violation(s):", out)
        self.assertIn("✗ .env: forbidden filename '.env'", out)
        self.assertIn("These artefacts must never enter a release.", out)

    def test_main_fails_when_scan_target_missing(self):
        # an empty fixture root has no public/ dir; main() must report the
        # missing scan target and return 1 before attempting any walk.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vrh.main(self.root)
        out = buf.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn(f"FAIL: scan target does not exist: {self.root / 'public'}", out)


if __name__ == "__main__":
    unittest.main()
