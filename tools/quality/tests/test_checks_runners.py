#!/usr/bin/env python3
"""Tests for the check runners in tools/lib/checks.py.

`run_check` (streaming) and the `_script`/`advisory` helpers are central to how
gate.py / lint.py execute the registry; here they run over synthetic Check
objects so every branch (function / command / neither) is asserted without a
real validator. The command branch patches `subprocess.run` (a stand-in, never a
real process), so these stay fast-tier-clean under the seam guard.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

from __future__ import annotations

import unittest
from unittest import mock

import _fixture

_fixture.bootstrap()

import checks  # noqa: E402
from checks import Category, Check, Tier  # noqa: E402


def _mk(*, function=None, command=None):
    return Check(
        "demo", "demo", Tier.ADVISORY, Category.QUALITY, "demo", function=function, command=command
    )


class RunCheck(unittest.TestCase):
    def test_function_branch_returns_its_code(self):
        self.assertEqual(checks.run_check(_mk(function=lambda: 0)), 0)
        self.assertEqual(checks.run_check(_mk(function=lambda: 3)), 3)

    def test_command_branch_uses_subprocess(self):
        with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0)) as m:
            rc = checks.run_check(_mk(command=["echo", "hi"]))
        self.assertEqual(rc, 0)
        self.assertEqual(m.call_args.args[0], ["echo", "hi"])

    def test_neither_function_nor_command_fails(self):
        self.assertEqual(checks.run_check(_mk()), 1)


class RunCheckCapturedNeither(unittest.TestCase):
    def test_neither_branch_captures_error(self):
        r = checks.run_check_captured(_mk())
        self.assertEqual(r.status, "failed")
        self.assertIn("neither function nor command", r.stderr)


class Helpers(unittest.TestCase):
    def test_script_fallback_when_not_in_a_pillar(self):
        argv = checks._script("a_script_that_is_in_no_pillar_xyz.py")
        self.assertTrue(argv[-1].endswith("a_script_that_is_in_no_pillar_xyz.py"))

    def test_advisory_returns_only_advisory_checks(self):
        adv = checks.advisory()
        self.assertTrue(adv)
        self.assertTrue(all(c.tier is Tier.ADVISORY for c in adv))


if __name__ == "__main__":
    unittest.main()
