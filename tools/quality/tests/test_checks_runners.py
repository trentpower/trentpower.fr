#!/usr/bin/env python3
"""Tests for the check runners in tools/lib/checks.py.

`run_registry` is the single captured loop gate.py + lint.py share; here it runs
over synthetic Check objects so its contract (runs all in order, returns the
CheckResults, fires on_result, honours stop_on_fail) is asserted without a real
validator and with no stdout to scrape. `progress_line` + `_script`/`advisory`
helpers are covered alongside.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

from __future__ import annotations

import unittest

import _fixture

_fixture.bootstrap()

import checks  # noqa: E402
from checks import Category, Check, Tier  # noqa: E402


def _mk(rc=0, cid="demo"):
    return Check(cid, cid, Tier.BLOCKING, Category.CORRECTNESS, "demo", function=lambda: rc)


class RunRegistry(unittest.TestCase):
    def test_runs_all_in_order_and_returns_results(self):
        checks_in = [_mk(0, "a"), _mk(1, "b"), _mk(0, "c")]
        results = checks.run_registry(checks_in)
        self.assertEqual([r.id for r in results], ["a", "b", "c"])
        self.assertEqual([r.status for r in results], ["passed", "failed", "passed"])

    def test_on_result_fires_per_check_with_progress(self):
        seen = []
        checks.run_registry(
            [_mk(0, "a"), _mk(0, "b")], on_result=lambda d, t, r: seen.append((d, t, r.id))
        )
        self.assertEqual(seen, [(1, 2, "a"), (2, 2, "b")])

    def test_stop_on_fail_breaks_after_first_failure(self):
        results = checks.run_registry([_mk(0, "a"), _mk(1, "b"), _mk(0, "c")], stop_on_fail=True)
        self.assertEqual([r.id for r in results], ["a", "b"])  # stopped at the failure

    def test_default_runs_past_failures(self):
        results = checks.run_registry([_mk(1, "a"), _mk(0, "b")])
        self.assertEqual(len(results), 2)


class ProgressLine(unittest.TestCase):
    def test_pass_and_fail_marks(self):
        results = checks.run_registry([_mk(0, "ok_one"), _mk(1, "bad_one")])
        self.assertEqual(checks.progress_line(1, 3, results[0]), "[1/3] OK COR ok_one")
        self.assertEqual(checks.progress_line(2, 3, results[1]), "[2/3] X COR bad_one")


class RunCheckCapturedNeither(unittest.TestCase):
    def test_neither_branch_captures_error(self):
        neither = Check("demo", "demo", Tier.ADVISORY, Category.QUALITY, "demo")
        r = checks.run_check_captured(neither)
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
