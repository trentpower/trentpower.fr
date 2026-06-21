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
import sys
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

    def _evaluate(self, defective):
        _write(self.root, vlg.GATE_REL, defective)
        return vlg.evaluate(self.repo)

    def test_missing_robots_meta_is_caught(self):
        # strip the index,follow robots meta — the vestibule is the
        # indexable x-default gate, so its absence must fail.
        defective = PRISTINE_GATE.replace('<meta name="robots" content="index, follow">', "")
        r = self._evaluate(defective)
        self.assertTrue(any("missing <meta robots" in f for f in r.fails), r.fails)

    def test_missing_canonical_is_caught(self):
        # drop the self-canonical link — the vestibule must canonical to itself.
        defective = PRISTINE_GATE.replace(
            '<link rel="canonical" href="https://trentpower.fr/">', ""
        )
        r = self._evaluate(defective)
        self.assertTrue(any("self-canonical" in f for f in r.fails), r.fails)

    def test_missing_storage_read_is_caught(self):
        # remove the pre-paint localStorage read — the boot script must read
        # the stored edition to set the display language.
        defective = PRISTINE_GATE.replace(
            "<script>var L='tp-last-edition';var v=localStorage.getItem(L);</script>",
            "",
        )
        r = self._evaluate(defective)
        self.assertTrue(any("does not read localStorage" in f for f in r.fails), r.fails)

    def test_missing_en_au_choice_is_caught(self):
        # remove the english <a> choice — the vestibule must offer a real link.
        defective = PRISTINE_GATE.replace('<a href="/en-au/" data-lang-choice="en">English</a>', "")
        r = self._evaluate(defective)
        self.assertTrue(any("no <a href=/en-au/" in f for f in r.fails), r.fails)

    def test_missing_fr_choice_is_caught(self):
        # remove the french <a> choice — the vestibule must offer a real link.
        defective = PRISTINE_GATE.replace('<a href="/fr/" data-lang-choice="fr">Français</a>', "")
        r = self._evaluate(defective)
        self.assertTrue(any("no <a href=/fr/" in f for f in r.fails), r.fails)


class ExternalInterface(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_main(self):
        # call main against the fixture root, capturing both streams — the
        # fail/missing branches print to stderr, the ok line to stdout.
        import contextlib
        import io

        buf = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = vlg.main(self.root)
        return rc, buf.getvalue(), err.getvalue()

    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = vlg.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue() + err.getvalue())

    def test_main_renders_ok_line_on_green_fixture(self):
        # a pristine fixture drives main() down the ok path: rc 0, ok line on stdout.
        _write(self.root, vlg.GATE_REL, PRISTINE_GATE)
        rc, out, err = self._run_main()
        self.assertEqual(rc, 0, msg=err)
        self.assertIn("language vestibule OK", out)
        self.assertEqual(err, "")

    def test_main_renders_fails_to_stderr(self):
        # a defective vestibule (auto-redirect) drives main() down the
        # fail-render branch: rc 1, each fail printed to stderr.
        defective = PRISTINE_GATE.replace(
            "var v=localStorage.getItem(L);",
            "var v=localStorage.getItem(L);if(v)location.replace('/'+v+'/');",
        )
        _write(self.root, vlg.GATE_REL, defective)
        rc, out, err = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("✗", err)
        self.assertIn("language vestibule", err)
        self.assertIn("error(s)", err)
        self.assertEqual(out, "")

    def test_main_reports_missing_vestibule(self):
        # no index.html written — main() takes the missing branch: rc 1,
        # the "vestibule not found" run-hint printed to stderr.
        rc, out, err = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("vestibule not found", err)
        self.assertIn("render_pages.py", err)
        self.assertEqual(out, "")

    def _run_main_with_argv(self, argv):
        # drive main() through the argv-parsing path (the --root option).
        import contextlib
        import io

        buf = io.StringIO()
        err = io.StringIO()
        saved = sys.argv
        sys.argv = ["validate_lang_gate.py", *argv]
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
                rc = vlg.main(REPO_ROOT)
        finally:
            sys.argv = saved
        return rc, buf.getvalue(), err.getvalue()

    def test_main_root_outside_repo_tree_reads_its_own_root(self):
        # --root points at a fixture under /tmp — outside REPO_ROOT — so main()
        # takes the ValueError fallback and reads index.html via its own Repo.
        # a green fixture there drives the ok path.
        _write(self.root, "index.html", PRISTINE_GATE)
        rc, out, err = self._run_main_with_argv(["--root", str(self.root)])
        self.assertEqual(rc, 0, msg=err)
        self.assertIn("language vestibule OK", out)

    def test_main_root_outside_repo_tree_catches_defect(self):
        # the same out-of-tree --root path, but with a defective fixture: the
        # fail-render branch fires through the argv adapter.
        defective = PRISTINE_GATE.replace('hreflang="fr"', 'hreflang="de"')
        _write(self.root, "index.html", defective)
        rc, out, err = self._run_main_with_argv(["--root", str(self.root)])
        self.assertEqual(rc, 1)
        self.assertIn("missing hreflang fr", err)


if __name__ == "__main__":
    unittest.main()
