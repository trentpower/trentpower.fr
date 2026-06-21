#!/usr/bin/env python3
"""Tests for the language-vestibule gate (tools/quality/validate_lang_gate.py).

Cross `evaluate(Repo, gate_rel)` over a fixture repo: a pristine "/" vestibule
goes green; a seeded defect (auto-redirect, missing hreflang) is caught. Tests
assert on the returned Result, never on stdout. An ExternalInterface case runs
main(REPO_ROOT) against the real repo and asserts the baseline exit code.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_lang_gate as vlg  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent

# a minimal-but-pristine vestibule that satisfies every invariant.
PRISTINE_GATE = """<!doctype html>
<html lang="en">
<head>
<meta name="robots" content="index, follow">
<link rel="canonical" href="https://trentpower.fr/">
<link rel="alternate" hreflang="en-AU" href="https://trentpower.fr/en-au/">
<link rel="alternate" hreflang="fr" href="https://trentpower.fr/fr/">
<link rel="alternate" hreflang="x-default" href="https://trentpower.fr/">
<script>var L='tp-last-edition';var v=localStorage.getItem(L);</script>
</head>
<body>
<a href="/en-au/" data-lang-choice="en">English</a>
<a href="/fr/" data-lang-choice="fr">Français</a>
</body>
</html>
"""


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vlg.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pristine_gate_is_green(self):
        _write(self.root, vlg.GATE_REL, PRISTINE_GATE)
        r = vlg.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.fails, [])
        self.assertIsNone(r.missing)

    def test_auto_redirect_is_caught(self):
        # seed an auto-redirect — the root must never bypass the choice.
        defective = PRISTINE_GATE.replace(
            "var v=localStorage.getItem(L);",
            "var v=localStorage.getItem(L);if(v)location.replace('/'+v+'/');",
        )
        _write(self.root, vlg.GATE_REL, defective)
        r = vlg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("must not auto-redirect" in f for f in r.fails), r.fails)

    def test_missing_hreflang_is_caught(self):
        defective = PRISTINE_GATE.replace('hreflang="fr"', 'hreflang="de"')
        _write(self.root, vlg.GATE_REL, defective)
        r = vlg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("missing hreflang fr" in f for f in r.fails), r.fails)

    def test_absent_vestibule_is_missing(self):
        # no file written — a load failure (missing), not an invariant fail.
        r = vlg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertEqual(r.fails, [])
        self.assertEqual(r.missing, vlg.GATE_REL)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = vlg.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue() + err.getvalue())


if __name__ == "__main__":
    unittest.main()
