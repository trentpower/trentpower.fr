#!/usr/bin/env python3
"""Tests for tools/quality/coverage_summary.py — the suite-size + summary derive.

compute() crosses the Proc seam (git ls-files) and the Repo seam (file reads), so
every case runs in the fast tier with a FakeProc (canned `git ls-files`) + a tmp
Repo of crafted test files — no real git, no host dependence.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import _fixture

_fixture.bootstrap()

import coverage_summary as cs  # noqa: E402
from repo import Repo  # noqa: E402

_FLOORS = {"seal": 95, "adr": 95, "broad": 95}


def _proc(paths):
    """FakeProc whose `git ls-files` returns exactly `paths` (one per line)."""
    return _fixture.FakeProc(
        lambda argv, cwd, env: _fixture.proc_result(0, "\n".join(paths) + "\n")
    )


def _two_tests(
    body_a="def test_x():\n    pass\n\ndef test_y():\n    pass\n",
    body_b="def test_z():\n    pass\n",
):
    return body_a, body_b


class Compute(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, rel, text):
        _fixture.write(self.root, rel, text)

    def test_counts_tracked_files_and_functions(self):
        a, b = _two_tests()
        self._write("tools/quality/tests/test_a.py", a)  # 2 functions
        self._write("tools/quality/tests/test_b.py", b)  # 1 function
        proc = _proc(["tools/quality/tests/test_a.py", "tools/quality/tests/test_b.py"])
        d = cs.compute(96.0, _FLOORS, proc=proc, repo=Repo(self.root))
        self.assertEqual(d["test_files"], 2)
        self.assertEqual(d["test_functions"], 3)

    def test_filters_non_test_files(self):
        self._write("tools/quality/tests/test_a.py", "def test_x():\n    pass\n")
        self._write("tools/quality/tests/_fixture.py", "def test_helper():\n    pass\n")
        self._write("tools/quality/tests/run_fast.py", "def test_runner():\n    pass\n")
        # ls-files lists all three, but only the test_*.py file counts.
        proc = _proc(
            [
                "tools/quality/tests/test_a.py",
                "tools/quality/tests/_fixture.py",
                "tools/quality/tests/run_fast.py",
            ]
        )
        d = cs.compute(90.0, _FLOORS, proc=proc, repo=Repo(self.root))
        self.assertEqual(d["test_files"], 1)
        self.assertEqual(d["test_functions"], 1)

    def test_only_tracked_files_counted(self):
        self._write("tools/quality/tests/test_a.py", "def test_x():\n    pass\n")
        self._write(
            "tools/quality/tests/test_scratch.py",
            "def test_a():\n    pass\ndef test_b():\n    pass\n",
        )
        # the scratch file is on disk but NOT in git ls-files → not counted.
        proc = _proc(["tools/quality/tests/test_a.py"])
        d = cs.compute(90.0, _FLOORS, proc=proc, repo=Repo(self.root))
        self.assertEqual(d["test_files"], 1)
        self.assertEqual(d["test_functions"], 1)

    def test_schema_rounding_and_floors(self):
        self._write("tools/quality/tests/test_a.py", "def test_x():\n    pass\n")
        proc = _proc(["tools/quality/tests/test_a.py"])
        d = cs.compute(96.04, {"seal": 95, "adr": 97, "broad": 95}, proc=proc, repo=Repo(self.root))
        self.assertEqual(d["test_coverage_pct"], 96)
        self.assertEqual(d["raw"], 96.04)
        self.assertEqual(d["surface"], "unit-testable-logic")
        self.assertEqual(d["floors"], {"seal": 95, "adr": 97, "broad": 95})

    def test_git_ls_files_invoked_over_the_tests_dir(self):
        captured = {}

        def handler(argv, cwd, env):
            captured["argv"] = argv
            return _fixture.proc_result(0, "")

        cs.compute(0.0, _FLOORS, proc=_fixture.FakeProc(handler), repo=Repo(self.root))
        self.assertEqual(captured["argv"][:2], ["git", "ls-files"])
        self.assertIn("tools/quality/tests/", captured["argv"])


if __name__ == "__main__":
    unittest.main()
