#!/usr/bin/env python3
"""Tests for the changelog-freshness gate (tools/quality/validate_changelog.py).

Cross the module's interface — `evaluate(Ctx)` and `load(Repo)` — over a tiny
fixture repo. No monkeypatching; the fixture repo is the second filesystem
adapter. Tests assert on the returned Result, never on stdout.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import json
import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
for _sub in ("lib", "build", "quality", "verify"):
    sys.path.insert(0, str(TOOLS / _sub))

import validate_changelog as vc  # noqa: E402

REPO_ROOT = TOOLS.parent
EDITION = "2026-06-14"


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _make_fixture_repo(root: pathlib.Path, edition: str = EDITION, top: str = EDITION) -> None:
    _write(root, vc.IDENTITY_CANONICAL_REL, json.dumps({"edition": edition}))
    _write(root, vc.CHANGELOG_REL, f"{top} — a changelog entry\nolder stuff\n")


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vc.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_edition_matches_top_is_green(self):
        _make_fixture_repo(self.root, EDITION, EDITION)
        r = vc.evaluate(vc.load(self.repo))
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("matches edition" in o for o in r.oks), r.oks)

    def test_edition_older_than_top_is_green(self):
        _make_fixture_repo(self.root, edition="2026-06-10", top="2026-06-14")
        r = vc.evaluate(vc.load(self.repo))
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("ahead of" in o for o in r.oks), r.oks)

    def test_edition_newer_than_top_fails(self):
        _make_fixture_repo(self.root, edition="2026-06-20", top="2026-06-14")
        r = vc.evaluate(vc.load(self.repo))
        self.assertFalse(r.ok)
        self.assertTrue(any("newer than the topmost changelog" in f for f in r.fails), r.fails)

    def test_absent_inputs_skip_and_pass(self):
        # no files written — mirrors the inline skip-and-pass.
        r = vc.evaluate(vc.load(self.repo))
        self.assertTrue(r.ok)
        self.assertEqual(r.fails, [])

    def test_malformed_canon_is_a_warning_not_a_fail(self):
        _write(self.root, vc.IDENTITY_CANONICAL_REL, "{not json")
        _write(self.root, vc.CHANGELOG_REL, f"{EDITION} — entry\n")
        r = vc.evaluate(vc.load(self.repo))
        self.assertTrue(r.ok)  # never fatal
        self.assertTrue(any("did not complete" in w for w in r.warns), r.warns)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vc.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
