#!/usr/bin/env python3
"""Tests for the SRI coherence gate (tools/quality/validate_sri_coherence.py).

Cross `evaluate(Repo)` over a fixture repo with assets + HTML referencing them.
Assert on the Result.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import base64
import hashlib
import pathlib
import tempfile
import unittest

import _fixture

_fixture.bootstrap()

import validate_sri_coherence as vsc  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _sri(data: bytes) -> str:
    return "sha384-" + base64.b64encode(hashlib.sha384(data).digest()).decode()


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vsc.Repo(self.root)
        self.css = b"body{color:#000}\n"
        self.js = b"console.log(1)\n"
        _fixture.write(self.root, "public/styles.css", self.css.decode())
        _fixture.write(self.root, "public/js/theme.js", self.js.decode())

    def tearDown(self):
        self._tmp.cleanup()

    def _page(self, link_integ: str, script_integ: str) -> None:
        html = (
            f'<link rel="stylesheet" href="/styles.css?v=1" integrity="{link_integ}">'
            f'<script src="/js/theme.js?v=1" integrity="{script_integ}"></script>'
        )
        _fixture.write(self.root, "public/index.html", html)

    def test_coherent_sri_green(self):
        self._page(_sri(self.css), _sri(self.js))
        r = vsc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.checked, 2)

    def test_stale_link_sri_fails(self):
        self._page("sha384-WRONGWRONGWRONG", _sri(self.js))
        r = vsc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("<link" in f and "stale" in f for f in r.fails), r.fails)

    def test_missing_script_sri_fails(self):
        html = (
            f'<link rel="stylesheet" href="/styles.css" integrity="{_sri(self.css)}">'
            '<script src="/js/theme.js"></script>'  # no integrity
        )
        _fixture.write(self.root, "public/index.html", html)
        r = vsc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("<script" in f and "NO integrity" in f for f in r.fails), r.fails)

    def test_print_css_is_skipped(self):
        _fixture.write(self.root, "public/print.css", "@media print{}")
        # print.css referenced WITHOUT integrity must not fail.
        _fixture.write(
            self.root, "public/index.html", '<link rel="stylesheet" href="/print.css" media="print">'
        )
        r = vsc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_verification_data_must_not_carry_integrity(self):
        _fixture.write(self.root, "public/verify/verification-data.js", "var D=[]")
        _fixture.write(
            self.root,
            "public/index.html",
            '<script src="/verify/verification-data.js?v=1" integrity="sha384-x"></script>',
        )
        r = vsc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("must NOT carry integrity" in f for f in r.fails), r.fails)

    def test_missing_asset_fails(self):
        _fixture.write(
            self.root, "public/index.html", '<link rel="stylesheet" href="/gone.css" integrity="sha384-x">'
        )
        r = vsc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("not found" in f for f in r.fails), r.fails)

    def test_cross_origin_and_scheme_refs_skipped(self):
        # cross-origin (https://) + data:/mailto: refs are out of SRI scope ->
        # resolve to None -> not checked, no fail.
        html = (
            '<link rel="stylesheet" href="https://cdn.example/x.css" integrity="sha384-z">'
            '<script src="data:text/javascript,1" integrity="sha384-z"></script>'
        )
        _fixture.write(self.root, "public/index.html", html)
        r = vsc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.checked, 0)

    def test_document_relative_ref_resolved(self):
        # a relative href (no leading /) resolves against the page's directory.
        css = b"a{}\n"
        _fixture.write(self.root, "public/sub/theme.css", css.decode())
        _fixture.write(
            self.root,
            "public/sub/index.html",
            f'<link rel="stylesheet" href="theme.css" integrity="{_sri(css)}">',
        )
        r = vsc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.checked, 1)

    def test_link_without_href_skipped(self):
        _fixture.write(self.root, "public/index.html", '<link rel="stylesheet">')
        r = vsc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_main_renders_failures_over_fixture(self):
        # main() over a seeded-defect fixture exercises the FAIL render + RC 1.
        import contextlib
        import io

        self._page("sha384-STALEWRONG", _sri(self.js))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vsc.main(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("SRI coherence issue", buf.getvalue())

    def test_frozen_archive_html_skipped(self):
        _fixture.write(
            self.root,
            "public/integrity/releases/2026-05-09/index.html",
            '<link rel="stylesheet" href="/styles.css" integrity="sha384-STALEOK">',
        )
        r = vsc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)  # frozen archives are out of scope


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vsc.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
