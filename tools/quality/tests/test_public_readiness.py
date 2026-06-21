#!/usr/bin/env python3
"""Tests for the public-repo posture gate
(tools/quality/validate_public_readiness.py).

Cross `evaluate(repo, proc, full=...)` over a fixture repo + a FakeProc that
returns the git outputs the checks expect. Assert on the Result.

The ExternalInterface case runs the real `main()` against the real repo to
pin the OK/RC text contract.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import datetime
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

import _fixture

_fixture.bootstrap()

import validate_public_readiness as vpr  # noqa: E402
from _fixture import FakeProc, proc_result  # noqa: E402
from _fixture import write as _write  # noqa: E402
from _fixture import write_bytes as _write_bytes  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

# the declared facts the validator reads. kept minimal but coherent: one
# required root file, one font glob, one declared font.
_CONFIG = {
    "font_policy": "untracked",
    "required_root_files": ["LICENSE"],
    "forbidden_readme_phrases": ["Private. Not open source"],
    "untracked_font_globs": ["public/fonts/*.woff2"],
    "untracked_internal_records": ["reports/secret.txt"],
    "secret_scan_max_age_days": 7,
}


def _build_fixture(root: pathlib.Path) -> None:
    """A pristine fixture repo: config, the required root files, the README,
    .gitattributes, the exclusions manifest, and the one declared font on
    disk so on-disk and declared agree."""
    _write(root, vpr.CONFIG_REL, json.dumps(_CONFIG))
    _write(root, "LICENSE", "MIT License\n\nPermission is hereby granted ...")
    _write(root, "README.md", "See LICENSE and CONTENT-RIGHTS.md for terms.")
    _write(root, ".gitattributes", "public/** linguist-generated\n")
    _write(
        root,
        vpr.EXCLUSIONS_REL,
        json.dumps({"files": [{"path": "public/fonts/serif.woff2"}]}),
    )
    # the declared font present on disk so declared == on_disk.
    _write(root, "public/fonts/serif.woff2", "binary-ish")


def _green_proc() -> FakeProc:
    """A FakeProc whose handler returns the git outputs that make a pristine
    fixture pass: nothing forbidden tracked, no licensed fonts tracked, no
    internal records tracked."""

    def handler(argv, cwd, env):
        # everything is empty -> nothing forbidden is tracked.
        return proc_result(0, "")

    return FakeProc(handler)


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _build_fixture(self.root)
        self.repo = vpr.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pristine_fixture_green(self):
        r = vpr.evaluate(self.repo, _green_proc())
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.fails, [])

    def test_node_modules_tracked_caught(self):
        # FakeProc reports node_modules has a tracked entry.
        def handler(argv, cwd, env):
            if argv[:3] == ["git", "ls-files", "node_modules"]:
                return proc_result(0, "node_modules/left-pad/index.js\n")
            return proc_result(0, "")

        r = vpr.evaluate(self.repo, FakeProc(handler))
        self.assertFalse(r.ok)
        self.assertIn("node_modules is tracked", r.fails)

    def test_tracked_licensed_font_caught(self):
        # FakeProc reports the licensed font glob has a tracked entry.
        def handler(argv, cwd, env):
            if argv[:3] == ["git", "ls-files", "--"] and "public/fonts/*.woff2" in argv:
                return proc_result(0, "public/fonts/serif.woff2\n")
            return proc_result(0, "")

        r = vpr.evaluate(self.repo, FakeProc(handler))
        self.assertFalse(r.ok)
        self.assertTrue(
            any("licensed font binaries are tracked" in f for f in r.fails), msg=r.fails
        )

    def _ls_files_proc(self, *tracked: str) -> FakeProc:
        """A green-ish FakeProc whose `git ls-files -z` lists the given files."""

        def handler(argv, cwd, env):
            if argv[:3] == ["git", "ls-files", "-z"]:
                return proc_result(0, "\0".join(tracked))
            return proc_result(0, "")

        return FakeProc(handler)

    def test_deploy_metadata_in_tracked_source_caught(self):
        # a tracked recipe with a literal sftp host + lftp open directive.
        _write(
            self.root,
            "tools/release/deploy.sftp.lftp",
            'open -u "acct-123" sftp://sftp.sd3.gpaas.net\n',
        )
        r = vpr.evaluate(self.repo, self._ls_files_proc("tools/release/deploy.sftp.lftp"))
        self.assertFalse(r.ok)
        self.assertTrue(
            any("deployment metadata in tracked source" in f for f in r.fails), msg=r.fails
        )

    def test_template_path_is_allowlisted(self):
        # the template carries `open -u` but is an allowlisted path -> not flagged.
        _write(
            self.root,
            "tools/release/deploy.sftp.lftp.template",
            'open -u "${SFTP_USERNAME}" sftp://${SFTP_HOST}\n',
        )
        r = vpr.evaluate(self.repo, self._ls_files_proc("tools/release/deploy.sftp.lftp.template"))
        self.assertTrue(r.ok, msg=r.fails)

    def test_env_placeholder_form_not_flagged(self):
        # a doc using ${VAR}/$VAR placeholders (not literals) must pass.
        _write(self.root, "docs/DEPLOY.md", "connect: sftp://${SFTP_HOST} as $SFTP_USERNAME\n")
        r = vpr.evaluate(self.repo, self._ls_files_proc("docs/DEPLOY.md"))
        self.assertTrue(r.ok, msg=r.fails)

    def test_required_root_file_missing_caught(self):
        # delete the one required root file -> the present/non-empty check fails.
        (self.root / "LICENSE").unlink()
        r = vpr.evaluate(self.repo, _green_proc())
        self.assertFalse(r.ok)
        self.assertIn("required root file missing or empty: LICENSE", r.fails)

    def test_required_root_file_empty_caught(self):
        # a present-but-empty required root file fails the size() guard.
        _write(self.root, "LICENSE", "")
        r = vpr.evaluate(self.repo, _green_proc())
        self.assertFalse(r.ok)
        self.assertIn("required root file missing or empty: LICENSE", r.fails)

    def test_license_without_mit_text_caught(self):
        # LICENSE present and non-empty but lacking the MIT phrase.
        _write(self.root, "LICENSE", "Copyright only, no licence grant here.\n")
        r = vpr.evaluate(self.repo, _green_proc())
        self.assertFalse(r.ok)
        self.assertIn("LICENSE does not contain the MIT License text", r.fails)

    def test_content_rights_without_cc_text_caught(self):
        # CONTENT-RIGHTS.md present but does not name the CC BY-SA licence.
        _write(self.root, "CONTENT-RIGHTS.md", "All rights reserved.\n")
        r = vpr.evaluate(self.repo, _green_proc())
        self.assertFalse(r.ok)
        self.assertIn("CONTENT-RIGHTS.md does not name CC BY-SA 4.0", r.fails)

    def test_forbidden_readme_phrase_caught(self):
        # the README carries a forbidden private-repo claim.
        _write(
            self.root,
            "README.md",
            "Private. Not open source\nSee LICENSE and CONTENT-RIGHTS.md.",
        )
        r = vpr.evaluate(self.repo, _green_proc())
        self.assertFalse(r.ok)
        self.assertTrue(any("still claims" in f for f in r.fails), msg=r.fails)

    def test_readme_missing_licence_reference_caught(self):
        # the README references neither licence file.
        _write(self.root, "README.md", "A readme with no licence pointers.")
        r = vpr.evaluate(self.repo, _green_proc())
        self.assertFalse(r.ok)
        self.assertIn("README.md does not reference LICENSE", r.fails)
        self.assertIn("README.md does not reference CONTENT-RIGHTS.md", r.fails)

    def test_gitattributes_lost_marker_caught(self):
        # .gitattributes present but missing the linguist-generated marker.
        _write(self.root, ".gitattributes", "*.png binary\n")
        r = vpr.evaluate(self.repo, _green_proc())
        self.assertFalse(r.ok)
        self.assertIn(
            ".gitattributes lost the public/** linguist-generated marker", r.fails
        )

    def test_forbidden_filename_tracked_caught(self):
        # a tracked file whose basename is in FORBIDDEN_NAMES (e.g. an .env file).
        forbidden = next(iter(vpr.FORBIDDEN_NAMES))
        rel = f"some/dir/{forbidden}"
        r = vpr.evaluate(self.repo, self._ls_files_proc(rel))
        self.assertFalse(r.ok)
        self.assertIn(f"forbidden filename tracked: {rel}", r.fails)

    def test_deploy_scan_skips_non_utf8_tracked_file(self):
        # a tracked scannable-suffix file with non-utf8 bytes is skipped, not
        # crashed on: the UnicodeDecodeError branch continues past it.
        _write_bytes(self.root, "tools/release/blob.sh", b"\xff\xfe not utf8\n")
        r = vpr.evaluate(self.repo, self._ls_files_proc("tools/release/blob.sh"))
        self.assertTrue(r.ok, msg=r.fails)

    def test_font_policy_not_untracked_skips_font_checks(self):
        # when font_policy is anything other than "untracked", the whole font
        # block is skipped -- a tracked font would otherwise fail but does not.
        cfg = dict(_CONFIG, font_policy="tracked")
        _write(self.root, vpr.CONFIG_REL, json.dumps(cfg))

        def handler(argv, cwd, env):
            # report the font glob as tracked; with the block skipped it is ignored.
            if argv[:3] == ["git", "ls-files", "--"] and "public/fonts/*.woff2" in argv:
                return proc_result(0, "public/fonts/serif.woff2\n")
            return proc_result(0, "")

        r = vpr.evaluate(self.repo, FakeProc(handler))
        self.assertTrue(r.ok, msg=r.fails)

    def test_font_on_disk_not_declared_caught(self):
        # an extra font on disk that the exclusions manifest does not declare.
        _write(self.root, "public/fonts/mono.woff2", "binary-ish")
        r = vpr.evaluate(self.repo, _green_proc())
        self.assertFalse(r.ok)
        self.assertTrue(
            any("font on disk but not declared" in f for f in r.fails), msg=r.fails
        )

    def test_declared_font_missing_on_disk_caught(self):
        # the manifest declares a font that is not present on disk.
        (self.root / "public/fonts/serif.woff2").unlink()
        r = vpr.evaluate(self.repo, _green_proc())
        self.assertFalse(r.ok)
        self.assertTrue(
            any("declared font missing on disk" in f for f in r.fails), msg=r.fails
        )

    def test_internal_record_tracked_caught(self):
        # an internal process record that must stay untracked is reported tracked.
        def handler(argv, cwd, env):
            if argv[:3] == ["git", "ls-files", "--"] and "reports/secret.txt" in argv:
                return proc_result(0, "reports/secret.txt\n")
            return proc_result(0, "")

        r = vpr.evaluate(self.repo, FakeProc(handler))
        self.assertFalse(r.ok)
        self.assertIn("internal record is tracked: reports/secret.txt", r.fails)


class FullMode(unittest.TestCase):
    """The release-ceremony (--full) secret-scan freshness checks. These only
    run when evaluate(..., full=True)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _build_fixture(self.root)
        self.repo = vpr.Repo(self.root)
        self._head = "a" * 40

    def tearDown(self):
        self._tmp.cleanup()

    def _now_stamp(self) -> str:
        return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _write_scan(self, **over) -> None:
        scan = {
            "status": "passed",
            "scanned_commit": self._head,
            "generated_at": self._now_stamp(),
        }
        scan.update(over)
        _write(self.root, vpr.SCAN_REPORT_REL, json.dumps(scan))

    def _full_proc(self, ancestor_rc: int = 0) -> FakeProc:
        """Green-ish proc that also answers rev-parse HEAD and the merge-base
        ancestor probe."""

        def handler(argv, cwd, env):
            if argv[:2] == ["git", "rev-parse"]:
                return proc_result(0, self._head + "\n")
            if argv[:2] == ["git", "merge-base"]:
                return proc_result(ancestor_rc, "")
            return proc_result(0, "")

        return FakeProc(handler)

    def test_full_green_passes(self):
        self._write_scan()
        r = vpr.evaluate(self.repo, self._full_proc(), full=True)
        self.assertTrue(r.ok, msg=r.fails)

    def test_full_missing_report_caught(self):
        # no scan report on disk.
        r = vpr.evaluate(self.repo, self._full_proc(), full=True)
        self.assertFalse(r.ok)
        self.assertTrue(any("no secret-scan report" in f for f in r.fails), msg=r.fails)

    def test_full_status_not_passed_caught(self):
        self._write_scan(status="failed")
        r = vpr.evaluate(self.repo, self._full_proc(), full=True)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("secret scan status is 'failed'" in f for f in r.fails), msg=r.fails
        )

    def test_full_scanned_commit_is_ancestor_passes(self):
        # scanned commit differs from HEAD but is an ancestor (merge-base rc 0).
        self._write_scan(scanned_commit="b" * 40)
        r = vpr.evaluate(self.repo, self._full_proc(ancestor_rc=0), full=True)
        self.assertTrue(r.ok, msg=r.fails)

    def test_full_scanned_commit_unrelated_caught(self):
        # scanned commit differs and is NOT an ancestor (merge-base rc != 0).
        self._write_scan(scanned_commit="b" * 40)
        r = vpr.evaluate(self.repo, self._full_proc(ancestor_rc=1), full=True)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("unrelated commit" in f for f in r.fails), msg=r.fails
        )

    def test_full_stale_scan_caught(self):
        # a scan older than secret_scan_max_age_days (7) is flagged.
        old = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=30)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self._write_scan(generated_at=old)
        r = vpr.evaluate(self.repo, self._full_proc(), full=True)
        self.assertFalse(r.ok)
        self.assertTrue(any("days old" in f for f in r.fails), msg=r.fails)

    def test_full_unparseable_timestamp_caught(self):
        self._write_scan(generated_at="not-a-timestamp")
        r = vpr.evaluate(self.repo, self._full_proc(), full=True)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("no parseable timestamp" in f for f in r.fails), msg=r.fails
        )


class ExternalInterface(unittest.TestCase):
    """main() against the REAL repo (real git + real Proc) — pins the text
    contract and the routine-mode exit code."""

    def test_main_routine_green(self):
        # main() parses sys.argv; pin it to the routine (no --full) invocation
        # so the test runner's own argv does not leak into argparse.
        with mock.patch.object(sys, "argv", ["validate_public_readiness.py"]):
            self.assertEqual(vpr.main(REPO_ROOT), 0)

    def test_main_fail_renders_and_returns_one(self):
        # drive main() over a fixture with a seeded defect (a missing required
        # root file) and a FakeProc swapped in for the real Proc, so it returns
        # 1 quickly and prints the FAIL block. assert rc==1 and the failure line.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        _build_fixture(root)
        (root / "LICENSE").unlink()  # the seeded defect

        def handler(argv, cwd, env):
            return proc_result(0, "")

        with mock.patch.object(sys, "argv", ["validate_public_readiness.py"]), mock.patch.object(
            vpr, "Proc", lambda: FakeProc(handler)
        ), mock.patch("sys.stdout", new=__import__("io").StringIO()) as out:
            rc = vpr.main(root)
        self.assertEqual(rc, 1)
        printed = out.getvalue()
        self.assertIn("FAIL:", printed)
        self.assertIn("required root file missing or empty: LICENSE", printed)


if __name__ == "__main__":
    unittest.main()
