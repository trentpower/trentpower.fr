#!/usr/bin/env python3
"""Tests for the translation-state gate (tools/quality/validate_translation_state.py).

Cross the module's interface — `evaluate(Ctx, release)` and `load(Repo)` — over a
tiny fixture repo. No monkeypatching; the fixture repo is the second filesystem
adapter. Tests assert on the returned Result, never on stdout.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_translation_state as vts  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent

# a minimal EN source page and its sha256-prefixed digest (the value an FR page
# must carry to declare a fresh translation).
_EN_HOME = "meta:\n  home:\n    title: Home\n"


def _fresh_hash(repo: vts.Repo) -> str:
    return vts._en_source_hash(repo, "home")


def _fr_page(source_hash: str, status: str = "machine-assisted") -> str:
    return (
        "translation:\n"
        "  source_page: home\n"
        f"  source_hash: {source_hash}\n"
        f"  status: {status}\n"
        "  updated: '2026-05-22'\n"
        "meta:\n  home:\n    title: Accueil\n"
    )


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vts.Repo(self.root)
        _write(self.root, "content/en/pages/home.yml", _EN_HOME)

    def tearDown(self):
        self._tmp.cleanup()

    def test_fresh_translation_is_green_with_no_warns(self):
        _write(self.root, "content/fr/pages/home.yml", _fr_page(_fresh_hash(self.repo)))
        r = vts.evaluate(vts.load(self.repo))
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.warns, [])
        self.assertTrue(any("translation state OK" in o for o in r.oks), r.oks)

    def test_stale_source_hash_is_a_warning_not_a_fail(self):
        _write(self.root, "content/fr/pages/home.yml", _fr_page("sha256-deadbeef"))
        r = vts.evaluate(vts.load(self.repo))
        self.assertTrue(r.ok, msg=r.fails)  # stale is a warning in dev mode
        self.assertEqual(r.fails, [])
        self.assertTrue(any("source_hash stale" in w for w in r.warns), r.warns)

    def test_stale_source_hash_fails_under_release(self):
        _write(self.root, "content/fr/pages/home.yml", _fr_page("sha256-deadbeef"))
        r = vts.evaluate(vts.load(self.repo), release=True)
        self.assertFalse(r.ok)
        self.assertTrue(any("source_hash stale" in f for f in r.fails), r.fails)

    def test_missing_translation_block_fails(self):
        _write(self.root, "content/fr/pages/home.yml", "meta:\n  home:\n    title: Accueil\n")
        r = vts.evaluate(vts.load(self.repo))
        self.assertFalse(r.ok)
        self.assertTrue(any("missing translation: block" in f for f in r.fails), r.fails)

    def test_no_fr_pages_fails(self):
        r = vts.evaluate(vts.load(self.repo))
        self.assertFalse(r.ok)
        self.assertTrue(any("no content/fr/pages" in f for f in r.fails), r.fails)

    def test_missing_field_in_block_fails(self):
        # a translation block lacking the updated field trips the per-field check.
        page = (
            "translation:\n"
            "  source_page: home\n"
            f"  source_hash: {_fresh_hash(self.repo)}\n"
            "  status: machine-assisted\n"
            "meta:\n  home:\n    title: Accueil\n"
        )
        _write(self.root, "content/fr/pages/home.yml", page)
        r = vts.evaluate(vts.load(self.repo))
        self.assertFalse(r.ok)
        self.assertTrue(any("translation.updated missing" in f for f in r.fails), r.fails)

    def test_invalid_status_fails(self):
        _write(
            self.root,
            "content/fr/pages/home.yml",
            _fr_page(_fresh_hash(self.repo), status="approved"),
        )
        r = vts.evaluate(vts.load(self.repo))
        self.assertFalse(r.ok)
        self.assertTrue(any("invalid status 'approved'" in f for f in r.fails), r.fails)

    def test_missing_en_source_yields_no_stale_warning(self):
        # source_page names an EN page that does not exist; _en_source_hash
        # returns None, so the page is never flagged stale even with a bogus hash.
        page = (
            "translation:\n"
            "  source_page: ghost\n"
            "  source_hash: sha256-deadbeef\n"
            "  status: human-reviewed\n"
            "  updated: '2026-05-22'\n"
            "meta:\n  home:\n    title: Accueil\n"
        )
        _write(self.root, "content/fr/pages/home.yml", page)
        r = vts.evaluate(vts.load(self.repo))
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.warns, [])


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        # keep the dev-mode (warning) path: strip any --release the caller passed.
        saved = sys.argv
        sys.argv = [saved[0]]
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vts.main(REPO_ROOT)
        finally:
            sys.argv = saved
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_main_fails_and_prints_to_stderr_on_defect_fixture(self):
        import contextlib
        import io
        import tempfile

        # main() renders fails (and the summary line) to stderr; a fixture with
        # no fr pages drives the fail branch.
        saved = sys.argv
        sys.argv = [saved[0]]
        try:
            with tempfile.TemporaryDirectory() as d:
                root = pathlib.Path(d)
                _write(root, "content/en/pages/home.yml", _EN_HOME)
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = vts.main(root)
        finally:
            sys.argv = saved
        out = err.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("translation state:", out)
        self.assertIn("error(s)", out)


if __name__ == "__main__":
    unittest.main()
