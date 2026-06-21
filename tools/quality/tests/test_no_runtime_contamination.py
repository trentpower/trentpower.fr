#!/usr/bin/env python3
"""Tests for the runtime-contamination gate
(tools/quality/validate_no_runtime_contamination.py).

Cross `evaluate(Repo)` over a fixture repo. Assert on the Result; the
ExternalInterface case runs main() against the real repo for the baseline RC.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_no_runtime_contamination as vnrc  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vnrc.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pristine_tree_green(self):
        _write(
            self.root,
            "public/index.html",
            "<!DOCTYPE html><html><body>"
            "<p>This site uses no analytics.</p>"
            '<script type="application/javascript">const x = 1;</script>'
            "</body></html>\n",
        )
        _write(self.root, "public/app.js", "const greet = () => 'hello';\n")
        r = vnrc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertFalse(r.public_missing)

    def test_google_analytics_in_html_script_caught(self):
        _write(
            self.root,
            "public/page.html",
            "<html><body><script>"
            "var s='https://www.google-analytics.com/analytics.js';"
            "</script></body></html>\n",
        )
        r = vnrc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any(label == "google-analytics" for _, _, label, _ in r.fails), r.fails)
        self.assertTrue(any(rel == "page.html" for rel, _, _, _ in r.fails), r.fails)

    def test_websocket_in_js_caught(self):
        _write(self.root, "public/live.js", "const sock = new WebSocket('wss://example.test');\n")
        r = vnrc.evaluate(self.repo)
        self.assertFalse(r.ok)
        labels = {label for _, _, label, _ in r.fails}
        # both `new WebSocket` and the `wss://` scheme fire on this line.
        self.assertIn("new WebSocket", labels)
        self.assertIn("wss:// scheme", labels)

    def test_localhost_websocket_scheme_caught(self):
        _write(self.root, "public/dev.js", "const ev = 'ws://localhost:35729/livereload';\n")
        r = vnrc.evaluate(self.repo)
        self.assertFalse(r.ok)
        labels = {label for _, _, label, _ in r.fails}
        self.assertIn("ws:// scheme", labels)
        self.assertIn("livereload", labels)

    def test_no_analytics_prose_allowlisted(self):
        # the privacy statement names google-analytics on a "no analytics"
        # line — authored prose, not runtime; the allowlist suppresses it.
        _write(
            self.root,
            "public/privacy.js",
            "// No analytics: no google-analytics, no dataLayer, ever.\n",
        )
        r = vnrc.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_missing_public_root_flagged(self):
        _write(self.root, "notpublic/x.js", "var a = 1;\n")
        r = vnrc.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(r.public_missing)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vnrc.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
