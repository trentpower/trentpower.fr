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
        self.assertTrue(
            any("inline credential assignment" in f for f in r.fails), r.fails
        )

    def test_published_pgp_key_skipped(self):
        # the *public* pgp key carries a PRIVATE KEY-shaped header in practice
        # only via its block label; the skip list keeps it green even if its
        # content trips a signature. seed a benign published asset to prove the
        # skip path does not itself fail.
        _write(self.root, "public/.well-known/pgp-key.asc", "-----BEGIN PGP PUBLIC KEY")
        r = vrh.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vrh.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())
        out = buf.getvalue()
        self.assertIn("OK: no forbidden artefacts in release inputs", out)
        self.assertIn(
            f"repository-hygiene: scanning {REPO_ROOT / 'public'}", out
        )


if __name__ == "__main__":
    unittest.main()
