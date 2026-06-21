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


class ExternalInterface(unittest.TestCase):
    """main() against the REAL repo (real git + real Proc) — pins the text
    contract and the routine-mode exit code."""

    def test_main_routine_green(self):
        # main() parses sys.argv; pin it to the routine (no --full) invocation
        # so the test runner's own argv does not leak into argparse.
        with mock.patch.object(sys, "argv", ["validate_public_readiness.py"]):
            self.assertEqual(vpr.main(REPO_ROOT), 0)


if __name__ == "__main__":
    unittest.main()
