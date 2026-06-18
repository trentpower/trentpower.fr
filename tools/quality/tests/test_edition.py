#!/usr/bin/env python3
"""Tests for the edition-consistency gate (tools/quality/validate_edition.py).

These cross the module's interface — `evaluate(Repo, edition) -> Result` and
`load(Repo)` — over a fixture repo. The active-HTML set is discovered inside
evaluate (not at import time), so a fixture repo is exercised cleanly with no
monkeypatching. Tests assert on the returned Result.

Stdlib unittest — no pytest dep.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import json
import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
for _sub in ("lib", "build", "quality", "verify"):
    sys.path.insert(0, str(TOOLS / _sub))

import validate_edition as ve  # noqa: E402

REPO_ROOT = TOOLS.parent
EDITION = "2026-06-18"


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _make_fixture_repo(root: pathlib.Path) -> None:
    _write(root, ve.CANONICAL_REL, json.dumps({"edition": EDITION}))
    _write(
        root,
        "public/index.html",
        f'<html data-edition="{EDITION}"><body>Edition {EDITION}</body></html>\n',
    )
    _write(
        root, ve.SITE_META_REL, json.dumps({"edition": EDITION, "asset_version": f"{EDITION}.1"})
    )


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _make_fixture_repo(self.root)
        self.repo = ve.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pristine_green(self):
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(r.ok, msg=r.fails)

    def test_stale_data_edition_fails(self):
        _write(self.root, "public/index.html", '<html data-edition="2020-01-01"></html>\n')
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(any("data-edition expected" in f for f in r.fails), r.fails)

    def test_stale_edition_prefix_fails(self):
        _write(self.root, "public/page.html", "<p>Édition 2020-01-01</p>\n")
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(any("expected edition" in f for f in r.fails), r.fails)

    def test_site_metadata_edition_mismatch_fails(self):
        _write(
            self.root,
            ve.SITE_META_REL,
            json.dumps({"edition": "2020-01-01", "asset_version": "2020-01-01.1"}),
        )
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(any("site-metadata.json: edition expected" in f for f in r.fails), r.fails)

    def test_asset_version_prefix_mismatch_fails(self):
        _write(
            self.root, ve.SITE_META_REL, json.dumps({"edition": EDITION, "asset_version": "9999.1"})
        )
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(any("asset_version" in f for f in r.fails), r.fails)

    def test_sw_cache_missing_edition_fails(self):
        _write(self.root, ve.SW_REL, "var CACHE = 'tp-cache-old';\n")
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(any("sw.js: CACHE name" in f for f in r.fails), r.fails)

    def test_verify_modal_edition_mismatch_fails(self):
        _write(self.root, ve.VERIFY_MODAL_REL, "var EDITION = '2020-01-01';\n")
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(any("verify-modal.js: EDITION expected" in f for f in r.fails), r.fails)

    def test_verification_data_stale_record_fails(self):
        _write(
            self.root,
            ve.VERIFICATION_DATA_REL,
            'window.TP_VERIFICATION_MAP = {"/":{"edition": "2020-01-01"}};\n',
        )
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(
            any("verification-data.js" in f and "edition expected" in f for f in r.fails), r.fails
        )


class Load(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = ve.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_identity_returns_error(self):
        edition, errors = ve.load(self.repo)
        self.assertIsNone(edition)
        self.assertTrue(errors)

    def test_bad_edition_returns_error(self):
        _write(self.root, ve.CANONICAL_REL, json.dumps({"edition": "nope"}))
        edition, errors = ve.load(self.repo)
        self.assertIsNone(edition)
        self.assertTrue(any("YYYY-MM-DD" in e for e in errors), errors)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ve.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
