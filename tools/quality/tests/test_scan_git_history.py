#!/usr/bin/env python3
"""Tests for tools/verify/scan_git_history.py — the history secret/path sweep.

The scan functions take an injected Proc seam (and the repo root), so the whole
compute path runs over canned `git log`/`git ls-files` output via FakeProc —
no real git, no live history. We drive each branch with hand-built patch and
name-only streams and assert the right findings come out, then exercise main()'s
green path and the --strict non-zero contract.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import unittest

import _fixture

_fixture.bootstrap()

import scan_git_history as sgh  # noqa: E402
from _fixture import FakeProc, proc_result  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

# a fake `git log -p -U0` patch stream carrying one added line that trips the
# aws-access-key secret pattern, under one file path.
_SECRET_PATCH = (
    "commit abc1234567890\n"
    "diff --git a/conf.py b/conf.py\n"
    "+++ b/conf.py\n"
    "+aws_key = AKIAIOSFODNN7EXAMPLE\n"
)
# a clean patch stream: an added line with nothing secret-shaped in it.
_CLEAN_PATCH = (
    "commit def4567890123\n"
    "diff --git a/readme.txt b/readme.txt\n"
    "+++ b/readme.txt\n"
    "+just an ordinary line of prose\n"
)
# a patch whose added line carries a bare IPv4 (only flagged with --ips).
_IP_PATCH = (
    "commit aaa1112223334\n"
    "diff --git a/hosts.txt b/hosts.txt\n"
    "+++ b/hosts.txt\n"
    "+server at 203.0.113.7 responded\n"
)


def _fake_for(patch: str, names: str) -> FakeProc:
    """A FakeProc that returns `patch` for the `git log -p` content scan and
    `names` for the `git log --name-only` filename scan."""

    def handler(argv, cwd, env):
        if "-p" in argv:
            return proc_result(0, patch)
        if "--name-only" in argv:
            return proc_result(0, names)
        return proc_result(0, "")

    return FakeProc(handler)


class ContentScan(unittest.TestCase):
    def test_seeded_secret_line_is_reported(self):
        proc = _fake_for(_SECRET_PATCH, "")
        findings = sgh.scan_added_content(proc, REPO_ROOT, max_lines=5000)
        self.assertEqual(len(findings), 1)
        self.assertIn("abc1234", findings[0])
        self.assertIn("conf.py", findings[0])
        self.assertIn("aws access key id", findings[0])
        # the raw secret is masked, never echoed verbatim.
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", findings[0])

    def test_clean_patch_yields_no_findings(self):
        proc = _fake_for(_CLEAN_PATCH, "")
        self.assertEqual(sgh.scan_added_content(proc, REPO_ROOT, max_lines=5000), [])

    def test_max_lines_caps_the_scan(self):
        # the secret sits on the first added line; a zero cap skips it.
        proc = _fake_for(_SECRET_PATCH, "")
        self.assertEqual(sgh.scan_added_content(proc, REPO_ROOT, max_lines=0), [])

    def test_ip_option_off_then_on(self):
        proc_off = _fake_for(_IP_PATCH, "")
        self.assertEqual(sgh.scan_added_content(proc_off, REPO_ROOT, max_lines=5000), [])
        proc_on = _fake_for(_IP_PATCH, "")
        findings = sgh.scan_added_content(proc_on, REPO_ROOT, max_lines=5000, include_ips=True)
        self.assertEqual(len(findings), 1)
        self.assertIn("bare IPv4", findings[0])

    def test_git_crossing_goes_through_the_seam_with_repo_root(self):
        proc = _fake_for(_CLEAN_PATCH, "")
        sgh.scan_added_content(proc, REPO_ROOT, max_lines=5000)
        argv, cwd, _ = proc.calls[0]
        self.assertEqual(argv[:2], ["git", "log"])
        self.assertEqual(cwd, REPO_ROOT)


class FilenameScan(unittest.TestCase):
    def test_forbidden_basename_and_suffix_flagged(self):
        names = "src/app.py\n.env\nlib/data/store.sqlite\n"
        proc = _fake_for("", names)
        findings = sgh.scan_filenames(proc, REPO_ROOT)
        joined = "\n".join(findings)
        self.assertIn(".env (forbidden basename)", joined)
        self.assertIn("store.sqlite (forbidden suffix)", joined)

    def test_allowlisted_asc_not_flagged(self):
        names = "public/pgp-key.asc\nsrc/app.py\n"
        proc = _fake_for("", names)
        self.assertEqual(sgh.scan_filenames(proc, REPO_ROOT), [])


class MainPath(unittest.TestCase):
    def _run_with(self, patch: str, names: str, argv):
        # drive main() through the seam by swapping the module-level Proc + root.
        original_proc = sgh.Proc
        sgh.Proc = lambda: _fake_for(patch, names)
        try:
            return sgh.main(argv)
        finally:
            sgh.Proc = original_proc

    def test_green_path_returns_zero(self):
        self.assertEqual(self._run_with(_CLEAN_PATCH, "src/app.py\n", []), 0)

    def test_findings_non_strict_returns_zero(self):
        self.assertEqual(self._run_with(_SECRET_PATCH, "", []), 0)

    def test_findings_strict_returns_nonzero(self):
        self.assertEqual(self._run_with(_SECRET_PATCH, "", ["--strict"]), 1)

    def test_ips_flag_threads_through_main(self):
        self.assertEqual(self._run_with(_IP_PATCH, "", ["--ips", "--strict"]), 1)

    def test_not_a_git_repo_returns_zero(self):
        # point main() at a root with no .git so the early-out branch runs.
        original_root = sgh.REPO_ROOT
        original_proc = sgh.Proc
        sgh.REPO_ROOT = REPO_ROOT / "nonexistent-subdir-for-test"
        sgh.Proc = lambda: _fake_for(_SECRET_PATCH, "")
        try:
            self.assertEqual(sgh.main([]), 0)
        finally:
            sgh.REPO_ROOT = original_root
            sgh.Proc = original_proc


if __name__ == "__main__":
    unittest.main()
