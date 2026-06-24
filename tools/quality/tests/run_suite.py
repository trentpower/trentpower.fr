#!/usr/bin/env python3
"""run_suite.py — the single test runner: discover, guard, run, report.

Runs the unit suite a FILE at a time so the report carries per-file counts +
timing (the `make` ceremony, tools/quality/make-ui.sh, renders it as a summary
panel or a per-file table). `--fast` installs the seam guard and skips the
integration-tier allowlist; the full pass runs everything unblocked.

This module owns the fast tier outright — the allowlist, the load-before-block
ordering, and the guarded run all live here. On failure it surfaces each failing
test's id + traceback (in the report and, for a humans-watching run, on stderr),
so a red fast tier is debuggable from the CI log alone, not just a count.

    python3 tools/quality/tests/run_suite.py                 # full suite, terse
    python3 tools/quality/tests/run_suite.py --fast          # fast tier, exit 0/1
    python3 tools/quality/tests/run_suite.py --fast --json /tmp/r.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback as _tb
import unittest
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TESTS))

import _fixture  # noqa: E402

_fixture.bootstrap()

# Tests that legitimately use real subprocess / the real repo — the integration
# tier. They run in full under `make coverage` (unblocked), never under the
# guard. Each is here because it exercises a real binary or the real tree on
# purpose, not because it bypasses the seam by accident:
#   test_proc.py                  the production Proc() adapter itself
#   test_doctor_render.py         shells out to the real doctor.sh ceremony
#   test_check_report.py          run_check_captured runs real commands (true/false/…)
#   test_public_readiness.py      ExternalInterface — real main() over real git
#   test_validate_docs_freshness.py  ExternalInterface — main() over the real repo
#   test_validate_docs_links.py      ExternalInterface — main() over the real repo
# A future ACCIDENTAL seam bypass in any OTHER file still fails the guard.
SLOW_ALLOWLIST = frozenset(
    {
        "test_proc.py",
        "test_doctor_render.py",
        "test_check_report.py",
        "test_public_readiness.py",
        "test_validate_docs_freshness.py",
        "test_validate_docs_links.py",
    }
)


def selected_files(fast: bool) -> list[Path]:
    """The test files this run will load: every test_*.py, minus the slow-tier
    allowlist when fast. The one place discovery + the allowlist filter live, so
    the seam guard's "the fast suite excludes the integration tier" is a property
    of this function rather than of the run loop."""
    files = sorted(_TESTS.glob("test_*.py"))
    if fast:
        files = [f for f in files if f.name not in SLOW_ALLOWLIST]
    return files


def _collect_failures(result: unittest.TestResult, filename: str) -> list[dict]:
    """Each failure/error as {file, test_id, traceback} — the detail that makes a
    red fast tier debuggable from the report alone. Pure, so the runner's failure
    path is testable even though run_suite lives outside the coverage surface."""
    return [
        {"file": filename, "test_id": case.id(), "traceback": tb}
        for case, tb in (*result.failures, *result.errors)
    ]


def run(fast: bool) -> dict:
    loader = unittest.TestLoader()

    # load every module FIRST (imports run unblocked — some pull in ssl/asyncio,
    # which subclass socket at import time and would crash under the guard), then
    # install the guard only for the run phase (ADR-0005).
    loaded = [(f, loader.loadTestsFromName(f.stem)) for f in selected_files(fast)]

    restore = _fixture.block_real_processes() if fast else None
    rows: list[dict] = []
    failures: list[dict] = []
    total = {"tests": 0, "passed": 0, "failed": 0, "errors": 0, "ms": 0}
    try:
        for f, suite in loaded:
            result = unittest.TestResult()
            result.buffer = True  # swallow test stdout/stderr unless it fails
            t0 = time.monotonic()
            suite.run(result)
            ms = int((time.monotonic() - t0) * 1000)
            failed, errors = len(result.failures), len(result.errors)
            passed = result.testsRun - failed - errors
            failures.extend(_collect_failures(result, f.name))
            rows.append(
                {
                    "file": f.name,
                    "tests": result.testsRun,
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                    "ms": ms,
                }
            )
            for k, v in (
                ("tests", result.testsRun),
                ("passed", passed),
                ("failed", failed),
                ("errors", errors),
                ("ms", ms),
            ):
                total[k] += v
    finally:
        if restore:
            restore()

    return {
        "summary": total,
        "files": rows,
        "failures": failures,
        "ok": total["failed"] == 0 and total["errors"] == 0,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="run the unit suite, emit a per-file report")
    ap.add_argument("--fast", action="store_true", help="fast tier (seam guard + allowlist)")
    ap.add_argument("--json", metavar="PATH", help="write the full JSON report to PATH")
    args = ap.parse_args(argv)

    try:
        report = run(args.fast)
    except Exception:  # a discovery/import error is itself a fast-tier failure
        _tb.print_exc()
        return 1

    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    s = report["summary"]
    tier = "fast tier" if args.fast else "suite"
    if report["ok"]:
        print(f"{tier}: {s['passed']} passed · {s['ms'] / 1000:.1f}s")
        return 0

    # loud on failure: name each test and show its traceback on stderr, so the
    # CI log / preflight panel is debuggable without re-running with -v.
    for fail in report["failures"]:
        print(f"\nFAIL {fail['test_id']}  [{fail['file']}]", file=sys.stderr)
        print(fail["traceback"], file=sys.stderr)
    print(
        f"{tier}: {s['failed']} failed, {s['errors']} errors of {s['tests']}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
