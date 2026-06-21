#!/usr/bin/env python3
"""Tests for the homepage-anchor gate (tools/quality/validate_home_anchors.py).

The three check_* functions are pure (text -> errors) and tested directly. The
file-loading half crosses `evaluate(Repo) -> Result` over a fixture repo. No
monkeypatching.

Stdlib unittest — no pytest dep.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_home_anchors as vha  # noqa: E402

REPO_ROOT = TOOLS.parent

_FILES = (
    "en-au/index.html",
    "fr/index.html",
    "js/theme.js",
    "sw-register.js",
    "js/reveal.js",
    "styles.css",
)


def _good_index() -> str:
    secs = "".join(f'<section id="{s}"><h2>{s}</h2></section>\n' for s in vha.SECTION_IDS)
    return f"<html><body>{secs}</body></html>\n"


def _good_styles() -> str:
    return "".join(f"#{s} {{ scroll-margin-top: 5rem; }}\n" for s in vha.SECTION_IDS)


class PureChecks(unittest.TestCase):
    def test_index_good_is_clean(self):
        self.assertEqual(vha.check_index_html("x", _good_index()), [])

    def test_index_missing_section_fails(self):
        html = _good_index().replace('<section id="projects"><h2>projects</h2></section>\n', "")
        errs = vha.check_index_html("x", html)
        self.assertTrue(any("projects" in e and "not found" in e for e in errs), errs)

    def test_index_anchor_span_standin_fails(self):
        html = _good_index() + '<span id="approach" class="anchor-target"></span>\n'
        errs = vha.check_index_html("x", html)
        self.assertTrue(any("stand-in detected" in e for e in errs), errs)

    def test_index_duplicate_id_fails(self):
        html = _good_index() + '<div id="contact"></div>\n'
        errs = vha.check_index_html("x", html)
        self.assertTrue(any('id="contact"' in e and "must be unique" in e for e in errs), errs)

    def test_app_js_scrollintoview_banned(self):
        self.assertTrue(
            any("scrollIntoView" in e for e in vha.check_app_js("el.scrollIntoView();"))
        )

    def test_app_js_clean_is_ok(self):
        self.assertEqual(vha.check_app_js("const x = 1;\n"), [])

    def test_app_js_preventdefault_in_anchor_handler_banned(self):
        # a click handler targeting a[href^="#"] that calls preventDefault.
        js = (
            'document.addEventListener("click", function (e) {\n'
            '  const a = e.target.closest(\'a[href^="#"]\');\n'
            "  if (a) { e.preventDefault(); }\n"
            "});\n"
        )
        errs = vha.check_app_js(js)
        self.assertTrue(any("preventDefault" in e for e in errs), errs)

    def test_app_js_scrollto_in_anchor_handler_banned(self):
        # scrollTo( inside the same nav-anchor handler is also forbidden.
        js = (
            'el.addEventListener("click", function () {\n'
            "  const a = q('a[href^=\"#\"]');\n"
            "  window.scrollTo(0, 0);\n"
            "});\n"
        )
        errs = vha.check_app_js(js)
        self.assertTrue(any("scrollTo(" in e for e in errs), errs)

    def test_styles_good_is_clean(self):
        self.assertEqual(vha.check_styles_css(_good_styles()), [])

    def test_styles_missing_scroll_margin_fails(self):
        css = _good_styles().replace("#contact { scroll-margin-top: 5rem; }\n", "")
        errs = vha.check_styles_css(css)
        self.assertTrue(any("#contact" in e for e in errs), errs)


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        # copy the real source files so the fixture is a coherent green repo.
        for rel in _FILES:
            (self.root / "public" / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / "public" / rel).write_text(
                (REPO_ROOT / "public" / rel).read_text(encoding="utf-8"), encoding="utf-8"
            )
        self.repo = vha.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pristine_copy_is_green(self):
        self.assertTrue(vha.evaluate(self.repo).ok, msg=vha.evaluate(self.repo).errors)

    def test_injected_scrollintoview_breaks(self):
        p = self.root / "public/js/theme.js"
        p.write_text("el.scrollIntoView();\n" + p.read_text(encoding="utf-8"), encoding="utf-8")
        r = vha.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("scrollIntoView" in e for e in r.errors), r.errors)

    def test_missing_file_reported(self):
        (self.root / "public/styles.css").unlink()
        r = vha.evaluate(self.repo)
        self.assertTrue(any("styles.css" in e for e in r.errors), r.errors)

    def test_missing_index_html_reported(self):
        (self.root / "public/fr/index.html").unlink()
        r = vha.evaluate(self.repo)
        self.assertTrue(any("missing file: public/fr/index.html" in e for e in r.errors), r.errors)

    def test_missing_js_module_reported(self):
        (self.root / "public/js/reveal.js").unlink()
        r = vha.evaluate(self.repo)
        self.assertTrue(any("missing file: public/js/reveal.js" in e for e in r.errors), r.errors)

    def test_all_js_modules_missing_skips_app_js_scan(self):
        # when every js successor is absent, the combined scan is skipped (the
        # 200->203 false branch); the only errors are the three missing-file ones.
        for name in ("js/theme.js", "sw-register.js", "js/reveal.js"):
            (self.root / "public" / name).unlink()
        r = vha.evaluate(self.repo)
        missing = [e for e in r.errors if "missing file:" in e]
        self.assertEqual(len(missing), 3, r.errors)
        self.assertFalse(any("scrollIntoView" in e for e in r.errors), r.errors)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vha.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_main_fails_and_renders_issues_over_a_broken_fixture(self):
        # build a green fixture, inject a scroll-hijack defect, then drive main()
        # over it and assert the FAIL-render branch prints and returns 1.
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for rel in _FILES:
                dst = root / "public" / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(
                    (REPO_ROOT / "public" / rel).read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            theme = root / "public/js/theme.js"
            theme.write_text("el.scrollIntoView();\n" + theme.read_text(encoding="utf-8"), encoding="utf-8")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vha.main(root)
            out = buf.getvalue()
        self.assertEqual(rc, 1, out)
        self.assertIn("FAIL: home-anchors", out)
        self.assertIn("scrollIntoView", out)


if __name__ == "__main__":
    unittest.main()
