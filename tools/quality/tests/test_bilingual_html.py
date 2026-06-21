#!/usr/bin/env python3
"""Tests for the bilingual-HTML gate (tools/quality/validate_bilingual_html.py).

Cross `evaluate(Repo, tree_prefix)` over a fixture repo. evaluate() consults the
real content/shared/routes.yml for the page set, so the fixture seeds each route
output by copying it from the real public/ tree (mirroring test_nav_regression):
a faithful copy goes green; a seeded defect (mangled <html lang>, a runtime-i18n
leak, a dropped hreflang) is caught. Tests assert on the returned Result, never
on stdout. An ExternalInterface case runs main(REPO_ROOT) against the real repo
and asserts the baseline exit code.

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
import _fixture  # noqa: E402

_fixture.bootstrap()

import routes as routemap  # noqa: E402
import validate_bilingual_html as vbh  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _seed_real_tree(root: pathlib.Path) -> None:
    """Copy every rendered route output from the real public/ tree into the
    fixture under the same public/<route_output> path."""
    for key in routemap.route_keys():
        for lang in routemap.languages():
            rel = routemap.route_output(key, lang)
            src = REPO_ROOT / "public" / rel
            _write(root, f"public/{rel}", src.read_text(encoding="utf-8"))


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _seed_real_tree(self.root)
        self.repo = vbh.Repo(self.root)
        # a concrete first route to mutate in defect tests.
        self.first_key = routemap.route_keys()[0]
        self.first_rel = routemap.route_output(self.first_key, routemap.languages()[0])

    def tearDown(self):
        self._tmp.cleanup()

    def test_coherent_tree_is_green(self):
        r = vbh.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.fails, [])
        self.assertIsNone(r.missing)

    def test_wrong_lang_attr_is_caught(self):
        p = self.root / "public" / self.first_rel
        html = p.read_text(encoding="utf-8").replace('<html lang="', '<html lang="zz-', 1)
        p.write_text(html, encoding="utf-8")
        r = vbh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("<html lang>" in f and self.first_rel in f for f in r.fails), r.fails)

    def test_runtime_i18n_leak_is_caught(self):
        p = self.root / "public" / self.first_rel
        html = p.read_text(encoding="utf-8").replace("</body>", "<script>window.I18N={}</script></body>")
        p.write_text(html, encoding="utf-8")
        r = vbh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("runtime-i18n leak" in f for f in r.fails), r.fails)

    def test_missing_page_is_caught(self):
        (self.root / "public" / self.first_rel).unlink()
        r = vbh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("missing rendered page" in f and self.first_rel in f for f in r.fails), r.fails
        )

    def test_absent_tree_is_missing(self):
        empty = pathlib.Path(self._tmp.name) / "nope"
        empty.mkdir()
        repo = vbh.Repo(empty)
        r = vbh.evaluate(repo)
        self.assertFalse(r.ok)
        self.assertEqual(r.fails, [])
        self.assertEqual(r.missing, vbh.TREE_PREFIX)


    def test_missing_canonical_is_caught(self):
        # drop the canonical link entirely -> "no canonical" branch.
        p = self.root / "public" / self.first_rel
        html = re.sub(r'<link rel="canonical" href="[^"]+"', "", p.read_text(encoding="utf-8"), count=1)
        p.write_text(html, encoding="utf-8")
        r = vbh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("no canonical" in f and self.first_rel in f for f in r.fails), r.fails)

    def test_wrong_canonical_is_caught(self):
        # rewrite the canonical href to a bogus URL -> mismatch branch.
        p = self.root / "public" / self.first_rel
        html = re.sub(
            r'<link rel="canonical" href="[^"]+"',
            '<link rel="canonical" href="https://example.invalid/wrong"',
            p.read_text(encoding="utf-8"),
            count=1,
        )
        p.write_text(html, encoding="utf-8")
        r = vbh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("canonical" in f and "!=" in f and self.first_rel in f for f in r.fails), r.fails)

    def test_missing_hreflang_is_caught(self):
        # drop one reciprocal hreflang link -> "missing hreflang" branch.
        p = self.root / "public" / self.first_rel
        url = next(iter(routemap.hreflang_cluster(self.first_key).items()))[1]
        html = p.read_text(encoding="utf-8").replace(f'href="{url}"', 'href="https://example.invalid/dropped"')
        p.write_text(html, encoding="utf-8")
        r = vbh.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("missing hreflang" in f and self.first_rel in f for f in r.fails), r.fails)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = vbh.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue() + err.getvalue())


class MainFailRender(unittest.TestCase):
    """Drive main() over a fixture tree so its adapter branches run: the
    FAIL-render path (rc==1 + printed "✗" line) and the missing-tree path."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.first_key = routemap.route_keys()[0]
        self.first_rel = routemap.route_output(self.first_key, routemap.languages()[0])

    def tearDown(self):
        self._tmp.cleanup()

    def _run_main(self, argv):
        import contextlib
        import io

        buf = io.StringIO()
        err = io.StringIO()
        saved = sys.argv
        sys.argv = ["validate_bilingual_html.py", *argv]
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
                rc = vbh.main(self.root)
        finally:
            sys.argv = saved
        return rc, buf.getvalue(), err.getvalue()

    def test_seeded_defect_renders_fail_and_exits_1(self):
        # faithful tree, then a seeded <html lang> defect: evaluate() fails, so
        # main()'s fail-render branch must print a "✗" line and return 1.
        _seed_real_tree(self.root)
        p = self.root / "public" / self.first_rel
        html = p.read_text(encoding="utf-8").replace('<html lang="', '<html lang="zz-', 1)
        p.write_text(html, encoding="utf-8")

        rc, out, err = self._run_main([])
        self.assertEqual(rc, 1)
        text = out + err
        self.assertIn("✗", text)
        self.assertIn("bilingual HTML", text)
        self.assertIn("error(s)", text)

    def test_missing_tree_renders_run_hint_and_exits_1(self):
        # no public/ tree at all: main() takes the missing-tree branch.
        rc, out, err = self._run_main([])
        self.assertEqual(rc, 1)
        text = out + err
        self.assertIn("rendered tree not found", text)
        self.assertIn("render_pages.py", text)

    def test_root_inside_repo_resolves_prefix(self):
        # --root points at public/ inside the fixture repo: main() resolves the
        # prefix relative to repo_root and passes against a faithful tree.
        _seed_real_tree(self.root)
        rc, out, err = self._run_main(["--root", str(self.root / "public")])
        self.assertEqual(rc, 0, msg=out + err)
        self.assertIn("bilingual HTML OK", out + err)

    def test_root_outside_repo_reads_directly(self):
        # --root outside repo_root: main() falls back to Repo(root) with prefix
        # "" and reads route outputs at the tree root directly.
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        outside = pathlib.Path(other.name)
        for key in routemap.route_keys():
            for lang in routemap.languages():
                rel = routemap.route_output(key, lang)
                src = REPO_ROOT / "public" / rel
                _write(outside, rel, src.read_text(encoding="utf-8"))
        rc, out, err = self._run_main(["--root", str(outside)])
        self.assertEqual(rc, 0, msg=out + err)
        self.assertIn("bilingual HTML OK", out + err)


if __name__ == "__main__":
    unittest.main()
