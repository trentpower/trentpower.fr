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
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_edition as ve  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent
EDITION = "2026-06-18"


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

    def test_stale_document_edition_meta_fails(self):
        # line 95 — <meta name="document-edition"> with a non-canonical value.
        _write(
            self.root,
            "public/page.html",
            '<meta name="document-edition" content="2020-01-01">\n',
        )
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(any("document-edition expected" in f for f in r.fails), r.fails)

    def test_missing_active_html_file_reported(self):
        # lines 126-127 — _active_html discovers a path that is no longer a file
        # by the time evaluate re-reads it (a phantom glob entry). a Repo
        # subclass injects the phantom so no frozen field is mutated.
        class _PhantomRepo(ve.Repo):
            def glob(self, pattern):
                paths = list(super().glob(pattern))
                if "public/**/*.html" in pattern:
                    paths.append("public/phantom.html")
                return paths

        repo = _PhantomRepo(self.root)
        r = ve.evaluate(repo, EDITION)
        self.assertTrue(any("missing active HTML file" in f for f in r.fails), r.fails)

    def test_site_metadata_nested_edition_id_date_mismatch_fails(self):
        # line 140 — nested edition object whose id and date disagree.
        _write(
            self.root,
            ve.SITE_META_REL,
            json.dumps(
                {
                    "edition": {"id": EDITION, "date": "2020-01-01"},
                    "asset_version": f"{EDITION}.1",
                }
            ),
        )
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(any("does not match edition.date" in f for f in r.fails), r.fails)

    def test_site_metadata_missing_file_fails(self):
        # line 154 — site-metadata.json absent entirely.
        (self.root / ve.SITE_META_REL).unlink()
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(any("site-metadata.json: file missing" in f for f in r.fails), r.fails)

    def test_verify_modal_no_edition_literal_fails(self):
        # line 160 — verify-modal.js present but with no `var EDITION` literal.
        _write(self.root, ve.VERIFY_MODAL_REL, "// no edition here\n")
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(
            any("no `var EDITION = '...'` literal found" in f for f in r.fails), r.fails
        )

    def test_sw_no_cache_literal_fails(self):
        # line 168 — sw.js present but with no `var CACHE` literal.
        _write(self.root, ve.SW_REL, "// service worker without a cache name\n")
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(any("no `var CACHE = '...'` literal found" in f for f in r.fails), r.fails)

    def test_humans_txt_stale_last_reviewed_fails(self):
        # line 186 — humans.txt last-reviewed date is stale.
        _write(self.root, ve.HUMANS_REL, "Last reviewed: 2020-01-01\n")
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(any("humans.txt: Last reviewed expected" in f for f in r.fails), r.fails)

    def test_strings_invalid_json_is_swallowed_green(self):
        # lines 197-198, 199->247 — strings.json that does not parse is treated
        # as absent (sd = None) and does not contribute a failure.
        _write(self.root, ve.STRINGS_REL, "{ this is not json")
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(r.ok, msg=r.fails)

    def test_strings_non_iso_edition_skips_localised_check(self):
        # lines 204-205, 206->247 — a non-ISO edition makes strptime raise, so
        # the localised-date walk is skipped and the stale string is not flagged.
        _write(
            self.root,
            ve.STRINGS_REL,
            json.dumps({"en": {"footer": "10 June 2020"}}),
        )
        r = ve.evaluate(self.repo, "not-a-real-date")
        self.assertFalse(any("localised date" in f for f in r.fails), r.fails)

    def test_strings_unknown_language_subtree_ignored(self):
        # line 224 — a top-level key that is not a known locale is skipped.
        _write(
            self.root,
            ve.STRINGS_REL,
            json.dumps({"de": {"footer": "10 June 2020"}}),
        )
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(r.ok, msg=r.fails)

    def test_strings_stale_localised_date_fails(self):
        # line 234 — a localised date string in a known locale that is not the
        # canonical edition's localised form.
        _write(
            self.root,
            ve.STRINGS_REL,
            json.dumps({"en": {"footer": "10 June 2020"}}),
        )
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(
            any("localised date" in f and "10 June 2020" in f for f in r.fails), r.fails
        )

    def test_strings_stale_localised_date_inside_list_fails(self):
        # lines 241-243 — the walk descends into lists of strings too.
        _write(
            self.root,
            ve.STRINGS_REL,
            json.dumps({"en": {"notes": ["fresh", "10 June 2020"]}}),
        )
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(any("notes[1]" in f and "localised date" in f for f in r.fails), r.fails)

    def test_strings_ignored_prefix_is_not_flagged(self):
        # the IGNORE_PREFIXES branch — release-card labels carry coincidental
        # localised dates that reference frozen archives, so they are skipped.
        _write(
            self.root,
            ve.STRINGS_REL,
            json.dumps({"en": {"releases": {"detail": {"label": "10 June 2020"}}}}),
        )
        r = ve.evaluate(self.repo, EDITION)
        self.assertTrue(r.ok, msg=r.fails)


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

    def test_main_fails_and_prints_on_stale_fixture(self):
        # lines 258-263 — main() over a fixture repo with a seeded stale
        # data-edition reference returns 1 and prints the FAIL header plus the
        # failing path.
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture_repo(root)
            _write(root, "public/index.html", '<html data-edition="2020-01-01"></html>\n')
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = ve.main(root)
            out = buf.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("FAIL:", out)
        self.assertIn("edition-consistency issue", out)
        self.assertIn("data-edition expected", out)

    def test_main_fails_on_bad_canonical_edition(self):
        # lines 254-256 — load() returns errors (non-ISO canonical edition), so
        # main() prints each FAIL line to stderr and returns 1 before evaluate.
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root, ve.CANONICAL_REL, json.dumps({"edition": "nope"}))
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = ve.main(root)
            out = err.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("FAIL:", out)
        self.assertIn("YYYY-MM-DD", out)


if __name__ == "__main__":
    unittest.main()
