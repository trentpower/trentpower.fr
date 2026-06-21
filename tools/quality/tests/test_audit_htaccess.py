#!/usr/bin/env python3
"""Tests for the focused .htaccess + CSP audit (tools/quality/audit_htaccess.py).

The compute half crosses `evaluate(Repo) -> Result` over a fixture repo; tests
assert on the Result, never on stdout. The render half (`main`) is exercised
over a fixture repo and against the real repo for the byte-exact gate contract.
No monkeypatching.

The coherent fixture embeds the live renderer output for the marker bodies and
mirrors the real public tree's path shape, so the freshness check and the
dead-allow-rule scan both go green; defects are then seeded one at a time.

Stdlib unittest — no pytest dep.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import contextlib
import io
import json
import pathlib
import tempfile
import unittest

import _fixture  # noqa: E402

_fixture.bootstrap()

import audit_htaccess as ah  # noqa: E402
import htaccess_config as cfg  # noqa: E402
from _fixture import write as _write  # noqa: E402
from generate_htaccess import (  # noqa: E402
    CSP_BEGIN,
    CSP_END,
    EXPOSURE_BEGIN,
    EXPOSURE_END,
    _render_csp_block,
    _render_exposure_block,
)
from repo import Repo  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _canonical_htaccess() -> str:
    """assemble the .htaccess exactly as generate_htaccess._replace_marker_block
    would: `{begin}\\n{body}\\n{end}` for each marker pair."""
    return (
        f"{EXPOSURE_BEGIN}\n{_render_exposure_block()}\n{EXPOSURE_END}\n"
        f"{CSP_BEGIN}\n{_render_csp_block()}\n{CSP_END}\n"
    )


def _make_fixture_repo(root: pathlib.Path) -> None:
    """a coherent repo the audit passes clean.

    - .htaccess marker bodies are the live renderer output (freshness green)
    - the public tree mirrors the real tree's path shape (release tree included),
      so every allow-rule family matches a candidate url (dead-rule scan green)
      and every real release edition keeps its full artefact set (release green)
    - the manifest's public_routes are copied verbatim (route candidates)
    - no inline scripts shipped, so the csp-hash check is vacuously green
    """
    real = Repo(REPO_ROOT)

    _write(root, "public/.htaccess", _canonical_htaccess())

    # mirror every real public path (as empty files) so the dead-allow-rule
    # scan sees the same candidate-url universe the live rules were written for,
    # and every real release edition keeps its complete artefact set.
    for repo_rel in real.glob("public/**/*"):
        rel = repo_rel[len("public/") :]
        if rel == ".htaccess":
            continue
        _write(root, f"public/{rel}", "")

    # copy the real public-exposure manifest (drives route candidates).
    manifest = real.read("tools/config/public-exposure.json")
    _write(root, "tools/config/public-exposure.json", manifest)


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _make_fixture_repo(self.root)
        self.repo = Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_coherent_fixture_is_green(self):
        r = ah.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.issues, [])
        # summary numbers are carried on the Result for the render half.
        self.assertEqual(r.n_allow_families, len(cfg.ALLOW_RULE_FAMILIES))
        self.assertGreaterEqual(r.n_editions, 1)
        self.assertEqual(r.n_hashed, 0)
        self.assertGreater(r.n_lines, 0)

    def test_missing_marker_is_caught(self):
        # drop the whole CSP block — markers imbalanced + body not found.
        text = ah._read_htaccess(self.repo)
        text = text[: text.find(CSP_BEGIN)]
        _write(self.root, "public/.htaccess", text)
        r = ah.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any(label == "markers" for label, _ in r.issues), r.fails)

    def test_marker_body_drift_is_caught(self):
        # insert a stray rule inside the exposure gate -> freshness drift.
        text = ah._read_htaccess(self.repo)
        text = text.replace(
            EXPOSURE_END,
            "  RewriteRule ^sneaky$ - [L]\n" + EXPOSURE_END,
            1,
        )
        _write(self.root, "public/.htaccess", text)
        r = ah.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any(label == "csp" for label, _ in r.issues), r.fails)

    def test_stale_csp_hash_is_caught(self):
        # ship an inline executable script whose hash is not in the config.
        _write(
            self.root,
            "public/index.html",
            "<!doctype html><script>console.log('not a declared hash')</script>",
        )
        r = ah.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any(label == "csp-hash" for label, _ in r.issues), r.fails)
        self.assertEqual(r.n_hashed, 1)

    def test_incomplete_release_is_caught(self):
        # remove a required artefact from a modern edition.
        (self.root / "public/integrity/releases/2026-05-09/SHA256SUMS").unlink()
        r = ah.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any(label == "release" for label, _ in r.issues), r.fails)
        self.assertIn("2026-05-09 missing SHA256SUMS", " ".join(r.fails))

    def test_dead_allow_rule_is_caught(self):
        # delete every public file + clear the manifest routes, so no candidate
        # url remains for the allow rules to match.
        for repo_rel in self.repo.glob("public/**/*"):
            rel = repo_rel[len("public/") :]
            if rel == ".htaccess":
                continue
            (self.root / repo_rel).unlink()
        _write(self.root, "tools/config/public-exposure.json", json.dumps({"public_routes": []}))
        r = ah.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any(label == "dead-rule" for label, _ in r.issues), r.fails)

    def test_missing_htaccess_flags_result(self):
        (self.root / "public/.htaccess").unlink()
        r = ah.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(r.htaccess_missing)
        self.assertEqual(r.issues, [])

    def test_end_marker_before_begin_is_caught(self):
        # swap the order of one marker pair so END precedes BEGIN.
        text = ah._read_htaccess(self.repo)
        text = text.replace(EXPOSURE_BEGIN, "\0B\0").replace(EXPOSURE_END, "\0E\0")
        text = text.replace("\0B\0", EXPOSURE_END).replace("\0E\0", EXPOSURE_BEGIN)
        _write(self.root, "public/.htaccess", text)
        issues = ah._check_markers(ah._read_htaccess(self.repo))
        self.assertTrue(any("end marker precedes begin" in i for i in issues), issues)


class HelperUnits(unittest.TestCase):
    """direct unit coverage for the verbatim-lifted helpers the fixture cannot
    easily drive (normalize edge, the GATE_SKIP_SIGNATURE pre-archive path)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_normalize_strips_trailing_blank_lines(self):
        self.assertEqual(ah._normalize("  a\n  b\n\n\n"), "a\nb")

    def test_pre_archive_defers_in_flight_edition(self):
        # GATE_SKIP_SIGNATURE=1: the in-flight edition needs only index.html;
        # its SHA256SUMS/.sig are deferred to the post-signature gate.
        import os

        _write(self.root, "public/integrity.json", json.dumps({"edition": "2026-07-01"}))
        _write(self.root, "public/integrity/releases/2026-07-01/index.html", "")
        prev = os.environ.get("GATE_SKIP_SIGNATURE")
        os.environ["GATE_SKIP_SIGNATURE"] = "1"
        try:
            issues, count = ah._release_completeness(self.repo)
        finally:
            if prev is None:
                os.environ.pop("GATE_SKIP_SIGNATURE", None)
            else:
                os.environ["GATE_SKIP_SIGNATURE"] = prev
        self.assertEqual(issues, [])  # index.html alone satisfies the in-flight edition.
        self.assertEqual(count, 1)


def _run_main(root: pathlib.Path) -> tuple[int, str, str]:
    """run main() over a fixture root, capturing stdout + stderr."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = ah.main(root)
    return rc, out.getvalue(), err.getvalue()


class MainRender(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _make_fixture_repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_main_ok_on_coherent_fixture(self):
        rc, out, _ = _run_main(self.root)
        self.assertEqual(rc, 0, msg=out)
        self.assertIn("htaccess audit:", out)
        self.assertIn("OK: .htaccess + CSP audit clean", out)

    def test_main_fails_on_defect_with_printed_failure(self):
        # remove a release artefact -> rc 1 + the failure printed under FAIL:.
        (self.root / "public/integrity/releases/2026-05-09/SHA256SUMS.sig").unlink()
        rc, out, _ = _run_main(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL:", out)
        self.assertIn("[release]", out)
        self.assertIn("2026-05-09 missing SHA256SUMS.sig", out)

    def test_main_missing_htaccess_returns_1_on_stderr(self):
        (self.root / "public/.htaccess").unlink()
        rc, out, err = _run_main(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("not found", err)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        rc, out, _ = _run_main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=out)
        # the byte-exact summary line the build report and the gate depend on.
        self.assertTrue(out.startswith("  htaccess audit: "), out)


if __name__ == "__main__":
    unittest.main()
