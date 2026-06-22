#!/usr/bin/env python3
"""Tests for the fast-tier seam guard (_fixture.block_real_processes + run_fast).

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

import run_fast  # noqa: E402


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
            run_fast.SLOW_ALLOWLIST,
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

    def test_fast_suite_excludes_allowlisted_files(self):
        # the loaded fast suite must contain no test from an allowlisted module.
        def ids(suite):
            for t in suite:
                if isinstance(t, unittest.TestSuite):
                    yield from ids(t)
                else:
                    yield t.id()

        loaded = list(ids(run_fast.load_fast_suite()))
        self.assertTrue(loaded)  # sanity: it loaded something
        for tid in loaded:
            self.assertNotIn("test_proc.", tid)
            self.assertNotIn("test_doctor_render.", tid)
            self.assertNotIn("test_check_report.", tid)


if __name__ == "__main__":
    unittest.main()
