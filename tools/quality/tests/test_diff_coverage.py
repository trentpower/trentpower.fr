#!/usr/bin/env python3
"""Tests for tools/quality/diff_coverage.py — the changed-line coverage ratchet.

evaluate() is pure: every case feeds a fixture coverage map + a canned unified
diff and asserts the verdict — no git, no coverage run, no host dependence. One
main()-level test injects FakeProc (the diff) + a tmp Repo (the coverage JSON).

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import _fixture

_fixture.bootstrap()

import diff_coverage as dc  # noqa: E402
from repo import Repo  # noqa: E402


def _diff(path, start, plus_lines):
    """A minimal unified-diff (--unified=0 style) adding `plus_lines` lines to
    `path` beginning at new-file line `start`."""
    body = "".join(f"+{i}\n" for i in range(plus_lines))
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -{start},0 +{start},{plus_lines} @@\n"
        f"{body}"
    )


def _cov(path, executed, missing):
    return {"files": {path: {"executed_lines": executed, "missing_lines": missing}}}


P = "tools/quality/widget.py"  # an in-scope path


class ParseChangedLines(unittest.TestCase):
    def test_added_lines_mapped_to_new_numbers(self):
        changed = dc.parse_changed_lines(_diff(P, 10, 3))
        self.assertEqual(changed[P], {10, 11, 12})

    def test_removed_lines_ignored(self):
        diff = (
            f"diff --git a/{P} b/{P}\n--- a/{P}\n+++ b/{P}\n"
            "@@ -5,2 +5,1 @@\n-old one\n-old two\n+new\n"
        )
        # only the single + line counts, at line 5.
        self.assertEqual(dc.parse_changed_lines(diff)[P], {5})

    def test_new_file_dev_null_old_side(self):
        diff = f"diff --git a/{P} b/{P}\n--- /dev/null\n+++ b/{P}\n@@ -0,0 +1,2 @@\n+a\n+b\n"
        self.assertEqual(dc.parse_changed_lines(diff)[P], {1, 2})


class Scope(unittest.TestCase):
    def test_in_scope_paths(self):
        self.assertTrue(dc.in_scope("tools/quality/x.py"))
        self.assertTrue(dc.in_scope("tools/lib/x.py"))
        self.assertTrue(dc.in_scope("tools/verify/x.py"))

    def test_out_of_scope_paths(self):
        self.assertFalse(dc.in_scope("tools/build/x.py"))  # generators excluded
        self.assertFalse(dc.in_scope("tools/quality/tests/test_x.py"))
        self.assertFalse(dc.in_scope("tools/quality/gate.py"))
        self.assertFalse(dc.in_scope("tools/quality/lint.py"))
        self.assertFalse(dc.in_scope("README.md"))


class Evaluate(unittest.TestCase):
    def test_fully_covered_change_passes(self):
        cov = _cov(P, executed=[10, 11, 12], missing=[])
        r = dc.evaluate(cov, _diff(P, 10, 3), 90)
        self.assertTrue(r.ok)
        self.assertEqual(r.files[0].status, "pass")
        self.assertEqual(r.files[0].ratio, 100.0)

    def test_uncovered_changed_line_fails_and_is_listed(self):
        # lines 10,11 covered, 12 missing → 2/3 = 66.7% < 90.
        cov = _cov(P, executed=[10, 11], missing=[12])
        r = dc.evaluate(cov, _diff(P, 10, 3), 90)
        self.assertFalse(r.ok)
        self.assertEqual(r.files[0].status, "fail")
        self.assertIn(12, r.files[0].uncovered_lines)
        self.assertEqual(r.files[0].uncovered_lines, [12])

    def test_threshold_boundary_inclusive(self):
        # exactly 90% passes (9 of 10 covered).
        cov = _cov(P, executed=list(range(10, 19)), missing=[19])
        r = dc.evaluate(cov, _diff(P, 10, 10), 90)
        self.assertEqual(r.files[0].ratio, 90.0)
        self.assertEqual(r.files[0].status, "pass")
        self.assertTrue(r.ok)

    def test_out_of_scope_file_skipped_not_failed(self):
        cov = {"files": {}}
        r = dc.evaluate(cov, _diff("tools/build/gen.py", 1, 5), 90)
        self.assertTrue(r.ok)
        self.assertEqual(r.files[0].status, "skip-out-of-scope")

    def test_in_scope_absent_from_coverage_is_unmeasured_fail(self):
        cov = {"files": {}}  # P never imported by the suite
        r = dc.evaluate(cov, _diff(P, 1, 4), 90)
        self.assertFalse(r.ok)
        self.assertEqual(r.files[0].status, "unmeasured")
        self.assertEqual(r.files[0].uncovered_lines, [1, 2, 3, 4])

    def test_pragma_excluded_lines_do_not_count(self):
        # changed lines 10,11 are neither executed nor missing (pragma-excluded
        # → coverage.py drops them) → nothing coverable → skip, not fail.
        cov = _cov(P, executed=[], missing=[])
        r = dc.evaluate(cov, _diff(P, 10, 2), 90)
        self.assertTrue(r.ok)
        self.assertEqual(r.files[0].status, "skip-no-coverable")

    def test_no_changed_files_passes(self):
        r = dc.evaluate({"files": {}}, "", 90)
        self.assertTrue(r.ok)
        self.assertEqual(r.files, [])


class MainSeam(unittest.TestCase):
    def test_main_reads_coverage_and_runs_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cov = _cov(P, executed=[1, 2], missing=[3])
            _fixture.write(root, dc.COVERAGE_JSON, json.dumps(cov))
            repo = Repo(root)
            # exercise load + parse via the pure path; git is the only real seam.
            data = dc.load_coverage(repo, dc.COVERAGE_JSON)
            r = dc.evaluate(data, _diff(P, 1, 3), 90)
            self.assertFalse(r.ok)  # 2/3 covered
            self.assertEqual(r.files[0].uncovered_lines, [3])

    def test_git_diff_resolves_merge_base_then_diffs_worktree(self):
        def handler(argv, cwd, env):
            if argv[:2] == ["git", "merge-base"]:
                self.assertIn("origin/main", argv)
                return _fixture.proc_result(0, "abc123\n")
            if argv[:2] == ["git", "diff"]:
                self.assertIn("abc123", argv)  # the resolved merge-base sha
                self.assertIn("--unified=0", argv)
                return _fixture.proc_result(0, _diff(P, 1, 1))
            return _fixture.proc_result(1)

        out = dc.git_diff(_fixture.FakeProc(handler), "origin/main")
        self.assertIn("+0", out)

    def test_git_merge_base_failure_raises(self):
        fp = _fixture.FakeProc(lambda a, c, e: _fixture.proc_result(128, "", "bad rev"))
        with self.assertRaises(SystemExit):
            dc.git_diff(fp, "nope")

    def test_git_diff_failure_raises(self):
        def handler(argv, cwd, env):
            if argv[:2] == ["git", "merge-base"]:
                return _fixture.proc_result(0, "abc123\n")
            return _fixture.proc_result(128, "", "diff blew up")

        with self.assertRaises(SystemExit):
            dc.git_diff(_fixture.FakeProc(handler), "origin/main")


class LoadCoverage(unittest.TestCase):
    def test_missing_file_raises_with_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as cm:
                dc.load_coverage(Repo(Path(tmp)), "nope/missing.json")
            self.assertIn("coverage.sh", str(cm.exception))

    def test_present_file_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fixture.write(root, "cov.json", json.dumps(_cov(P, [1], [])))
            data = dc.load_coverage(Repo(root), "cov.json")
            self.assertIn(P, data["files"])


class Render(unittest.TestCase):
    def _render_to_str(self, report):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            dc._render(report)
        return buf.getvalue()

    def test_render_covers_every_status_branch(self):
        report = dc.DiffCoverageReport(
            threshold=90,
            files=[
                dc.FileVerdict("a.py", "pass", 3, 3, 100.0, []),
                dc.FileVerdict("b.py", "fail", 1, 2, 50.0, [7]),
                dc.FileVerdict("c.py", "unmeasured", 0, 2, 0.0, [1, 2]),
                dc.FileVerdict("d.py", "skip-out-of-scope"),
                dc.FileVerdict("e.py", "skip-no-coverable"),
            ],
            ok=False,
        )
        out = self._render_to_str(report)
        self.assertIn("[ok]   a.py", out)
        self.assertIn("[FAIL] b.py", out)
        self.assertIn("uncovered changed lines: [7]", out)
        self.assertIn("not exercised by the suite", out)
        self.assertIn("out of coverage surface", out)
        self.assertIn("no executable lines changed", out)
        self.assertIn("FAIL: changed lines below the bar.", out)

    def test_render_nothing_to_gate(self):
        out = self._render_to_str(dc.DiffCoverageReport(threshold=90, files=[], ok=True))
        self.assertIn("no in-scope changed lines", out)
        self.assertIn("OK: changed lines meet the bar.", out)


class Main(unittest.TestCase):
    def _run(self, argv, cov, diff):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fixture.write(root, dc.COVERAGE_JSON, json.dumps(cov))
            proc = _fixture.FakeProc(
                lambda a, c, e: (
                    _fixture.proc_result(0, "mb\n")
                    if a[:2] == ["git", "merge-base"]
                    else _fixture.proc_result(0, diff)
                )
            )
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = dc.main(argv, repo=Repo(root), proc=proc)
            return rc, buf.getvalue()

    def test_main_plain_pass_exit_zero(self):
        rc, out = self._run([], _cov(P, [10, 11, 12], []), _diff(P, 10, 3))
        self.assertEqual(rc, 0)
        self.assertIn("OK: changed lines meet the bar.", out)

    def test_main_fail_exit_one(self):
        rc, out = self._run([], _cov(P, [10], [11, 12]), _diff(P, 10, 3))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL", out)

    def test_main_json_emits_valid_report(self):
        rc, out = self._run(["--json"], _cov(P, [10, 11, 12], []), _diff(P, 10, 3))
        self.assertEqual(rc, 0)
        doc = json.loads(out)
        self.assertEqual(doc["threshold"], dc.DIFF_MIN)
        self.assertTrue(doc["ok"])

    def test_main_threshold_override(self):
        # 2/3 = 66.7% passes at --threshold 50, fails at default 90.
        rc, _ = self._run(["--threshold", "50"], _cov(P, [10, 11], [12]), _diff(P, 10, 3))
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
