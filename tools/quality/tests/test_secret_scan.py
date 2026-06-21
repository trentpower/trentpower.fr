#!/usr/bin/env python3
"""Tests for tools/quality/secret_scan.py through the Proc seam.

The whole compute path — gitleaks json parsing, the tracked-tree pass, the
history fallback, and the report build + pass/fail in main — runs against a
FakeProc, so no real gitleaks, git, or python subprocess is invoked. The
network install path stays out of scope (pragma: no cover in the module).

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import json
import pathlib
import unittest

import _fixture

_fixture.bootstrap()

import secret_scan as ss  # noqa: E402
from _fixture import FakeProc, proc_result  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _detect_report_path(argv):
    """Pull the gitleaks --report-path argument out of a detect argv."""
    return argv[argv.index("--report-path") + 1]


def _gitleaks_handler(raw_report, *, detect_rc=0, version="8.21.2"):
    """Build a FakeProc handler that emulates a gitleaks binary.

    `version` answers the version probe; the detect run writes `raw_report`
    (a list of gitleaks finding dicts) to the requested --report-path and
    exits with `detect_rc` (0 clean, 1 leaks found).
    """

    def handler(argv, cwd, env):
        if argv[1:2] == ["version"]:
            return proc_result(0, version + "\n")
        if argv[1:2] == ["detect"]:
            report = _detect_report_path(argv)
            pathlib.Path(report).write_text(json.dumps(raw_report), encoding="utf-8")
            return proc_result(detect_rc)
        return proc_result(0)

    return handler


class RunGitleaks(unittest.TestCase):
    def test_clean_report_yields_no_findings(self):
        proc = FakeProc(_gitleaks_handler([], detect_rc=0))
        findings, version = ss.run_gitleaks(proc, pathlib.Path("/usr/bin/gitleaks"))
        self.assertEqual(findings, [])
        self.assertEqual(version, "8.21.2")

    def test_leak_report_is_parsed_into_findings(self):
        raw = [
            {
                "RuleID": "generic-api-key",
                "File": "config/secrets.env",
                "Commit": "abcdef0123456789aaaa",
                "StartLine": 7,
                "Description": "Generic API Key",
            }
        ]
        proc = FakeProc(_gitleaks_handler(raw, detect_rc=1))
        findings, version = ss.run_gitleaks(proc, pathlib.Path("/usr/bin/gitleaks"))
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["rule"], "generic-api-key")
        self.assertEqual(f["file"], "config/secrets.env")
        # commit is truncated to 12 chars.
        self.assertEqual(f["commit"], "abcdef012345")
        self.assertEqual(f["line"], 7)
        self.assertEqual(f["description"], "Generic API Key")

    def test_engine_error_raises(self):
        # exit code outside {0, 1} is a gitleaks engine error, not a verdict.
        def handler(argv, cwd, env):
            if argv[1:2] == ["version"]:
                return proc_result(0, "8.21.2\n")
            return proc_result(2, "", "fatal: bad source")

        proc = FakeProc(handler)
        with self.assertRaises(RuntimeError):
            ss.run_gitleaks(proc, pathlib.Path("/usr/bin/gitleaks"))


class ScanHistoryFallback(unittest.TestCase):
    def test_clean_scanner_yields_no_findings(self):
        proc = FakeProc(lambda argv, cwd, env: proc_result(0, ""))
        self.assertEqual(ss.scan_history_fallback(proc), [])

    def test_dirty_scanner_lines_become_findings(self):
        out = "first/path leak\nsecond/path leak\n"
        proc = FakeProc(lambda argv, cwd, env: proc_result(1, out))
        findings = ss.scan_history_fallback(proc)
        self.assertEqual(len(findings), 2)
        self.assertEqual(findings[0]["rule"], "scan_git_history finding")
        self.assertEqual(findings[0]["commit"], "history")
        self.assertEqual(findings[0]["file"], "first/path leak")


class ScanTrackedTree(unittest.TestCase):
    """The content pass reads each tracked text file under REPO_ROOT and applies
    the hygiene patterns. We point REPO_ROOT at a temp tree and feed ls-files."""

    def _run(self, files, ls_output):
        with _tmpdir() as td:
            root = pathlib.Path(td)
            for rel, text in files.items():
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
            orig_root = ss.REPO_ROOT
            ss.REPO_ROOT = root
            try:
                proc = FakeProc(lambda argv, cwd, env: proc_result(0, ls_output))
                return ss.scan_tracked_tree(proc)
            finally:
                ss.REPO_ROOT = orig_root

    def test_secret_line_is_flagged(self):
        # an AKIA-shaped token trips the aws access key id pattern.
        files = {"config/app.json": "ok\nkey = AKIAABCDEFGHIJKLMNOP\ntail\n"}
        findings = self._run(files, "config/app.json\0")
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["rule"], "aws access key id")
        self.assertEqual(f["file"], "config/app.json")
        self.assertEqual(f["commit"], "worktree")
        self.assertEqual(f["line"], 2)

    def test_clean_and_skipped_files_yield_nothing(self):
        # a clean text file, a binary-suffix file (skipped), an exempt basename,
        # and a missing path all produce no findings.
        files = {
            "notes.md": "just prose, nothing secret here\n",
            "image.png": "AKIAABCDEFGHIJKLMNOP",  # non-text suffix -> skipped
            "pgp-key.asc": "AKIAABCDEFGHIJKLMNOP",  # exempt basename -> skipped
        }
        ls = "notes.md\0image.png\0pgp-key.asc\0gone.txt\0\0"
        self.assertEqual(self._run(files, ls), [])


class FindGitleaks(unittest.TestCase):
    def test_uses_which_when_on_path(self):
        orig_which = ss.shutil.which
        ss.shutil.which = lambda name: "/opt/bin/gitleaks"
        try:
            self.assertEqual(ss.find_gitleaks(), pathlib.Path("/opt/bin/gitleaks"))
        finally:
            ss.shutil.which = orig_which

    def test_falls_back_to_local_bin(self):
        orig_which = ss.shutil.which
        orig_local = ss.LOCAL_BIN
        tmp = pathlib.Path(self.enterContext(_tmpdir()))
        (tmp / "gitleaks").write_text("x", encoding="utf-8")
        ss.shutil.which = lambda name: None
        ss.LOCAL_BIN = tmp
        try:
            self.assertEqual(ss.find_gitleaks(), tmp / "gitleaks")
        finally:
            ss.shutil.which = orig_which
            ss.LOCAL_BIN = orig_local

    def test_returns_none_when_absent(self):
        orig_which = ss.shutil.which
        orig_local = ss.LOCAL_BIN
        tmp = pathlib.Path(self.enterContext(_tmpdir()))
        ss.shutil.which = lambda name: None
        ss.LOCAL_BIN = tmp
        try:
            self.assertIsNone(ss.find_gitleaks())
        finally:
            ss.shutil.which = orig_which
            ss.LOCAL_BIN = orig_local


def _tmpdir():
    import tempfile

    return tempfile.TemporaryDirectory()


class MainReportBuild(unittest.TestCase):
    """Drive main() end to end with a FakeProc and a forced gitleaks binary."""

    def _run_main(self, raw_report, detect_rc, tmp_path):
        # force find_gitleaks to a fake path so main takes the gitleaks engine;
        # keep the tracked-tree pass empty so the verdict is the gitleaks one.
        orig_find = ss.find_gitleaks
        ss.find_gitleaks = lambda: pathlib.Path("/usr/bin/gitleaks")

        def handler(argv, cwd, env):
            if argv[0] != "git" and argv[1:2] == ["version"]:
                return proc_result(0, "8.21.2\n")
            if argv[0] != "git" and argv[1:2] == ["detect"]:
                report = _detect_report_path(argv)
                pathlib.Path(report).write_text(json.dumps(raw_report), encoding="utf-8")
                return proc_result(detect_rc)
            if argv[:2] == ["git", "ls-files"]:
                return proc_result(0, "")  # empty tracked tree
            if argv[:2] == ["git", "rev-parse"]:
                return proc_result(0, "deadbeefcafe\n")
            if argv[:2] == ["git", "for-each-ref"]:
                return proc_result(0, "refs/heads/main\nrefs/heads/preprod\n")
            return proc_result(0)

        proc = FakeProc(handler)
        report_path = tmp_path / "report.json"
        argv_backup = ss.sys.argv
        ss.sys.argv = ["secret_scan.py", "--json", str(report_path)]
        try:
            rc = ss.main(proc)
        finally:
            ss.sys.argv = argv_backup
            ss.find_gitleaks = orig_find
        report = json.loads(report_path.read_text(encoding="utf-8"))
        return rc, report

    def test_clean_run_passes(self):
        with _tmpdir() as td:
            rc, report = self._run_main([], 0, pathlib.Path(td))
        self.assertEqual(rc, 0)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["summary"], {"passed": 1, "failed": 0, "warnings": 0})
        self.assertEqual(report["engine"], "gitleaks 8.21.2")
        self.assertEqual(report["scanned_commit"], "deadbeefcafe")
        self.assertEqual(report["refs_scanned"], 2)
        self.assertEqual(report["command"], "secret_scan.py")

    def test_leaked_run_fails(self):
        raw = [
            {
                "RuleID": "aws-access-token",
                "File": "deploy/keys.txt",
                "Commit": "0123456789abcdef",
                "StartLine": 3,
                "Description": "AWS Access Token",
            }
        ]
        with _tmpdir() as td:
            rc, report = self._run_main(raw, 1, pathlib.Path(td))
        self.assertEqual(rc, 1)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(len(report["findings"]), 1)
        self.assertEqual(report["summary"]["failed"], 1)
        self.assertEqual(report["summary"]["passed"], 0)
        self.assertEqual(report["findings"][0]["rule"], "aws-access-token")

    def test_many_findings_truncate_print_and_fail(self):
        # 30 gitleaks findings exercise the ">25 more" print branch.
        raw = [
            {
                "RuleID": f"rule-{i}",
                "File": f"f{i}.env",
                "Commit": "0123456789ab",
                "StartLine": i,
                "Description": "leak",
            }
            for i in range(30)
        ]
        with _tmpdir() as td:
            rc, report = self._run_main(raw, 1, pathlib.Path(td))
        self.assertEqual(rc, 1)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(len(report["findings"]), 30)

    def test_fallback_engine_when_gitleaks_absent(self):
        # no gitleaks binary -> main routes through scan_history_fallback.
        orig_find = ss.find_gitleaks
        ss.find_gitleaks = lambda: None

        def handler(argv, cwd, env):
            if argv[:2] == ["git", "ls-files"]:
                return proc_result(0, "")
            if argv[:2] == ["git", "rev-parse"]:
                return proc_result(0, "feedface0000\n")
            if argv[:2] == ["git", "for-each-ref"]:
                return proc_result(0, "refs/heads/main\n")
            # the scan_git_history.py subprocess: clean.
            return proc_result(0, "")

        proc = FakeProc(handler)
        with _tmpdir() as td:
            report_path = pathlib.Path(td) / "report.json"
            argv_backup = ss.sys.argv
            ss.sys.argv = ["secret_scan.py", "--json", str(report_path)]
            try:
                rc = ss.main(proc)
            finally:
                ss.sys.argv = argv_backup
                ss.find_gitleaks = orig_find
            report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(rc, 0)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["engine"], "scan_git_history-fallback")
        self.assertEqual(report["scanned_commit"], "feedface0000")


if __name__ == "__main__":
    unittest.main()
