#!/usr/bin/env python3
"""run_suite.py — run the unit suite and emit a per-file JSON result.

A sibling of run_fast.py used by the `make` ceremony (tools/quality/make-ui.sh)
to render a summary panel or a per-file table instead of a raw `unittest -v`
dump. Each test FILE is run on its own so the report carries per-file counts +
timing; test stdout is buffered (shown only on failure). Lives under
tools/quality/tests/ so it never counts toward the coverage surface.

    python3 tools/quality/tests/run_suite.py --json /tmp/r.json   # full suite
    python3 tools/quality/tests/run_suite.py --fast --json /tmp/r.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import unittest
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TESTS))

import _fixture  # noqa: E402

_fixture.bootstrap()

import run_fast  # noqa: E402  (reuse the slow-tier allowlist + the seam guard)


def run(fast: bool) -> dict:
    loader = unittest.TestLoader()
    files = sorted(_TESTS.glob("test_*.py"))
    if fast:
        files = [f for f in files if f.name not in run_fast.SLOW_ALLOWLIST]

    # load every module FIRST (imports run unblocked — some pull in ssl/asyncio,
    # which subclass socket at import time and would crash under the guard), then
    # install the guard only for the run phase. Mirrors run_fast.py's ordering.
    loaded = [(f, loader.loadTestsFromName(f.stem)) for f in files]

    restore = _fixture.block_real_processes() if fast else None
    rows: list[dict] = []
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

    return {"summary": total, "files": rows, "ok": total["failed"] == 0 and total["errors"] == 0}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="run the unit suite, emit a per-file report")
    ap.add_argument("--fast", action="store_true", help="fast tier (seam guard + allowlist)")
    ap.add_argument("--json", metavar="PATH", help="write the JSON report to PATH (else stdout)")
    args = ap.parse_args(argv)

    report = run(args.fast)
    text = json.dumps(report, indent=2)
    if args.json:
        Path(args.json).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
