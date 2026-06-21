#!/usr/bin/env python3
"""Tests for the nav-regression gate (tools/quality/validate_nav_regression.py).

The four check_* functions are pure (text -> errors) and tested directly. The
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

import validate_nav_regression as vnr  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent
_SECTIONS = ("approach", "credentials", "trajectory", "projects", "contact")
_PUBLIC_FILES = (
    "js/theme.js",
    "sw-register.js",
    "js/reveal.js",
    "en-au/index.html",
    "fr/index.html",
    "styles.css",
)


def _good_index() -> str:
    secs = "".join(f'<section id="{s}"><h2>{s}</h2></section>\n' for s in _SECTIONS)
    return (
        '<header class="site-header"><div class="nav">'
        '<a class="nav-mark">Trent Power</a></div></header>\n' + secs
    )


class PureChecks(unittest.TestCase):
    def test_app_js_clean_ok(self):
        self.assertEqual(vnr.check_app_js("const x = 1;\n"), [])

    def test_app_js_data_nav_state_banned(self):
        self.assertTrue(
            any(
                "data-nav-state" in e
                for e in vnr.check_app_js('el.setAttribute("data-nav-state","x")')
            )
        )

    def test_index_good_ok(self):
        self.assertEqual(vnr.check_index_html("x", _good_index()), [])

    def test_index_nav_toggle_back_fails(self):
        html = _good_index() + '<button class="nav-toggle"></button>\n'
        self.assertTrue(
            any("nav-toggle markup is back" in e for e in vnr.check_index_html("x", html))
        )

    def test_index_missing_section_fails(self):
        html = _good_index().replace('<section id="contact"><h2>contact</h2></section>\n', "")
        self.assertTrue(
            any("contact" in e and "not found" in e for e in vnr.check_index_html("x", html))
        )

    def test_styles_css_nav_toggle_selector_fails(self):
        self.assertTrue(
            any(".nav-toggle" in e for e in vnr.check_styles_css(".nav-toggle { display:none; }\n"))
        )

    def test_styles_css_clean_ok(self):
        self.assertEqual(vnr.check_styles_css("body{}\n"), [])

    def test_styles_src_nav_links_selector_fails(self):
        self.assertTrue(
            any(".nav-links" in e for e in vnr.check_styles_src(".nav-links { gap:1rem; }\n"))
        )


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        for rel in _PUBLIC_FILES:
            _write(
                self.root, f"public/{rel}", (REPO_ROOT / "public" / rel).read_text(encoding="utf-8")
            )
        _write(
            self.root,
            "styles/styles.src.css",
            (REPO_ROOT / "styles" / "styles.src.css").read_text(encoding="utf-8"),
        )
        self.repo = vnr.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pristine_copy_is_green(self):
        self.assertTrue(vnr.evaluate(self.repo).ok, msg=vnr.evaluate(self.repo).errors)

    def test_injected_data_nav_state_breaks(self):
        p = self.root / "public/js/theme.js"
        p.write_text(
            'el.setAttribute("data-nav-state","open");\n' + p.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        r = vnr.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("data-nav-state" in e for e in r.errors), r.errors)

    def test_missing_src_file_reported(self):
        (self.root / "styles/styles.src.css").unlink()
        r = vnr.evaluate(self.repo)
        self.assertTrue(any("styles.src.css" in e for e in r.errors), r.errors)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vnr.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
