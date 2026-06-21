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


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vpp.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
