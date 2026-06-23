#!/usr/bin/env python3
"""run_fast.py — the fast unit tier with the seam guard installed.

Discovers and runs the unit suite with real subprocess + socket blocked
(_fixture.block_real_processes), MINUS an explicit two-file allowlist that
genuinely needs real processes. Any other test that shells out to real git/gpg
or opens a socket — bypassing the injected Proc seam — fails LOUD here, so the
seam architecture is an enforced invariant rather than a convention.

The block is installed AFTER the test modules are imported (so import-time work
is unaffected) and removed in a finally. `make coverage` runs the WHOLE suite
unblocked (including the allowlisted slow tests) and remains the authoritative
test+coverage pass; this is an extra, fast-failing guard.

Run:
    python3 tools/quality/tests/run_fast.py          # exit 0/1
    make test-fast
"""

from __future__ import annotations

import sys
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


def load_fast_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for f in sorted(_TESTS.glob("test_*.py")):
        if f.name in SLOW_ALLOWLIST:
            continue
        suite.addTests(loader.loadTestsFromName(f.stem))
    return suite


def main() -> int:
    suite = load_fast_suite()  # imports happen here, unblocked
    restore = _fixture.block_real_processes()
    try:
        result = unittest.TextTestRunner(verbosity=1).run(suite)
    finally:
        restore()
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
