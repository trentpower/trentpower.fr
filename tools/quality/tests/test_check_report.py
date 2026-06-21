#!/usr/bin/env python3
"""Tests for the check report contract (tools/check_report.py) and the
captured check runner (tools/lib/checks.py). Stdlib unittest -- no pytest dep.

Run:
    python3 -m unittest discover -s tools/tests
    python3 tools/tests/test_check_report.py
"""

import json
import pathlib
import sys
import tempfile
import unittest

import _fixture  # noqa: E402

_fixture.bootstrap("release")

import check_report  # noqa: E402
import checks  # noqa: E402
from checks import Category, Check, Tier  # noqa: E402


def _check_dict(status, tier="blocking", duration_ms=10):
    return {"status": status, "tier": tier, "duration_ms": duration_ms}


class BuildCheckReport(unittest.TestCase):
    def test_mixed_blocking_failure(self):
        rep = check_report.build_check_report(
            "gate",
            [_check_dict("passed"), _check_dict("failed", "blocking")],
        )
        self.assertEqual(rep["status"], "failed")
        self.assertEqual(rep["summary"]["passed"], 1)
        self.assertEqual(rep["summary"]["failed"], 1)
        self.assertEqual(rep["summary"]["warnings"], 0)
        self.assertEqual(rep["command"], "gate")
        self.assertEqual(rep["schema_version"], 1)
        self.assertTrue(rep["generated_at"].endswith("Z"))

    def test_all_pass(self):
        rep = check_report.build_check_report("gate", [_check_dict("passed")] * 3)
        self.assertEqual(rep["status"], "passed")
        self.assertEqual(rep["summary"]["failed"], 0)
        self.assertEqual(rep["summary"]["passed"], 3)

    def test_advisory_failure_is_warning_not_failure(self):
        rep = check_report.build_check_report(
            "lint", [_check_dict("passed"), _check_dict("failed", "advisory")]
        )
        self.assertEqual(rep["status"], "passed")  # advisory never flips status
        self.assertEqual(rep["summary"]["warnings"], 1)
        self.assertEqual(rep["summary"]["failed"], 0)

    def test_duration_summed(self):
        rep = check_report.build_check_report(
            "gate", [_check_dict("passed", duration_ms=100), _check_dict("passed", duration_ms=23)]
        )
        self.assertEqual(rep["summary"]["duration_ms"], 123)


class BuildAuditReport(unittest.TestCase):
    def _audit(self, statuses):
        return check_report.build_audit_report(
            "audit",
            run={"run_id": 1, "git_commit": "abc"},
            scorecards=[{"name": f"c{i}", "status": s} for i, s in enumerate(statuses)],
            headline_metrics=[{"metric": "m", "rolling_median": 9}],
            open_actions=[],
        )

    def test_fail_card_makes_status_failed(self):
        rep = self._audit(["PASS", "REVIEW", "FAIL"])
        self.assertEqual(rep["status"], "failed")
        self.assertEqual(rep["summary"]["failed"], 1)
        self.assertEqual(rep["summary"]["warnings"], 1)
        self.assertEqual(rep["summary"]["passed"], 1)

    def test_no_fail_card_passes(self):
        rep = self._audit(["PASS", "REVIEW"])
        self.assertEqual(rep["status"], "passed")
        self.assertEqual(rep["command"], "audit")
        self.assertEqual(rep["headline_metrics"][0]["rolling_median"], 9)


class AtomicWriteJson(unittest.TestCase):
    def test_writes_valid_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "nested" / "out.json"
            check_report.atomic_write_json({"a": 1, "é": "ok"}, p)
            self.assertTrue(p.exists())
            self.assertEqual(json.loads(p.read_text(encoding="utf-8")), {"a": 1, "é": "ok"})

    def test_no_partial_file_on_serialization_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "out.json"
            with self.assertRaises(TypeError):
                check_report.atomic_write_json({"bad": {1, 2, 3}}, p)  # set is not JSON
            self.assertFalse(p.exists())
            # and no leftover temp file in the directory.
            self.assertEqual(list(pathlib.Path(d).iterdir()), [])


class RunCheckCaptured(unittest.TestCase):
    def test_command_check_passing(self):
        c = Check(
            "demo_cmd",
            "demo command",
            Tier.BLOCKING,
            Category.CORRECTNESS,
            "demo",
            command=[sys.executable, "-c", "print('hello-stdout')"],
        )
        r = checks.run_check_captured(c)
        self.assertEqual(r.status, "passed")
        self.assertGreaterEqual(r.duration_ms, 0)
        self.assertIn("hello-stdout", r.stdout)
        d = r.to_dict()
        self.assertEqual(d["affected_files"], [])
        self.assertEqual(d["tier"], "blocking")

    def test_command_check_failing_captures_stderr(self):
        c = Check(
            "demo_fail",
            "demo fail",
            Tier.BLOCKING,
            Category.CORRECTNESS,
            "demo",
            command=[sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(1)"],
        )
        r = checks.run_check_captured(c)
        self.assertEqual(r.status, "failed")
        self.assertIn("boom", r.stderr)

    def test_function_check_stdout_captured(self):
        def fn():
            print("from-function")
            return 0

        c = Check("demo_fn", "demo fn", Tier.ADVISORY, Category.QUALITY, "demo", function=fn)
        r = checks.run_check_captured(c)
        self.assertEqual(r.status, "passed")
        self.assertIn("from-function", r.stdout)
        self.assertEqual(r.tier, "advisory")


if __name__ == "__main__":
    unittest.main()
