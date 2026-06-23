#!/usr/bin/env python3
"""Tests for the fast-tier seam guard (_fixture.block_real_processes + run_suite).

Context-independent: works whether or not a guard is already installed (it runs
in BOTH the guarded fast tier and the unguarded coverage pass), by asserting that
restore() returns the patched callables to whatever they were BEFORE the call —
not to any particular "real" object.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

from __future__ import annotations

import socket
import subprocess
import unittest

import _fixture

_fixture.bootstrap()

import run_suite  # noqa: E402


class BlockRealProcesses(unittest.TestCase):
    def test_patches_then_restores_subprocess_and_socket(self):
        before = (subprocess.run, subprocess.Popen, socket.socket)
        restore = _fixture.block_real_processes()
        try:
            self.assertIsNot(subprocess.run, before[0])
            self.assertIsNot(subprocess.Popen, before[1])
            self.assertIsNot(socket.socket, before[2])
        finally:
            restore()
        self.assertEqual((subprocess.run, subprocess.Popen, socket.socket), before)

    def test_blocked_subprocess_run_raises(self):
        restore = _fixture.block_real_processes()
        try:
            with self.assertRaises(AssertionError) as cm:
                subprocess.run(["true"])
            self.assertIn("Proc seam", str(cm.exception))
        finally:
            restore()

    def test_blocked_socket_raises(self):
        restore = _fixture.block_real_processes()
        try:
            with self.assertRaises(AssertionError):
                socket.socket()
        finally:
            restore()


class Allowlist(unittest.TestCase):
    def test_allowlist_is_exactly_the_integration_tier(self):
        self.assertEqual(
            run_suite.SLOW_ALLOWLIST,
            frozenset(
                {
                    "test_proc.py",
                    "test_doctor_render.py",
                    "test_check_report.py",
                    "test_public_readiness.py",
                    "test_validate_docs_freshness.py",
                    "test_validate_docs_links.py",
                }
            ),
        )

    def test_fast_selection_excludes_allowlisted_files(self):
        names = {f.name for f in run_suite.selected_files(fast=True)}
        self.assertTrue(names)  # sanity: it selected something
        self.assertTrue(names.isdisjoint(run_suite.SLOW_ALLOWLIST))

    def test_full_selection_includes_allowlisted_files(self):
        names = {f.name for f in run_suite.selected_files(fast=False)}
        self.assertTrue(run_suite.SLOW_ALLOWLIST.issubset(names))


class FailureSurfacing(unittest.TestCase):
    """run() must carry each failing test's id + traceback in the report — this
    is what makes a red fast tier debuggable from the CI log, and it guards the
    runner code, which lives under tests/ and so is outside the coverage surface."""

    def test_collect_failures_carries_id_and_traceback(self):
        class _Boom(unittest.TestCase):
            def test_boom(self):
                self.assertEqual(1, 2)

        result = unittest.TestResult()
        unittest.TestLoader().loadTestsFromTestCase(_Boom).run(result)
        collected = run_suite._collect_failures(result, "test_demo.py")
        self.assertEqual(len(collected), 1)
        self.assertEqual(collected[0]["file"], "test_demo.py")
        self.assertIn("test_boom", collected[0]["test_id"])
        self.assertIn("AssertionError", collected[0]["traceback"])

    def test_collect_failures_empty_on_clean_result(self):
        self.assertEqual(run_suite._collect_failures(unittest.TestResult(), "test_x.py"), [])


if __name__ == "__main__":
    unittest.main()
