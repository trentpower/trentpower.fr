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

    def test_glob_match_that_is_a_directory_is_ignored(self):
        # a directory whose name matches a hidden glob (e.g. a dir literally
        # named `.env`) must be skipped — the scan flags files only (line 92).
        (self.root / "public" / ".env").mkdir(parents=True)
        r = vh.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_user_ini_flagged(self):
        _write(self.root, "public/.user.ini", "auto_prepend_file=x")
        r = vh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any(".user.ini present" in f for f in r.fails), r.fails)

    def test_macosx_directory_flagged(self):
        (self.root / "public" / "sub" / "__MACOSX").mkdir(parents=True)
        r = vh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("hidden artefact dir" in f for f in r.fails), r.fails)

    def test_non_date_release_folder_skipped(self):
        # a folder under releases/ that is not YYYY-MM-DD must not be scanned;
        # the font binary it hides stays unreported (line 125 + 121->138).
        _zip(self.root, "public/integrity/releases/draft/trentpower-fr-draft.zip",
             ["fonts/x.woff2"])
        r = vh.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_stale_stylesheet_in_release_zip_flagged(self):
        _zip(self.root, "public/integrity/releases/2026-05-09/trentpower-fr-2026-05-09.zip",
             ["index.html", "assets/styles.v3.css"])
        r = vh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("stale stylesheet inside" in f for f in r.fails), r.fails)

    def test_unreadable_zip_is_a_finding(self):
        # a file with a .zip name that is not a valid archive must surface as a
        # finding rather than crash the scan (lines 135-136).
        _write(self.root,
               "public/integrity/releases/2026-05-09/trentpower-fr-2026-05-09.zip",
               "not actually a zip")
        r = vh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("could not read" in f for f in r.fails), r.fails)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vh.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_main_renders_fails_and_returns_one(self):
        # point main() at a fixture seeded with a hidden artefact; it must
        # return 1 and print the FAIL header plus the offending line.
        import contextlib

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        _write(root, "public/.env", "SECRET=1")

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = vh.main(root)
        combined = out.getvalue() + err.getvalue()
        self.assertEqual(rc, 1, msg=combined)
        self.assertIn("FAIL:", combined)
        self.assertIn("hidden artefact: .env", combined)
        self.assertIn("Remediation:", combined)


if __name__ == "__main__":
    unittest.main()
