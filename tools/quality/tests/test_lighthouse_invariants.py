#!/usr/bin/env python3
"""Tests for the Lighthouse-invariant gate
(tools/quality/validate_lighthouse_invariants.py).

Cross `evaluate(Repo, edition)` over a fixture repo. Assert on the Result, never
on stdout. ExternalInterface runs the real `main()` against the production repo
and asserts the baseline exit code.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import json
import pathlib
import tempfile
import unittest

import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_lighthouse_invariants as vli  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

EDITION = "2026-05-09"

# a footer language-link rule that satisfies the L4 touch-target invariant via
# the legacy min-width/min-height:44px form.
FOOTER_LANG_RULE = (
    ".site-footer__language a, .site-footer__language button { min-width: 44px; min-height: 44px; }"
)
# a cite-btn rule that satisfies the L8 invariant.
CITE_BTN_RULE = ".cite-btn { min-height: 44px; }"

# an .htaccess sw.js policy block carrying the L3 directives.
HTACCESS_SW = (
    '<FilesMatch "^sw\\.js$">\n'
    "  Header set Content-Type application/javascript\n"
    "  Header set Service-Worker-Allowed /\n"
    "</FilesMatch>\n"
)


def _index_html() -> str:
    # a clean homepage: no inline handlers, correctly-closed principle titles,
    # zero font preloads, no data: urls.
    return (
        "<!doctype html><html><head>\n"
        '<script type="application/javascript" src="/js/theme.js"></script>\n'
        "</head><body>\n"
        '<h3 class="principle-title">One</h3>\n'
        '<h3 class="principle-title">Two</h3>\n'
        "</body></html>\n"
    )


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vli.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _seed_clean(self):
        # the canonical identity input.
        _write(
            self.root,
            "tools/config/identity_canonical.json",
            json.dumps({"edition": EDITION}),
        )
        # a clean homepage.
        _write(self.root, "public/index.html", _index_html())
        # the seven behaviour-scoped JS bundles, none using eval().
        for js in (
            "js/theme.js",
            "sw-register.js",
            "js/reveal.js",
            "js/verify-modal.js",
            "js/copy.js",
            "js/overlay.js",
            "js/fonts.js",
        ):
            _write(self.root, f"public/{js}", "export const ok = true;\n")
        # .htaccess sw.js policy.
        _write(self.root, "public/.htaccess", HTACCESS_SW)
        # stylesheet satisfying L4 + L8, no data: urls.
        _write(
            self.root,
            "public/styles.css",
            FOOTER_LANG_RULE + "\n" + CITE_BTN_RULE + "\n",
        )
        # the clean verification-data alias, non-empty, no dated siblings.
        _write(self.root, "public/verify/verification-data.js", "window.V = {};\n")

    def test_clean_fixture_green(self):
        self._seed_clean()
        r = vli.evaluate(self.repo, EDITION)
        self.assertTrue(r.ok, msg=r.fails)

    def test_inline_handler_caught(self):
        # defect 1 (L1): an inline onclick handler in active HTML.
        self._seed_clean()
        bad = (
            "<!doctype html><html><head></head><body>\n"
            '<button onclick="doThing()">Go</button>\n'
            "</body></html>\n"
        )
        _write(self.root, "public/privacy/index.html", bad)
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(
            any(f.startswith("L1:") and "inline event handler" in f for f in r.fails),
            r.fails,
        )

    def test_eval_usage_caught(self):
        # defect 2 (L2): an eval() call in a behaviour-scoped JS bundle.
        self._seed_clean()
        _write(self.root, "public/js/copy.js", "const x = eval('1 + 1');\n")
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(
            any(f.startswith("L2:") and "js/copy.js" in f for f in r.fails),
            r.fails,
        )

    def test_missing_sw_directives_caught(self):
        # defect 3 (L3): the sw.js block lacks Service-Worker-Allowed.
        self._seed_clean()
        _write(
            self.root,
            "public/.htaccess",
            '<FilesMatch "^sw\\.js$">\n'
            "  Header set Content-Type application/javascript\n"
            "</FilesMatch>\n",
        )
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(any("Service-Worker-Allowed" in f for f in r.fails), r.fails)

    def test_missing_js_bundle_caught(self):
        # defect (L2): one behaviour-scoped bundle is absent on disk.
        self._seed_clean()
        (self.root / "public" / "js" / "copy.js").unlink()
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(
            any(f.startswith("L2:") and "js/copy.js missing" in f for f in r.fails),
            r.fails,
        )

    def test_missing_htaccess_caught(self):
        # defect (L3): the whole .htaccess is gone.
        self._seed_clean()
        (self.root / "public" / ".htaccess").unlink()
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(any(f == "L3: .htaccess missing" for f in r.fails), r.fails)

    def test_htaccess_no_filesmatch_block_caught(self):
        # defect (L3): .htaccess present but carries no sw.js FilesMatch block.
        self._seed_clean()
        _write(self.root, "public/.htaccess", "# nothing about sw.js here\n")
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(any("no <FilesMatch sw.js> block" in f for f in r.fails), r.fails)

    def test_htaccess_missing_content_type_caught(self):
        # defect (L3): the block omits the explicit Content-Type directive.
        self._seed_clean()
        _write(
            self.root,
            "public/.htaccess",
            '<FilesMatch "^sw\\.js$">\n  Header set Service-Worker-Allowed /\n</FilesMatch>\n',
        )
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(any("missing explicit Content-Type" in f for f in r.fails), r.fails)

    def test_missing_styles_css_caught(self):
        # defect (L4): styles.css absent — the footer touch-target rule is
        # unverifiable.
        self._seed_clean()
        (self.root / "public" / "styles.css").unlink()
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(any(f == "L4: styles.css missing" for f in r.fails), r.fails)

    def test_footer_lang_rule_absent_caught(self):
        # defect (L4): styles.css present but has no footer language-link rule.
        self._seed_clean()
        _write(self.root, "public/styles.css", ".some-other-rule { color: red; }\n")
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(any("no footer language-link rule" in f for f in r.fails), r.fails)

    def test_footer_lang_rule_undersized_caught(self):
        # defect (L4): the footer rule exists but neither the 44px box nor a
        # padding-block ≥ 12px is present, so it fails the touch-target bar.
        self._seed_clean()
        _write(
            self.root,
            "public/styles.css",
            ".site-footer__language a { padding-block: 4px; }\n" + CITE_BTN_RULE + "\n",
        )
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(any("needs touch-target ≥ 44px" in f for f in r.fails), r.fails)

    def test_footer_lang_rule_padding_satisfies(self):
        # green path (L4): a padding-block ≥ 12px alone satisfies the bar.
        self._seed_clean()
        _write(
            self.root,
            "public/styles.css",
            ".site-footer__language a { padding-block: 14px; }\n" + CITE_BTN_RULE + "\n",
        )
        r = vli.evaluate(self.repo, EDITION)
        self.assertTrue(r.ok, msg=r.fails)

    def test_cite_btn_missing_min_height_caught(self):
        # defect (L8): a .cite-btn rule exists but omits min-height: 44px.
        self._seed_clean()
        _write(
            self.root,
            "public/styles.css",
            FOOTER_LANG_RULE + "\n.cite-btn { color: blue; }\n",
        )
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(any(f.startswith("L8:") and "min-height" in f for f in r.fails), r.fails)

    def test_cite_btn_absent_is_not_applicable(self):
        # green path (L8): no .cite-btn rule at all is treated as not-applicable.
        self._seed_clean()
        _write(self.root, "public/styles.css", FOOTER_LANG_RULE + "\n")
        r = vli.evaluate(self.repo, EDITION)
        self.assertTrue(r.ok, msg=r.fails)

    def test_no_edition_caught(self):
        # defect (L5): the canonical identity carries no edition string.
        self._seed_clean()
        r = vli.evaluate(self.repo, None)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("identity_canonical.json has no edition" in f for f in r.fails),
            r.fails,
        )

    def test_verification_data_alias_missing_caught(self):
        # defect (L5): the clean verification-data alias is absent.
        self._seed_clean()
        (self.root / "public" / "verify" / "verification-data.js").unlink()
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(any("verification-data.js missing" in f for f in r.fails), r.fails)

    def test_verification_data_alias_empty_caught(self):
        # defect (L5): the alias exists but is zero-length.
        self._seed_clean()
        _write(self.root, "public/verify/verification-data.js", "")
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(any("verification-data.js is empty" in f for f in r.fails), r.fails)

    def test_verification_data_dated_sibling_caught(self):
        # defect (L5): a dated verification-data sibling lingers in the tree.
        self._seed_clean()
        _write(
            self.root,
            f"public/verify/verification-data.{EDITION}.deadbeef.js",
            "window.V = {};\n",
        )
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(any("dated verification-data sibling" in f for f in r.fails), r.fails)

    def test_missing_index_caught(self):
        # defect (L6 + L7): index.html absent — both homepage checks fire.
        self._seed_clean()
        (self.root / "public" / "index.html").unlink()
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(any(f == "L7: index.html missing" for f in r.fails), r.fails)
        self.assertTrue(any(f == "L6: index.html missing" for f in r.fails), r.fails)

    def test_principle_close_tag_mismatch_caught(self):
        # defect (L7): a principle-title <h3> closes with </h2>.
        self._seed_clean()
        _write(
            self.root,
            "public/index.html",
            "<!doctype html><html><head></head><body>\n"
            '<h3 class="principle-title">One</h2>\n'
            "</body></html>\n",
        )
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(any("close with </h2>" in f for f in r.fails), r.fails)

    def test_too_many_font_preloads_caught(self):
        # defect (L6): the homepage preloads more than three first-paint fonts.
        self._seed_clean()
        preload = '<link rel="preload" as="font" href="/f{}.woff2">'
        links = "\n".join(preload.format(i) for i in range(4))
        _write(
            self.root,
            "public/index.html",
            "<!doctype html><html><head>\n" + links + "\n</head><body></body></html>\n",
        )
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(
            any(f.startswith("L6:") and "preloads 4 fonts" in f for f in r.fails),
            r.fails,
        )

    def test_data_url_in_stylesheet_caught(self):
        # defect (L9): a url(data:...) inlined into a stylesheet would be blocked
        # by the CSP img-src 'self'.
        self._seed_clean()
        _write(
            self.root,
            "public/styles.css",
            FOOTER_LANG_RULE
            + "\n"
            + CITE_BTN_RULE
            + '\n.x { background: url("data:image/svg+xml;base64,AAAA"); }\n',
        )
        r = vli.evaluate(self.repo, EDITION)
        self.assertFalse(r.ok)
        self.assertTrue(any(f.startswith("L9:") and "url(data:" in f for f in r.fails), r.fails)


class Load(unittest.TestCase):
    def test_load_returns_none_when_identity_missing(self):
        # load() over a repo with no identity_canonical.json yields None.
        with tempfile.TemporaryDirectory() as tmp:
            repo = vli.Repo(pathlib.Path(tmp))
            self.assertIsNone(vli.load(repo))


class MainRender(unittest.TestCase):
    """Drive the side-effecting adapter over a FAILING fixture so the
    fail-render branch (print + per-fail loop + rc 1) is exercised; the green
    path is covered by ExternalInterface against the real repo."""

    def test_main_returns_1_and_prints_on_failure(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            # an empty repo: load() returns None and every check fails.
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = vli.main(root)
            self.assertEqual(rc, 1)
            combined = out.getvalue() + err.getvalue()
            self.assertIn("FAIL:", combined)
            self.assertIn("Lighthouse-invariant issue(s)", combined)
            # at least one per-fail line was rendered.
            self.assertIn("✗", combined)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vli.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
