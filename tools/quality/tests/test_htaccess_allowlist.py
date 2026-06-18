#!/usr/bin/env python3
"""Tests for the .htaccess allow-list gate (tools/quality/validate_htaccess_allowlist.py).

The per-url rule simulation (`classify`) is pure and tested directly. The
file-loading half crosses `load(Repo)` / `evaluate(Repo, ctx) -> Result` over a
fixture repo. No monkeypatching.

Stdlib unittest — no pytest dep.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import re
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
for _sub in ("lib", "build", "quality", "verify"):
    sys.path.insert(0, str(TOOLS / _sub))

import validate_htaccess_allowlist as vha  # noqa: E402

REPO_ROOT = TOOLS.parent

GATE = """\
# BEGIN PUBLIC EXPOSURE
RewriteRule ^$ - [L]
RewriteRule ^index\\.html$ - [L]
RewriteRule ^assets/ - [L]
# END PUBLIC EXPOSURE
"""


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _make_fixture_repo(root: pathlib.Path) -> None:
    _write(root, "public/.htaccess", GATE)
    _write(root, "public/index.html", "<p>home</p>\n")
    _write(root, "public/assets/app.css", "body{}\n")


class Classify(unittest.TestCase):
    def test_allow(self):
        rules = [(re.compile(r"^index\.html$"), "L")]
        self.assertEqual(vha.classify("/index.html", rules), "allow")

    def test_deny(self):
        rules = [(re.compile(r"^secret"), "F,L")]
        self.assertEqual(vha.classify("/secret.json", rules), "deny")

    def test_fallthrough(self):
        rules = [(re.compile(r"^index"), "L")]
        self.assertEqual(vha.classify("/nope.txt", rules), "fallthrough")

    def test_first_match_wins(self):
        rules = [(re.compile(r"^a"), "L"), (re.compile(r"^a"), "F")]
        self.assertEqual(vha.classify("/a.html", rules), "allow")


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _make_fixture_repo(self.root)
        self.repo = vha.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pristine_all_allowed(self):
        ctx, errors = vha.load(self.repo)
        self.assertEqual(errors, [])
        r = vha.evaluate(self.repo, ctx)
        self.assertTrue(r.ok, msg=(r.denied, r.fallthrough))
        self.assertEqual(r.rule_count, 3)

    def test_uncovered_file_falls_through(self):
        _write(self.root, "public/orphan.txt", "x\n")  # no rule matches
        ctx, _ = vha.load(self.repo)
        r = vha.evaluate(self.repo, ctx)
        self.assertFalse(r.ok)
        self.assertIn("/orphan.txt", r.fallthrough)

    def test_denied_file_is_reported(self):
        _write(self.root, "public/.htaccess",
               GATE.replace("# END", "RewriteRule ^secret - [F,L]\n# END"))
        _write(self.root, "public/secret.json", "{}\n")
        ctx, _ = vha.load(self.repo)
        r = vha.evaluate(self.repo, ctx)
        self.assertFalse(r.ok)
        self.assertIn("/secret.json", r.denied)


class Load(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vha.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_htaccess_errors(self):
        ctx, errors = vha.load(self.repo)
        self.assertIsNone(ctx)
        self.assertTrue(errors)

    def test_missing_gate_markers_errors(self):
        _write(self.root, "public/.htaccess", "RewriteRule ^x$ - [L]\n")  # no BEGIN/END
        ctx, errors = vha.load(self.repo)
        self.assertIsNone(ctx)
        self.assertTrue(any("rewrite gate block" in e for e in errors), errors)

    def test_empty_gate_errors(self):
        _write(self.root, "public/.htaccess", "# BEGIN PUBLIC EXPOSURE\n# END PUBLIC EXPOSURE\n")
        ctx, errors = vha.load(self.repo)
        self.assertIsNone(ctx)
        self.assertTrue(any("no RewriteRule" in e for e in errors), errors)


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
