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

    def test_bad_source_sha256_caught(self):
        # source_sha256 present but not a sha256-<base64> value.
        rec = dict(_GOOD_REC, source_sha256="not-a-hash")
        ctx = self._load({"/index.html": rec})
        r = vvd.evaluate(ctx)
        self.assertFalse(r.ok)
        self.assertTrue(any("source_sha256 is not a valid" in f for f in r.fails), r.fails)

    def test_non_object_record_caught(self):
        # a record that is not a dict is flagged and skipped.
        ctx = self._load({"/index.html": "i am a string, not an object"})
        r = vvd.evaluate(ctx)
        self.assertFalse(r.ok)
        self.assertTrue(any("record is not an object" in f for f in r.fails), r.fails)

    def test_duplicate_record_path_caught(self):
        # a JSON dict can't hold duplicate keys, so drive evaluate() directly
        # with a mapping whose .items() yields the same key twice to exercise
        # the duplicate-path guard.
        class _DupRecords(dict):
            def items(self):
                rec = dict(_GOOD_REC)
                return [("/index.html", rec), ("/index.html", rec)]

        ctx = vvd.Ctx(records=_DupRecords())
        r = vvd.evaluate(ctx)
        self.assertFalse(r.ok)
        self.assertTrue(any("duplicate record path" in f for f in r.fails), r.fails)


class Load(unittest.TestCase):
    """load() reads + parses the one input; assert on the returned errors."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vvd.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_file_returns_error(self):
        ctx, errors = vvd.load(self.repo)
        self.assertIsNone(ctx)
        self.assertTrue(any("not found" in e for e in errors), errors)

    def test_missing_map_object_returns_error(self):
        # the file exists but carries no TP_VERIFICATION_MAP assignment.
        _write(self.root, "public/verify/verification-data.js", "// nothing here\n")
        ctx, errors = vvd.load(self.repo)
        self.assertIsNone(ctx)
        self.assertTrue(any("could not parse" in e for e in errors), errors)

    def test_invalid_json_returns_error(self):
        # the map is located but its body is not valid JSON.
        _write(
            self.root,
            "public/verify/verification-data.js",
            "window.TP_VERIFICATION_MAP = {not: valid json};\n",
        )
        ctx, errors = vvd.load(self.repo)
        self.assertIsNone(ctx)
        self.assertTrue(any("could not parse" in e for e in errors), errors)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vvd.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_main_fails_and_renders_on_shape_defect(self):
        # seed a verification-data defect, run main() over the fixture root, and
        # assert it returns 1 and prints the FAIL-render block (the shape-issue
        # summary plus a per-issue line).
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bad = dict(_GOOD_REC, size_bytes=9_000_000)  # out-of-bounds size
            _write(
                root,
                "public/verify/verification-data.js",
                _data_js({"/index.html": bad}),
            )
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vvd.main(root)

        self.assertEqual(rc, 1)
        out = buf.getvalue()
        self.assertIn("FAIL:", out)
        self.assertIn("verification-data shape issue(s):", out)
        self.assertIn("size_bytes must be a positive int", out)

    def test_main_fails_and_renders_on_load_error(self):
        # no verification-data.js at all -> main() takes the load-error branch,
        # printing the per-error FAIL line and returning 1.
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vvd.main(root)

        self.assertEqual(rc, 1)
        out = buf.getvalue()
        self.assertIn("FAIL:", out)
        self.assertIn("not found", out)


if __name__ == "__main__":
    unittest.main()
