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
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
for _sub in ("lib", "build", "quality", "verify"):
    sys.path.insert(0, str(TOOLS / _sub))

import validate_home_anchors as vha  # noqa: E402

REPO_ROOT = TOOLS.parent

_FILES = ("en-au/index.html", "fr/index.html", "js/theme.js", "sw-register.js",
          "js/reveal.js", "styles.css")


def _good_index() -> str:
    secs = "".join(f'<section id="{s}"><h2>{s}</h2></section>\n' for s in vha.SECTION_IDS)
    return f"<html><body>{secs}</body></html>\n"


def _good_styles() -> str:
    return "".join(f"#{s} {{ scroll-margin-top: 5rem; }}\n" for s in vha.SECTION_IDS)


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


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
        self.assertTrue(any("scrollIntoView" in e for e in vha.check_app_js("el.scrollIntoView();")))

    def test_app_js_clean_is_ok(self):
        self.assertEqual(vha.check_app_js("const x = 1;\n"), [])

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
                (REPO_ROOT / "public" / rel).read_text(encoding="utf-8"), encoding="utf-8")
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


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vha.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
