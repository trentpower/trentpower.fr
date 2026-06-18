#!/usr/bin/env python3
"""Tests for the public-exposure gate (tools/quality/validate_public_exposure.py).

These cross the module's interface — `evaluate(Repo, manifest, pre_archive) ->
Result` and `load(Repo)` — over a tiny fixture repo. No monkeypatching: the
fixture repo is the second filesystem adapter and `pre_archive` is injected
(replacing the GATE_SKIP_SIGNATURE environment read), so both seams are real.
Tests assert on the returned Result, never on stdout.

Stdlib unittest — no pytest dep.

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

import validate_public_exposure as vpe  # noqa: E402

REPO_ROOT = TOOLS.parent
EDITION = "2026-06-18"


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _manifest():
    return {
        "schema": vpe.SCHEMA_TAG,
        "edition": EDITION,
        "public_routes": ["/"],
        "public_root_files": [
            "/integrity.json",
            "/integrity.json.sig",
            "/SHA256SUMS",
            "/SHA256SUMS.sig",
        ],
        "public_well_known_files": ["/.well-known/pgp-key.asc"],
        "public_asset_globs": ["/*.css"],
        "deny_extension_patterns": [".env"],
        "deny_path_patterns": ["/.git/**"],
        "deny_basename_patterns": [],
    }


def _make_fixture_repo(root: pathlib.Path) -> None:
    """A coherent public/ tree fully covered by _manifest()."""
    _write(root, "public/index.html", '<link href="/styles.css">\n')
    _write(root, "public/styles.css", "body{}\n")
    _write(root, "public/integrity.json", "{}\n")
    _write(root, "public/integrity.json.sig", "sig\n")
    _write(root, "public/SHA256SUMS", "hash\n")
    _write(root, "public/SHA256SUMS.sig", "sig\n")
    _write(root, "public/.well-known/pgp-key.asc", "key\n")


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _make_fixture_repo(self.root)
        self.repo = vpe.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _steps(self, result):
        return {label: fails for label, fails in result.step_results}

    def test_pristine_all_green(self):
        # pre_archive=True: the per-edition SHA256SUMS are not required.
        r = vpe.evaluate(self.repo, _manifest(), pre_archive=True)
        self.assertTrue(r.ok, msg=r.step_results)
        self.assertEqual(r.file_count, 7)
        self.assertGreaterEqual(r.link_count, 1)

    def test_uncovered_file_fails_coverage(self):
        _write(self.root, "public/orphan.txt", "x\n")  # no allow rule matches .txt
        r = vpe.evaluate(self.repo, _manifest(), pre_archive=True)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("orphan.txt" in f for f in self._steps(r)["file coverage"]), r.step_results
        )

    def test_denied_extension_fails_deny(self):
        # cover it with an allow glob so ONLY the deny step trips.
        m = _manifest()
        m["public_asset_globs"].append("/*.env")
        _write(self.root, "public/leak.env", "SECRET=1\n")
        r = vpe.evaluate(self.repo, m, pre_archive=True)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("leak.env" in f and "extension" in f for f in self._steps(r)["deny coverage"]),
            r.step_results,
        )

    def test_broken_internal_link_fails(self):
        _write(self.root, "public/index.html", '<a href="/nope/">x</a>\n')
        r = vpe.evaluate(self.repo, _manifest(), pre_archive=True)
        self.assertFalse(r.ok)
        self.assertTrue(any("/nope/" in f for f in self._steps(r)["html links"]), r.step_results)

    def test_missing_integrity_artefact_fails(self):
        (self.root / "public/SHA256SUMS").unlink()
        r = vpe.evaluate(self.repo, _manifest(), pre_archive=True)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("SHA256SUMS" in f for f in self._steps(r)["integrity artefacts"]), r.step_results
        )

    def test_pre_archive_flag_toggles_per_edition_requirement(self):
        # pre_archive False requires the per-edition SHA256SUMS (absent here) -> fail.
        r_strict = vpe.evaluate(self.repo, _manifest(), pre_archive=False)
        self.assertTrue(
            any(f"releases/{EDITION}" in f for f in self._steps(r_strict)["integrity artefacts"]),
            r_strict.step_results,
        )
        # pre_archive True drops that requirement -> green.
        r_lax = vpe.evaluate(self.repo, _manifest(), pre_archive=True)
        self.assertTrue(r_lax.ok, msg=r_lax.step_results)

    def test_deploy_excluded_file_is_not_validated(self):
        # a file the deploy pipeline excludes must not trip coverage/deny.
        _write(self.root, "public/CHANGES.md", "notes\n")  # uncovered by manifest
        m = _manifest()
        m["deploy_excluded_globs"] = ["/CHANGES.md"]
        r = vpe.evaluate(self.repo, m, pre_archive=True)
        self.assertTrue(r.ok, msg=r.step_results)


class Load(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vpe.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_manifest_returns_error(self):
        manifest, errors = vpe.load(self.repo)
        self.assertIsNone(manifest)
        self.assertTrue(any("not found" in e for e in errors), errors)

    def test_wrong_schema_returns_error(self):
        _write(self.root, vpe.MANIFEST_REL, json.dumps({"schema": "bogus"}))
        manifest, errors = vpe.load(self.repo)
        self.assertIsNone(manifest)
        self.assertTrue(any("schema" in e for e in errors), errors)


# the real-repo smoke needs a fully-built public/ tree; the font subsets are
# build-generated and absent in a bare checkout (CI's test job), so skip there.
_FULL_TREE = bool(list((REPO_ROOT / "public" / "fonts" / "subsets").glob("*.woff2")))


class ExternalInterface(unittest.TestCase):
    @unittest.skipUnless(_FULL_TREE, "public/ tree not fully built (font subsets absent)")
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vpe.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
