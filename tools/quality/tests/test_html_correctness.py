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
            "<!doctype html><html><head></head><body><h1>Title</h1><h2>Section</h3></body></html>\n"
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
        self.assertTrue(any("exactly one visible <h1>" in err for _rel, err in r.fails), r.fails)

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

    def test_h1_inside_aria_hidden_caught(self):
        # an <h1> inside an aria-hidden="true" subtree is banned (print-only
        # titles must be <p>). also leaves zero visible <h1>.
        bad = (
            "<!doctype html><html><head></head><body>"
            "<h1>Title</h1>"
            '<section aria-hidden="true"><h1>Print Title</h1></section>'
            "</body></html>\n"
        )
        _write(self.root, "public/index.html", bad)
        r = vhc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any('inside an aria-hidden="true" subtree' in err for _rel, err in r.fails),
            r.fails,
        )

    def test_heading_close_with_no_open_caught(self):
        # a stray </h2> with no matching open tag.
        bad = "<!doctype html><html><head></head><body><h1>Title</h1></h2></body></html>\n"
        _write(self.root, "public/index.html", bad)
        r = vhc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("with no matching open" in err for _rel, err in r.fails), r.fails)

    def test_anchor_with_aria_label_is_clean(self):
        # an icon-only anchor that declares aria-label is allowed — exercises
        # the skip arm of the empty-anchor check.
        good = (
            "<!doctype html><html><head>"
            '<link rel="canonical" href="https://trentpower.fr/">'
            '<meta name="description" content="x">'
            '<meta property="og:title" content="x">'
            '<meta property="og:url" content="https://trentpower.fr/">'
            "</head><body>"
            "<h1>Title</h1>"
            '<a href="/x" aria-label="search"></a>'
            "</body></html>\n"
        )
        _write(self.root, "public/index.html", good)
        r = vhc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_empty_anchor_inside_aria_hidden_is_clean(self):
        # an empty anchor nested in an aria-hidden subtree is exempt from the
        # accessible-name rule.
        good = (
            "<!doctype html><html><head>"
            '<link rel="canonical" href="https://trentpower.fr/">'
            '<meta name="description" content="x">'
            '<meta property="og:title" content="x">'
            '<meta property="og:url" content="https://trentpower.fr/">'
            "</head><body>"
            "<h1>Title</h1>"
            '<span aria-hidden="true"><a href="/x"></a></span>'
            "</body></html>\n"
        )
        _write(self.root, "public/index.html", good)
        r = vhc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_mismatched_nesting_unwinds_aria_hidden(self):
        # an aria-hidden frame left open when its parent closes forces the
        # end-tag handler to unwind intermediate frames (the while-loop arm).
        good = (
            "<!doctype html><html><head>"
            '<link rel="canonical" href="https://trentpower.fr/">'
            '<meta name="description" content="x">'
            '<meta property="og:title" content="x">'
            '<meta property="og:url" content="https://trentpower.fr/">'
            "</head><body>"
            "<h1>Title</h1>"
            '<div><span aria-hidden="true"><b>x</b></div>'
            '<a href="/y">visible</a>'
            "</body></html>\n"
        )
        _write(self.root, "public/index.html", good)
        r = vhc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_duplicate_id_via_self_closing_caught(self):
        # two self-closing elements sharing an id exercise the
        # handle_startendtag duplicate-id branch.
        bad = (
            "<!doctype html><html><head></head><body>"
            "<h1>Title</h1>"
            '<input id="dup"/><input id="dup"/>'
            "</body></html>\n"
        )
        _write(self.root, "public/index.html", bad)
        r = vhc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("duplicate id" in err for _rel, err in r.fails), r.fails)

    def test_self_closing_unique_id_is_clean(self):
        # a self-closing element with a fresh id records it without error
        # (the else arm of handle_startendtag).
        good = (
            "<!doctype html><html><head>"
            '<link rel="canonical" href="https://trentpower.fr/">'
            '<meta name="description" content="x">'
            '<meta property="og:title" content="x">'
            '<meta property="og:url" content="https://trentpower.fr/">'
            "</head><body>"
            "<h1>Title</h1>"
            '<input id="solo"/>'
            "</body></html>\n"
        )
        _write(self.root, "public/index.html", good)
        r = vhc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_duplicate_canonical_caught(self):
        bad = (
            "<!doctype html><html><head>"
            '<link rel="canonical" href="https://trentpower.fr/">'
            '<link rel="canonical" href="https://trentpower.fr/x">'
            "</head><body><h1>Title</h1></body></html>\n"
        )
        _write(self.root, "public/index.html", bad)
        r = vhc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("duplicate <link rel=canonical>" in err for _rel, err in r.fails),
            r.fails,
        )

    def test_duplicate_description_caught(self):
        bad = (
            "<!doctype html><html><head>"
            '<meta name="description" content="a">'
            '<meta name="description" content="b">'
            "</head><body><h1>Title</h1></body></html>\n"
        )
        _write(self.root, "public/index.html", bad)
        r = vhc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("duplicate <meta name=description>" in err for _rel, err in r.fails),
            r.fails,
        )

    def test_duplicate_og_title_caught(self):
        bad = (
            "<!doctype html><html><head>"
            '<meta property="og:title" content="a">'
            '<meta property="og:title" content="b">'
            "</head><body><h1>Title</h1></body></html>\n"
        )
        _write(self.root, "public/index.html", bad)
        r = vhc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("duplicate <meta property=og:title>" in err for _rel, err in r.fails),
            r.fails,
        )

    def test_duplicate_og_url_caught(self):
        bad = (
            "<!doctype html><html><head>"
            '<meta property="og:url" content="https://trentpower.fr/">'
            '<meta property="og:url" content="https://trentpower.fr/x">'
            "</head><body><h1>Title</h1></body></html>\n"
        )
        _write(self.root, "public/index.html", bad)
        r = vhc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("duplicate <meta property=og:url>" in err for _rel, err in r.fails),
            r.fails,
        )

    def test_missing_file_reported(self):
        # a stale Repo discovers the page set, then the file is unlinked before
        # evaluate reads it: the rel survives in the active set computed from a
        # warm glob, but is_file() is now false. we model this directly by
        # subclassing Repo so glob still reports the page after it is gone.
        _write(self.root, "public/index.html", CLEAN_PAGE)
        ghost = "public/ghost/index.html"
        _write(self.root, ghost, CLEAN_PAGE)
        (self.root / ghost).unlink()

        class _StaleRepo(vhc.Repo):
            def glob(self, pattern):
                base = super().glob(pattern)
                # re-add the now-deleted page so discovery still yields it.
                return sorted({*base, "public/ghost/index.html"})

        r = vhc.evaluate(_StaleRepo(self.root))
        self.assertFalse(r.ok)
        self.assertTrue(any(err == "missing" for _rel, err in r.fails), r.fails)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vhc.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_main_fails_and_renders_over_a_defective_fixture(self):
        # main() over a fixture repo with a structural defect: returns 1 and
        # prints the FAIL block with the per-page error line.
        import contextlib
        import io

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        _write(root, "public/index.html", CLEAN_PAGE)
        _write(
            root,
            "public/broken/index.html",
            "<!doctype html><html><head></head><body>"
            "<h1>Title</h1><h2>Section</h3>"
            "</body></html>\n",
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vhc.main(root)
        out = buf.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("FAIL: html-correctness", out)
        self.assertIn("heading mismatch", out)

    def test_main_truncates_long_fail_lists(self):
        # more than 40 issues triggers the "… N more" truncation tail.
        import contextlib
        import io

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        # each defective page contributes one fail (zero visible h1).
        zero_h1 = "<!doctype html><html><head></head><body><p>x</p></body></html>\n"
        for i in range(45):
            _write(root, f"public/p{i}/index.html", zero_h1)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vhc.main(root)
        out = buf.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("more", out)

    def test_main_missing_public_root(self):
        # a repo root with no public/ dir short-circuits to the FAIL guard.
        import contextlib
        import io

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vhc.main(root)
        out = buf.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("public root not found", out)


if __name__ == "__main__":
    unittest.main()
