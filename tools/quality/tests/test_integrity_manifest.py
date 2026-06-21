#!/usr/bin/env python3
"""Tests for the integrity-manifest freshness gate
(tools/quality/validate_integrity_manifest.py).

Cross `evaluate(Repo, required)` over a fixture repo. The required-path set is
injected, so a tiny fixture (one file) exercises the full compute path. Assert
on the Result.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import base64
import hashlib
import json
import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_integrity_manifest as vim  # noqa: E402
from _fixture import write_bytes as _write  # noqa: E402

REPO_ROOT = TOOLS.parent


def _sha256_b64(data: bytes) -> str:
    return "sha256-" + base64.b64encode(hashlib.sha256(data).digest()).decode()


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vim.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _seed(self, body: bytes = b"hello\n"):
        _write(self.root, "public/index.html", body)
        manifest = {"files": {"index.html": _sha256_b64(body)}}
        _write(self.root, vim.MANIFEST_REL, json.dumps(manifest).encode())

    def test_matching_manifest_green(self):
        self._seed()
        r = vim.evaluate(self.repo, ["index.html"])
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.file_count, 1)

    def test_hash_drift_fails(self):
        self._seed(b"hello\n")
        _write(self.root, "public/index.html", b"tampered\n")  # bytes now differ
        r = vim.evaluate(self.repo, ["index.html"])
        self.assertFalse(r.ok)
        self.assertTrue(any("hash drift" in f for f in r.fails), r.fails)

    def test_missing_required_entry_fails(self):
        self._seed()
        r = vim.evaluate(self.repo, ["index.html", "styles.css"])
        self.assertFalse(r.ok)
        self.assertTrue(any("missing required entry for styles.css" in f for f in r.fails), r.fails)

    def test_listed_but_missing_on_disk_fails(self):
        _write(
            self.root, vim.MANIFEST_REL, json.dumps({"files": {"gone.html": "sha256-x"}}).encode()
        )
        r = vim.evaluate(self.repo, [])
        self.assertFalse(r.ok)
        self.assertTrue(any("listed but missing on disk" in f for f in r.fails), r.fails)

    def test_missing_manifest(self):
        r = vim.evaluate(self.repo, [])
        self.assertFalse(r.ok)
        self.assertTrue(r.manifest_missing)

    def test_bad_json(self):
        _write(self.root, vim.MANIFEST_REL, b"{not json")
        r = vim.evaluate(self.repo, [])
        self.assertFalse(r.ok)
        self.assertTrue(r.bad_json)

    def test_no_files_dict(self):
        _write(self.root, vim.MANIFEST_REL, json.dumps({"files": "nope"}).encode())
        r = vim.evaluate(self.repo, [])
        self.assertFalse(r.ok)
        self.assertTrue(r.no_files_dict)


class RequiredPaths(unittest.TestCase):
    def test_includes_inventory_surface(self):
        req = vim.required_paths()
        self.assertIn("index.html", req)
        self.assertTrue(any(p.startswith("en-au/") for p in req), req[:5])
        self.assertTrue(any(p.endswith("/maintenance.html") for p in req), req[-5:])


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vim.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


class MainRendering(unittest.TestCase):
    """main() is the only adapter that prints/exits. Drive each render branch
    over a tiny temp-dir fixture and assert on rc plus the printed line.

    main() calls required_paths() (the real inventory surface), so seeding a
    drift defect on a covered entry — rather than a missing required entry —
    keeps the fail set deterministic across inventory changes.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_main(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vim.main(self.root)
        return rc, buf.getvalue()

    def test_fail_render_on_hash_drift(self):
        # seed a manifest entry whose disk bytes no longer match its hash —
        # exercises the fail-render branch (the dominant uncovered path).
        _write(self.root, "public/index.html", b"hello\n")
        manifest = {"files": {"index.html": _sha256_b64(b"original\n")}}
        _write(self.root, vim.MANIFEST_REL, json.dumps(manifest).encode())
        rc, out = self._run_main()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("FAIL:", out)
        self.assertIn("freshness issue", out)
        self.assertIn("hash drift", out)

    def test_fail_render_truncates_over_50(self):
        # more than 50 fails triggers the "… and N more" truncation line.
        files = {f"gone{i}.html": "sha256-x" for i in range(60)}
        _write(self.root, vim.MANIFEST_REL, json.dumps({"files": files}).encode())
        rc, out = self._run_main()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("FAIL:", out)
        self.assertIn("more", out)

    def test_fail_render_on_manifest_missing(self):
        rc, out = self._run_main()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("integrity.json missing", out)

    def test_fail_render_on_bad_json(self):
        _write(self.root, vim.MANIFEST_REL, b"{not json")
        rc, out = self._run_main()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("not valid JSON", out)

    def test_fail_render_on_no_files_dict(self):
        _write(self.root, vim.MANIFEST_REL, json.dumps({"files": "nope"}).encode())
        rc, out = self._run_main()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("missing 'files' dict", out)


if __name__ == "__main__":
    unittest.main()
