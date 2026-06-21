#!/usr/bin/env python3
"""Tests for the hidden-artefact + archive-safety gate
(tools/quality/validate_hidden_artefacts.py).

Cross `evaluate(Repo)` over a fixture repo. Assert on the Result.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import io
import pathlib
import tempfile
import unittest
import zipfile

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_hidden_artefacts as vh  # noqa: E402

REPO_ROOT = TOOLS.parent


def _write(root: pathlib.Path, rel: str, text: str = "x") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _zip(root: pathlib.Path, rel: str, names: list[str]) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for n in names:
            zf.writestr(n, "data")
    p.write_bytes(buf.getvalue())


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vh.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_tree_green(self):
        _write(self.root, "public/index.html")
        r = vh.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_dotenv_is_flagged(self):
        _write(self.root, "public/.env", "SECRET=1")
        r = vh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("hidden artefact: .env" in f for f in r.fails), r.fails)

    def test_key_material_flagged(self):
        _write(self.root, "public/sub/id_ed25519")
        r = vh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("id_ed25519" in f for f in r.fails), r.fails)

    def test_audit_prefix_skipped(self):
        _write(self.root, "public/_audit/x.log")
        r = vh.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_forbidden_directory_flagged(self):
        _write(self.root, "public/node_modules/pkg/index.js")
        r = vh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("forbidden directory" in f for f in r.fails), r.fails)

    def test_font_binary_in_release_zip_flagged(self):
        _zip(self.root, "public/integrity/releases/2026-05-09/trentpower-fr-2026-05-09.zip",
             ["index.html", "fonts/x.woff2"])
        r = vh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("font binary inside" in f for f in r.fails), r.fails)

    def test_clean_release_zip_green(self):
        _zip(self.root, "public/integrity/releases/2026-05-09/trentpower-fr-2026-05-09.zip",
             ["index.html", "styles.css"])
        r = vh.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vh.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
