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
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_public_exposure as vpe  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent
EDITION = "2026-06-18"


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


class PureHelpers(unittest.TestCase):
    """small pure helpers — glob/url/extraction branches the fixture path
    doesn't exercise on its own."""

    def test_url_directory_non_index_is_none(self):
        allow = vpe.AllowRules(_manifest())
        self.assertIsNone(allow.url_directory("/styles.css"))

    def test_matches_versioned_glob(self):
        m = _manifest()
        m["public_versioned_globs"] = ["/v/*.js"]
        allow = vpe.AllowRules(m)
        self.assertTrue(allow.matches("/v/app.js"))

    def test_deny_basename_glob_hits(self):
        m = _manifest()
        m["deny_basename_patterns"] = ["*.bak"]
        deny = vpe.DenyRules(m)
        hits = deny.violates("/foo/x.bak", "x.bak")
        self.assertTrue(any("basename" in h for h in hits), hits)

    def test_deny_path_glob_hits(self):
        m = _manifest()
        m["deny_path_patterns"] = ["/secret/**"]
        deny = vpe.DenyRules(m)
        hits = deny.violates("/secret/key.txt", "key.txt")
        self.assertTrue(any("path matches" in h for h in hits), hits)

    def test_url_to_disk_path_requires_leading_slash(self):
        with self.assertRaises(ValueError):
            vpe.url_to_disk_path("nope")

    def test_url_to_disk_path_forms(self):
        self.assertEqual(vpe.url_to_disk_path("/"), "index.html")
        self.assertEqual(vpe.url_to_disk_path("/foo/"), "foo/index.html")
        self.assertEqual(vpe.url_to_disk_path("/foo.css"), "foo.css")

    def test_extract_urls_skips_non_internal_and_empty(self):
        html = (
            '<a href="">empty</a>'
            '<a href="#frag">frag-only</a>'
            '<a href="?q=1">query-only</a>'
            '<a href="mailto:x@y.z">mail</a>'
            '<a href="https://ext.example/">ext</a>'
            '<a href="rel/path">rel</a>'
            '<a href="/keep.css">keep</a>'
        )
        urls = vpe.extract_urls(html)
        self.assertEqual(urls, {"/keep.css"})

    def test_extract_urls_data_src_and_srcset(self):
        html = '<img data-src="/lazy.png"><img srcset="/a.png 1x, /b.png 2x">'
        urls = vpe.extract_urls(html)
        self.assertIn("/lazy.png", urls)
        self.assertIn("/a.png", urls)
        self.assertIn("/b.png", urls)

    def test_extract_urls_reversed_meta_orderings(self):
        html = (
            '<meta content="/og.png" property="og:image">'
            '<meta content="/tw.png" name="twitter:image">'
        )
        urls = vpe.extract_urls(html)
        self.assertIn("/og.png", urls)
        self.assertIn("/tw.png", urls)


class EvaluateExtra(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _make_fixture_repo(self.root)
        self.repo = vpe.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _steps(self, result):
        return {label: fails for label, fails in result.step_results}

    def test_index_html_covered_via_directory_route(self):
        # a nested index.html is allow-listed only by its directory route.
        m = _manifest()
        m["public_routes"] = ["/", "/sub/"]
        _write(self.root, "public/sub/index.html", "<p>x</p>\n")
        r = vpe.evaluate(self.repo, m, pre_archive=True)
        self.assertTrue(r.ok, msg=r.step_results)

    def test_non_iso_edition_reports_integrity_failure(self):
        m = _manifest()
        m["edition"] = "not-a-date"
        r = vpe.evaluate(self.repo, m, pre_archive=False)
        self.assertTrue(
            any("not an ISO date" in f for f in self._steps(r)["integrity artefacts"]),
            r.step_results,
        )

    def test_missing_release_artefact_link_flagged(self):
        # a page links to a .zip release artefact that does not exist on disk.
        _write(
            self.root,
            "public/index.html",
            '<a href="/downloads/edition.zip">download</a>\n',
        )
        m = _manifest()
        m["public_asset_globs"].append("/downloads/*.zip")
        r = vpe.evaluate(self.repo, m, pre_archive=True)
        self.assertFalse(r.ok)
        self.assertTrue(
            any(
                "MISSING-ARTEFACT" in f and "edition.zip" in f for f in self._steps(r)["html links"]
            ),
            r.step_results,
        )

    def test_pre_archive_tolerates_in_flight_edition_release_files(self):
        # the current edition's index.html links to its own per-edition
        # SHA256SUMS, which is not yet built at the pre-archive gate.
        rel_dir = f"integrity/releases/{EDITION}"
        _write(
            self.root,
            f"public/{rel_dir}/index.html",
            f'<a href="/{rel_dir}/SHA256SUMS">sums</a>\n',
        )
        m = _manifest()
        m["public_routes"] = ["/", f"/{rel_dir}/"]
        m["public_integrity_globs"] = [f"/{rel_dir}/**"]
        # pre_archive True: the not-yet-built SHA256SUMS under THIS edition is tolerated.
        r = vpe.evaluate(self.repo, m, pre_archive=True)
        self.assertTrue(
            all("BROKEN-LINK" not in f for f in self._steps(r)["html links"]),
            r.step_results,
        )

    def test_evaluate_with_no_edition_key(self):
        # no edition declared -> current_edition is None; html-link checks still run.
        m = _manifest()
        del m["edition"]
        r = vpe.evaluate(self.repo, m, pre_archive=True)
        # the integrity step flags the non-ISO (empty) edition, but evaluation runs.
        self.assertIsInstance(r.total_fails, int)


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

    def test_invalid_json_returns_error(self):
        _write(self.root, vpe.MANIFEST_REL, "{ not valid json ")
        manifest, errors = vpe.load(self.repo)
        self.assertIsNone(manifest)
        self.assertTrue(any("not valid JSON" in e for e in errors), errors)


class MainAdapter(unittest.TestCase):
    """drive main() — the side-effecting adapter — over fixture repos."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vpe.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_manifest(self, m):
        _write(self.root, vpe.MANIFEST_REL, json.dumps(m))

    def test_main_load_error_goes_to_stderr_and_returns_1(self):
        import contextlib
        import io

        # no manifest at all -> load() error path.
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = vpe.main(self.root, pre_archive=True)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL", err.getvalue())

    def test_main_green_over_fixture(self):
        import contextlib
        import io

        _make_fixture_repo(self.root)
        self._write_manifest(_manifest())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = vpe.main(self.root, pre_archive=True)
        self.assertEqual(rc, 0, msg=out.getvalue())
        self.assertIn("OK: public exposure validated", out.getvalue())

    def test_main_fails_and_prints_step_failures(self):
        import contextlib
        import io

        _make_fixture_repo(self.root)
        _write(self.root, "public/orphan.txt", "x\n")  # uncovered file
        self._write_manifest(_manifest())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = vpe.main(self.root, pre_archive=True)
        self.assertEqual(rc, 1)
        text = out.getvalue()
        self.assertIn("FAIL [file coverage]", text)
        self.assertIn("public-exposure issue(s)", text)

    def test_main_pre_archive_defaults_from_environment(self):
        import contextlib
        import io
        import os

        _make_fixture_repo(self.root)
        self._write_manifest(_manifest())
        old = os.environ.get("GATE_SKIP_SIGNATURE")
        os.environ["GATE_SKIP_SIGNATURE"] = "1"
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = vpe.main(self.root)  # pre_archive=None -> reads env
        finally:
            if old is None:
                os.environ.pop("GATE_SKIP_SIGNATURE", None)
            else:
                os.environ["GATE_SKIP_SIGNATURE"] = old
        self.assertEqual(rc, 0, msg=out.getvalue())


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
