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
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

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
        styles.write_text(
            "@import url(x.css);\n" + styles.read_text(encoding="utf-8"), encoding="utf-8"
        )
        r = css.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any(e.startswith("L8") for e in r.failures), r.failures)

    def test_missing_source_file_reported(self):
        (self.root / css.FONTS_REL).unlink()
        r = css.evaluate(self.repo)
        self.assertTrue(any("fonts-full.src.css: missing" in e for e in r.failures), r.failures)


class PureChecksExtra(unittest.TestCase):
    """targeted seeded-defect cases driving the remaining check_* branches."""

    # -- _strip_block_comments -------------------------------------------
    def test_unterminated_comment_keeps_rest(self):
        # an unterminated /* … bails out and keeps the remaining text verbatim.
        out = css._strip_block_comments("a{}\n/* never closed")
        self.assertIn("a{}", out)

    # -- check_styles L1 wrong (non-canonical) declaration --------------
    def test_styles_wrong_layer_order_fails_l1(self):
        # a layer declaration that exists but is not the canonical order.
        text = "@layer tokens, reset, base;\n@layer tokens { :root {} }\n"
        errs = css.check_styles(text)
        self.assertTrue(any(e.startswith("L1") and "canonical order" in e for e in errs), errs)

    # -- check_styles L3 too many wrapper blocks ------------------------
    def test_styles_too_many_layer_blocks_fails_l3(self):
        text = CANON + ("@layer base { a {} }\n" * 4)
        errs = css.check_styles(text)
        self.assertTrue(any(e.startswith("L3") and "base" in e for e in errs), errs)

    # -- check_styles L2 skip branches: @keyframes/@page at top level ---
    def test_styles_top_level_keyframes_and_page_are_tolerated(self):
        # @keyframes and @page sit at depth 0 but are explicitly allowed.
        text = CANON + "@keyframes spin { from {} to {} }\n@page { margin: 0; }\n"
        errs = css.check_styles(text)
        self.assertFalse(any(e.startswith("L2") for e in errs), errs)

    # -- check_styles L2 top-level @media outside any layer -------------
    def test_styles_top_level_media_fails_l2(self):
        text = CANON + "@media screen { a { color: red; } }\n"
        errs = css.check_styles(text)
        self.assertTrue(any(e.startswith("L2") and "@media" in e for e in errs), errs)

    # -- check_styles L2 unexpected top-level at-rule -------------------
    def test_styles_unexpected_top_level_at_rule_fails_l2(self):
        text = CANON + "@supports (display:grid) { a {} }\n"
        errs = css.check_styles(text)
        self.assertTrue(any(e.startswith("L2") and "unexpected" in e for e in errs), errs)

    # -- check_styles L2 bare selector outside any layer ----------------
    def test_styles_selector_outside_layer_fails_l2(self):
        text = CANON + ".loose { color: red; }\n"
        errs = css.check_styles(text)
        self.assertTrue(any(e.startswith("L2") and "outside any @layer" in e for e in errs), errs)

    # -- check_styles L4 hex colour in property value is NOT an id ------
    def test_styles_hex_colour_value_is_not_id_selector(self):
        # `#faf7f0` follows `color:` on the same line — a value, not a selector.
        text = CANON + "@layer base { a { color: #faf7f0; } }\n"
        errs = css.check_styles(text)
        self.assertFalse(any(e.startswith("L4") for e in errs), errs)

    # -- check_styles L4 id selector outside overrides ------------------
    def test_styles_id_selector_outside_overrides_fails_l4(self):
        text = CANON + "@layer base {\n#main { color: red; }\n}\n"
        errs = css.check_styles(text)
        self.assertTrue(any(e.startswith("L4") and "#main" in e for e in errs), errs)

    def test_styles_id_selector_inside_overrides_is_clean(self):
        text = CANON + "@layer overrides {\n#main { color: red; }\n}\n"
        errs = css.check_styles(text)
        self.assertFalse(any(e.startswith("L4") for e in errs), errs)

    # -- check_styles L6 body[data-page] outside pages ------------------
    def test_styles_page_selector_outside_pages_fails_l6(self):
        text = CANON + '@layer base {\nbody[data-page="home"] { color: red; }\n}\n'
        errs = css.check_styles(text)
        self.assertTrue(any(e.startswith("L6") for e in errs), errs)

    # -- check_styles L7 tokens layer present but missing :root ---------
    def test_styles_tokens_missing_root_fails_l7(self):
        text = CANON + "@layer tokens { a { color: red; } }\n"
        errs = css.check_styles(text)
        self.assertTrue(any(e.startswith("L7") and ":root" in e for e in errs), errs)

    # -- check_styles L10 dark block missing a canonical token ----------
    def test_styles_dark_block_missing_token_fails_l10(self):
        # dark :root exists but omits --accent.
        text = (
            CANON
            + "@media (prefers-color-scheme: dark) { :root { --paper-main:#111; --ink:#eee; } }\n"
        )
        errs = css.check_styles(text)
        self.assertTrue(any(e.startswith("L10") and "--accent" in e for e in errs), errs)

    # -- check_print: more than one print-overrides wrapper -------------
    def test_print_multiple_wrappers_fails_l9(self):
        text = "@layer print-overrides {}\n@layer print-overrides {}\n"
        errs = css.check_print(text)
        self.assertTrue(any(e.startswith("L9") and "exactly one" in e for e in errs), errs)

    def test_print_page_outside_wrapper_fails_l9(self):
        text = "@page { margin: 0; }\n@layer print-overrides {}\n"
        errs = css.check_print(text)
        self.assertTrue(any(e.startswith("L9") and "@page" in e for e in errs), errs)

    def test_print_import_forbidden_l8(self):
        text = "@layer print-overrides { @import url(x.css); }\n"
        errs = css.check_print(text)
        self.assertTrue(any(e.startswith("L8") for e in errs), errs)

    # -- check_fonts: more than one fonts wrapper -----------------------
    def test_fonts_multiple_wrappers_fails_l9(self):
        text = "@layer fonts {}\n@layer fonts {}\n"
        errs = css.check_fonts(text)
        self.assertTrue(any(e.startswith("L9") and "exactly one" in e for e in errs), errs)

    def test_fonts_import_forbidden_l8(self):
        text = "@layer fonts { @import url(x.css); }\n"
        errs = css.check_fonts(text)
        self.assertTrue(any(e.startswith("L8") for e in errs), errs)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = css.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_main_fails_over_a_broken_fixture(self):
        # main() prints the FAIL summary to stdout and returns 1 over a repo
        # whose styles.src.css carries a forbidden @import.
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            for rel in (css.STYLES_REL, css.PRINT_REL, css.FONTS_REL):
                dst = root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text((REPO_ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
            styles = root / css.STYLES_REL
            styles.write_text(
                "@import url(x.css);\n" + styles.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = css.main(root)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL: css-architecture", buf.getvalue())

    def test_main_truncates_long_failure_lists(self):
        # >40 failures triggers the "… N more" truncation branch.
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            # styles.src.css with many id-selector violations.
            ids = "".join(f"@layer base {{\n#id{i} {{ color: red; }}\n}}\n" for i in range(45))
            (root / css.STYLES_REL).parent.mkdir(parents=True, exist_ok=True)
            (root / css.STYLES_REL).write_text(CANON + ids, encoding="utf-8")
            (root / css.PRINT_REL).write_text("@layer print-overrides {}\n", encoding="utf-8")
            (root / css.FONTS_REL).write_text("@layer fonts {}\n", encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = css.main(root)
        self.assertEqual(rc, 1)
        self.assertIn("more", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
