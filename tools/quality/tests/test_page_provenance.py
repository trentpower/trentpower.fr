#!/usr/bin/env python3
"""Tests for the page-provenance gate (tools/quality/validate_page_provenance.py).

Cross the module's interface — `load(Repo)` and `evaluate(Repo, Ctx)` — over a
tiny fixture repo. No monkeypatching; the fixture repo is the second filesystem
adapter. Tests assert on the returned Result, never on stdout. ExternalInterface
runs `main(REPO_ROOT)` and asserts the baseline exit code.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import json
import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_page_provenance as vpp  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent

REPO_URL = "https://github.com/trentpower/trentpower.fr"
BRANCH = "main"
EDITION = "2026-06-14"
BASE_URL = "https://trentpower.fr"


def _record(rel: str, source_path: str = "content/en/index.yml") -> str:
    """a coherent tp-page-record + comment for a page at public-relative rel."""
    if rel == "index.html":
        canonical = f"{BASE_URL}/"
    elif rel.endswith("/index.html"):
        canonical = f"{BASE_URL}/{rel[: -len('index.html')]}"
    else:
        canonical = f"{BASE_URL}/{rel}"
    rec = {
        "canonical": canonical,
        "sourceRepository": REPO_URL,
        "sourcePath": source_path,
        "sourceUrl": f"{REPO_URL}/blob/{BRANCH}/{source_path}",
        "edition": EDITION,
        "generated": True,
    }
    comment = (
        "<!-- provenance · page record · generated from the public source repository -->"
    )
    block = (
        '<script type="application/json" id="tp-page-record">'
        + json.dumps(rec)
        + "</script>"
    )
    return f"<!doctype html>\n<html>{comment}\n{block}\n</html>\n"


def _make_fixture_repo(root: pathlib.Path) -> None:
    """a pristine fixture: canonical identity + two coherent pages."""
    _write(
        root,
        vpp.IDENTITY_CANONICAL_REL,
        json.dumps(
            {
                "repository": {"url": REPO_URL, "branch": BRANCH},
                "edition": EDITION,
                "url": BASE_URL,
            }
        ),
    )
    _write(root, "public/index.html", _record("index.html"))
    _write(root, "public/privacy/index.html", _record("privacy/index.html"))


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vpp.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pristine_fixture_is_green(self):
        _make_fixture_repo(self.root)
        ctx, errors = vpp.load(self.repo)
        self.assertEqual(errors, [])
        r = vpp.evaluate(self.repo, ctx)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.checked, 2)
        self.assertTrue(any("carry one coherent record" in o for o in r.oks), r.oks)

    def test_missing_record_is_caught(self):
        _make_fixture_repo(self.root)
        # a page with neither comment nor tp-page-record block.
        _write(self.root, "public/orphan/index.html", "<!doctype html>\n<html></html>\n")
        ctx, errors = vpp.load(self.repo)
        self.assertEqual(errors, [])
        r = vpp.evaluate(self.repo, ctx)
        self.assertFalse(r.ok)
        self.assertTrue(any("orphan/index.html: expected 1 tp-page-record" in f for f in r.fails), r.fails)

    def test_duplicate_record_is_caught(self):
        _make_fixture_repo(self.root)
        # two record blocks (and two comments) on one page.
        doubled = _record("dup/index.html").replace("</html>", _record("dup/index.html"))
        _write(self.root, "public/dup/index.html", doubled)
        ctx, errors = vpp.load(self.repo)
        self.assertEqual(errors, [])
        r = vpp.evaluate(self.repo, ctx)
        self.assertFalse(r.ok)
        self.assertTrue(any("dup/index.html: expected 1 tp-page-record" in f for f in r.fails), r.fails)

    def test_local_path_leak_is_caught(self):
        _make_fixture_repo(self.root)
        leaky = _record("leak/index.html").replace(
            "</html>", "<!-- /home/trentpower/Desktop/x --></html>"
        )
        _write(self.root, "public/leak/index.html", leaky)
        ctx, errors = vpp.load(self.repo)
        self.assertEqual(errors, [])
        r = vpp.evaluate(self.repo, ctx)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("forbidden fragment '/home/'" in f for f in r.fails), r.fails
        )

    def test_missing_public_root_is_a_load_error(self):
        _write(
            self.root,
            vpp.IDENTITY_CANONICAL_REL,
            json.dumps(
                {"repository": {"url": REPO_URL, "branch": BRANCH}, "edition": EDITION, "url": BASE_URL}
            ),
        )
        ctx, errors = vpp.load(self.repo)
        self.assertIsNone(ctx)
        self.assertTrue(any("public root not found" in e for e in errors), errors)


class EvaluateBranches(unittest.TestCase):
    """seeded-defect tests, one per coherence branch in evaluate(). each writes
    a fixture page whose record trips exactly one check, asserting on the real
    failure that branch emits."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vpp.Repo(self.root)
        _make_fixture_repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _eval(self):
        ctx, errors = vpp.load(self.repo)
        self.assertEqual(errors, [])
        return vpp.evaluate(self.repo, ctx)

    def _page_with(self, rel: str, **overrides) -> None:
        """write a page at public/<rel> whose record carries overrides."""
        rec = {
            "canonical": f"{BASE_URL}/{rel}",
            "sourceRepository": REPO_URL,
            "sourcePath": "content/en/x.yml",
            "sourceUrl": f"{REPO_URL}/blob/{BRANCH}/content/en/x.yml",
            "edition": EDITION,
            "generated": True,
        }
        rec.update(overrides)
        comment = (
            "<!-- provenance · page record · generated from the public source repository -->"
        )
        block = (
            '<script type="application/json" id="tp-page-record">'
            + json.dumps(rec)
            + "</script>"
        )
        _write(self.root, f"public/{rel}", f"<!doctype html>\n<html>{comment}\n{block}\n</html>\n")

    def test_invalid_json_record_is_caught(self):
        comment = (
            "<!-- provenance · page record · generated from the public source repository -->"
        )
        block = '<script type="application/json" id="tp-page-record">{not json}</script>'
        _write(self.root, "public/bad/index.html", f"<html>{comment}\n{block}\n</html>\n")
        r = self._eval()
        self.assertTrue(any("not valid JSON" in f for f in r.fails), r.fails)

    def test_missing_required_keys_is_caught(self):
        comment = (
            "<!-- provenance · page record · generated from the public source repository -->"
        )
        block = (
            '<script type="application/json" id="tp-page-record">'
            + json.dumps({"canonical": f"{BASE_URL}/m/index.html"})
            + "</script>"
        )
        _write(self.root, "public/m/index.html", f"<html>{comment}\n{block}\n</html>\n")
        r = self._eval()
        self.assertTrue(any("missing keys" in f for f in r.fails), r.fails)

    def test_wrong_repository_is_caught(self):
        self._page_with("r/index.html", sourceRepository="https://example.com/other")
        r = self._eval()
        self.assertTrue(any("sourceRepository" in f for f in r.fails), r.fails)

    def test_wrong_edition_is_caught(self):
        self._page_with("e/index.html", edition="1999-01-01")
        r = self._eval()
        self.assertTrue(any("edition" in f for f in r.fails), r.fails)

    def test_generated_not_true_is_caught(self):
        self._page_with("g/index.html", generated=False)
        r = self._eval()
        self.assertTrue(any("generated must be true" in f for f in r.fails), r.fails)

    def test_absolute_source_path_is_caught(self):
        self._page_with(
            "a/index.html",
            sourcePath="/etc/passwd",
            sourceUrl=f"{REPO_URL}/blob/{BRANCH}//etc/passwd",
        )
        r = self._eval()
        self.assertTrue(any("not repository-relative" in f for f in r.fails), r.fails)

    def test_wrong_source_url_is_caught(self):
        self._page_with("u/index.html", sourceUrl="https://example.com/wrong")
        r = self._eval()
        self.assertTrue(any("sourceUrl" in f for f in r.fails), r.fails)

    def test_wrong_canonical_is_caught(self):
        self._page_with("c/index.html", canonical="https://example.com/wrong")
        r = self._eval()
        self.assertTrue(any("canonical" in f for f in r.fails), r.fails)

    def test_locale_mismatch_is_caught(self):
        # a french-tree page pointing at an english source.
        self._page_with(
            "fr/p/index.html",
            sourcePath="content/en/x.yml",
            sourceUrl=f"{REPO_URL}/blob/{BRANCH}/content/en/x.yml",
            canonical=f"{BASE_URL}/fr/p/",
        )
        r = self._eval()
        self.assertTrue(any("locale mismatch" in f for f in r.fails), r.fails)

    def test_absolute_template_path_is_caught(self):
        self._page_with("t/index.html", templatePath="/abs/template.html")
        r = self._eval()
        self.assertTrue(
            any("templatePath" in f and "not repository-relative" in f for f in r.fails),
            r.fails,
        )


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vpp.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_main_renders_evaluate_fails_and_returns_1(self):
        # point main() at a failing fixture repo: a seeded leak page makes
        # evaluate() return fails, exercising main()'s FAIL-render branch.
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture_repo(root)
            leaky = _record("leak/index.html").replace(
                "</html>", "<!-- /home/trentpower/Desktop/x --></html>"
            )
            _write(root, "public/leak/index.html", leaky)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = vpp.main(root)
        self.assertEqual(rc, 1)
        printed = out.getvalue() + err.getvalue()
        self.assertIn("FAIL: page-provenance", printed)
        self.assertIn("forbidden fragment", printed)

    def test_main_renders_load_error_and_returns_1(self):
        # a repo with no public/ root makes load() return errors, exercising
        # main()'s load-error render branch.
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(
                root,
                vpp.IDENTITY_CANONICAL_REL,
                json.dumps(
                    {
                        "repository": {"url": REPO_URL, "branch": BRANCH},
                        "edition": EDITION,
                        "url": BASE_URL,
                    }
                ),
            )
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = vpp.main(root)
        self.assertEqual(rc, 1)
        printed = out.getvalue() + err.getvalue()
        self.assertIn("public root not found", printed)


class Load(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vpp.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_incomplete_identity_is_a_load_error(self):
        # public/ present but identity missing edition/url — load() rejects it.
        _write(self.root, "public/index.html", _record("index.html"))
        _write(
            self.root,
            vpp.IDENTITY_CANONICAL_REL,
            json.dumps({"repository": {"url": REPO_URL, "branch": BRANCH}}),
        )
        ctx, errors = vpp.load(self.repo)
        self.assertIsNone(ctx)
        self.assertTrue(
            any("missing repository/edition/url" in e for e in errors), errors
        )


if __name__ == "__main__":
    unittest.main()
