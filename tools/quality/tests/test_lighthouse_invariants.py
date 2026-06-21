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
    ".site-footer__language a, .site-footer__language button "
    "{ min-width: 44px; min-height: 44px; }"
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
        self.assertTrue(
            any("Service-Worker-Allowed" in f for f in r.fails), r.fails
        )


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
