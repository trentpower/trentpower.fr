#!/usr/bin/env python3
"""Tests for the verification-data shape gate
(tools/verify/validate_verification_data.py).

Cross `evaluate(Ctx)` over a fixture record map and assert on the Result; the
ExternalInterface case runs `main(REPO_ROOT)` against the real repo and asserts
the baseline exit code.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_verification_data as vvd  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent

# a single shaped, bounded, path-safe record — the pristine baseline.
_GOOD_REC = {
    "path": "/index.html",
    "sha256": "sha256-abc123+/def=",
    "source_sha256": "sha256-ZZZ999+/=",
    "size_bytes": 1024,
    "edition": "2026-06-21",
    "validated": "2026-06-21",
}


def _data_js(records: dict) -> str:
    import json

    return f"window.TP_VERIFICATION_MAP = {json.dumps(records)};\n"


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vvd.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _load(self, records: dict) -> vvd.Ctx:
        _write(self.root, "public/verify/verification-data.js", _data_js(records))
        ctx, errors = vvd.load(self.repo)
        self.assertEqual(errors, [], msg=errors)
        self.assertIsNotNone(ctx)
        return ctx

    def test_pristine_fixture_green(self):
        ctx = self._load({"/index.html": dict(_GOOD_REC)})
        r = vvd.evaluate(ctx)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("1 record(s) shaped + bounded" in o for o in r.oks), r.oks)

    def test_path_unsafe_record_caught(self):
        rec = dict(_GOOD_REC, path="/../../etc/passwd")
        ctx = self._load({"/../../etc/passwd": rec})
        r = vvd.evaluate(ctx)
        self.assertFalse(r.ok)
        self.assertTrue(any("unsafe or malformed path" in f for f in r.fails), r.fails)

    def test_out_of_bounds_size_caught(self):
        rec = dict(_GOOD_REC, size_bytes=9_000_000)
        ctx = self._load({"/index.html": rec})
        r = vvd.evaluate(ctx)
        self.assertFalse(r.ok)
        self.assertTrue(any("size_bytes must be a positive int" in f for f in r.fails), r.fails)

    def test_malformed_date_caught(self):
        rec = dict(_GOOD_REC, edition="2026/06/21")
        ctx = self._load({"/index.html": rec})
        r = vvd.evaluate(ctx)
        self.assertFalse(r.ok)
        self.assertTrue(any("edition must be YYYY-MM-DD" in f for f in r.fails), r.fails)

    def test_key_path_mismatch_caught(self):
        ctx = self._load({"/other.html": dict(_GOOD_REC)})  # rec.path is /index.html
        r = vvd.evaluate(ctx)
        self.assertFalse(r.ok)
        self.assertTrue(any("does not match its key" in f for f in r.fails), r.fails)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vvd.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
