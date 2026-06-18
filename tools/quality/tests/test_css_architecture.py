#!/usr/bin/env python3
"""Tests for the CSS cascade-layer gate (tools/quality/validate_css_architecture.py).

The three check_* functions are already pure (css text -> list[str]); they are
the natural test surface and are exercised directly with tiny CSS strings. The
deepening added a Repo seam + evaluate()/Result for the file-loading half, tested
over a fixture repo. main() is smoked against the real repo. No monkeypatching.

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

import validate_css_architecture as css  # noqa: E402

REPO_ROOT = TOOLS.parent
CANON = css.CANONICAL_DECLARATION + "\n"


class PureChecks(unittest.TestCase):
    # -- check_print -----------------------------------------------------
    def test_print_good_is_clean(self):
        text = "@layer print-overrides {\n  @media print { body { color:#000; } }\n}\n"
        self.assertEqual(css.check_print(text), [])

    def test_print_media_outside_wrapper_fails(self):
        text = "@media print { body {} }\n@layer print-overrides {}\n"
        errs = css.check_print(text)
        self.assertTrue(any(e.startswith("L9") for e in errs), errs)

    # -- check_fonts -----------------------------------------------------
    def test_fonts_good_is_clean(self):
        text = "@layer fonts {\n  @font-face { font-family: X; }\n}\n"
        self.assertEqual(css.check_fonts(text), [])

    def test_fonts_face_outside_wrapper_fails(self):
        text = "@font-face { font-family: X; }\n@layer fonts {}\n"
        self.assertTrue(any(e.startswith("L9") for e in css.check_fonts(text)), text)

    def test_fonts_important_forbidden(self):
        text = "@layer fonts { @font-face { font-family: X !important; } }\n"
        self.assertTrue(any(e.startswith("L5") for e in css.check_fonts(text)), text)

    # -- check_styles (targeted rule breaks) -----------------------------
    def test_styles_missing_layer_declaration_fails_l1(self):
        self.assertTrue(any(e.startswith("L1") for e in css.check_styles("a{}\n")))

    def test_styles_import_forbidden_l8(self):
        text = CANON + "@import url(x.css);\n"
        self.assertTrue(any(e.startswith("L8") for e in css.check_styles(text)), text)

    def test_styles_important_budget_l5(self):
        text = CANON + "@layer base { a { " + "color:red !important; " * 19 + "} }\n"
        self.assertTrue(any(e.startswith("L5") for e in css.check_styles(text)), text)

    def test_styles_low_contrast_fails_l11(self):
        text = CANON + "@layer tokens { :root { --ink:#cccccc; --paper-main:#ffffff; } }\n"
        errs = css.check_styles(text)
        self.assertTrue(any(e.startswith("L11") and "--ink" in e for e in errs), errs)

    def test_styles_high_contrast_passes_l11_for_that_pair(self):
        text = CANON + "@layer tokens { :root { --ink:#000000; --paper-main:#ffffff; } }\n"
        errs = css.check_styles(text)
        self.assertFalse(any(e.startswith("L11") and "--ink" in e for e in errs), errs)


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        # copy the real source files so the fixture is a coherent green repo.
        for rel in (css.STYLES_REL, css.PRINT_REL, css.FONTS_REL):
            dst = self.root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text((REPO_ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
        self.repo = css.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pristine_copy_is_green(self):
        self.assertTrue(css.evaluate(self.repo).ok, msg=css.evaluate(self.repo).failures)

    def test_injected_import_breaks_evaluate(self):
        styles = self.root / css.STYLES_REL
        styles.write_text("@import url(x.css);\n" + styles.read_text(encoding="utf-8"), encoding="utf-8")
        r = css.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any(e.startswith("L8") for e in r.failures), r.failures)

    def test_missing_source_file_reported(self):
        (self.root / css.FONTS_REL).unlink()
        r = css.evaluate(self.repo)
        self.assertTrue(any("fonts-full.src.css: missing" in e for e in r.failures), r.failures)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = css.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
