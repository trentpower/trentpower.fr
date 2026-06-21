#!/usr/bin/env python3
"""Tests for the structural-HTML-defect gate
(tools/quality/validate_html_correctness.py).

Cross `evaluate(Repo)` over a fixture repo. Assert on the Result, never on
stdout. ExternalInterface runs the real `main()` against the production repo and
asserts the baseline exit code.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_html_correctness as vhc  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


# a minimal, structurally clean page: exactly one visible <h1>, well-nested
# headings, a single canonical/description/og pair, and no empty anchors.
CLEAN_PAGE = (
    "<!doctype html><html><head>"
    '<link rel="canonical" href="https://trentpower.fr/">'
    '<meta name="description" content="x">'
    '<meta property="og:title" content="x">'
    '<meta property="og:url" content="https://trentpower.fr/">'
    "</head><body>"
    "<h1>Title</h1>"
    "<h2>Section</h2>"
    '<a href="/somewhere">visible text</a>'
    "</body></html>\n"
)


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vhc.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_page_green(self):
        _write(self.root, "public/index.html", CLEAN_PAGE)
        _write(self.root, "public/privacy/index.html", CLEAN_PAGE)
        r = vhc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.page_count, 2)

    def test_mismatched_heading_caught(self):
        # defect 1: a heading opened as <h2> closed as </h3>.
        bad = (
            "<!doctype html><html><head></head><body>"
            "<h1>Title</h1><h2>Section</h3>"
            "</body></html>\n"
        )
        _write(self.root, "public/index.html", bad)
        r = vhc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("heading mismatch" in err for _rel, err in r.fails), r.fails)

    def test_duplicate_id_caught(self):
        # defect 2: two elements sharing the same id="…" in one document.
        bad = (
            "<!doctype html><html><head></head><body>"
            "<h1>Title</h1>"
            '<div id="dup"></div><div id="dup"></div>'
            "</body></html>\n"
        )
        _write(self.root, "public/index.html", bad)
        r = vhc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("duplicate id" in err for _rel, err in r.fails), r.fails)

    def test_empty_anchor_no_aria_label_caught(self):
        # defect 3: an icon-only/JS-populated <a> with no visible text and no
        # aria-label — a banned construct (no accessible name).
        bad = (
            "<!doctype html><html><head></head><body>"
            "<h1>Title</h1>"
            '<a href="/x"></a>'
            "</body></html>\n"
        )
        _write(self.root, "public/index.html", bad)
        r = vhc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("empty <a> with no aria-label" in err for _rel, err in r.fails), r.fails
        )

    def test_missing_visible_h1_caught(self):
        # zero visible <h1> is a structural defect (expected exactly one).
        bad = "<!doctype html><html><head></head><body><p>body</p></body></html>\n"
        _write(self.root, "public/index.html", bad)
        r = vhc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("exactly one visible <h1>" in err for _rel, err in r.fails), r.fails
        )

    def test_frozen_archive_pages_excluded(self):
        # dated frozen-archive snapshots are not scanned, even if defective.
        _write(self.root, "public/index.html", CLEAN_PAGE)
        _write(
            self.root,
            "public/integrity/releases/2026-02/index.html",
            "<!doctype html><body><h2>no h1</h2></body>",
        )
        r = vhc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.page_count, 1)

    def test_source_view_shell_excluded(self):
        # the JS-driven source-view reader shell carries no static <h1> by
        # design and is excluded from the active-page set.
        _write(self.root, "public/index.html", CLEAN_PAGE)
        _write(
            self.root,
            "public/source/view/index.html",
            "<!doctype html><body><p>runtime-rendered shell</p></body>",
        )
        r = vhc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.page_count, 1)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vhc.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
