#!/usr/bin/env python3
"""gate.py -- the deploy-blocking gate.

Runs only the Tier.BLOCKING checks from tools/lib/checks.py: security and
correctness. A failure here means the tree is unsafe or incorrect to ship.
Editorial / quality lint lives in tools/lint.py and never blocks a deploy.

Usage:
    python3 tools/gate.py          # fail-fast: stop at the first blocking failure
    python3 tools/gate.py --all    # run all blocking checks, report every failure

Exit 0 = ready to deploy. Exit 1 = blocked.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(
    0,
    str(
        next(
            _a
            for _a in __import__("pathlib").Path(__file__).resolve().parents
            if _a.name == "tools"
        )
        / "lib"
    ),
)
import check_report  # noqa: E402
from checks import blocking, progress_line, run_registry, signature_check_ids  # noqa: E402

# the signature-dependent checks (gpg verify + sig freshness) are flagged in the
# registry (Check.requires_signature) and surfaced via signature_check_ids(), so
# this gate no longer keeps its own list to drift out of sync. the graphical
# build runs the blocking gate ONCE before signing (for the publication review
# screen) and again, in full, after signing. --skip-signature /
# GATE_SKIP_SIGNATURE=1 omits only the flagged checks for that pre-signature
# pass; the post-signature run is full. a normal `gate.py` is unaffected.


def _blocking_checks(skip_signature: bool) -> list:
    checks = blocking()
    if skip_signature:
        sig_ids = set(signature_check_ids())
        checks = [c for c in checks if c.id not in sig_ids]
    return checks


def _render_gate(done: int, total: int, result) -> None:
    """Live per-check line for the human-facing run; blocking failures called out."""
    print(progress_line(done, total, result), flush=True)
    if result.status != "passed":
        print(f"  X BLOCKING FAILURE [{result.category}] {result.id} -- {result.rationale}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="deploy-blocking security + correctness gate")
    ap.add_argument(
        "--all",
        action="store_true",
        help="run every blocking check and report all failures (default: stop at first)",
    )
    ap.add_argument(
        "--json",
        metavar="PATH",
        help="write a machine-readable report to PATH (implies --all)",
    )
    ap.add_argument(
        "--skip-signature",
        action="store_true",
        default=os.environ.get("GATE_SKIP_SIGNATURE") == "1",
        help="omit the signature-dependent checks (gpg verify + sig freshness); "
        "for the pre-signing Publication Review pass only -- NOT a deploy gate",
    )
    args = ap.parse_args(argv)

    if args.skip_signature:
        skipped = ", ".join(signature_check_ids())
        print(f"note: --skip-signature -- omitting signature checks ({skipped})")
        # in the graphical build, release archives are built only AFTER signing
        # (build.sh stage 08), so a pre-signature pass is also a pre-archive pass.
        # export the flag so subprocess validators defer the in-flight edition's
        # release-archive checks; the post-signature gate (and CI) still enforce them.
        os.environ["GATE_SKIP_SIGNATURE"] = "1"

    # one captured loop for every mode: fail-fast unless --all/--json wants the
    # full set. --json additionally writes the machine-readable report.
    checks = _blocking_checks(args.skip_signature)
    results = run_registry(checks, on_result=_render_gate, stop_on_fail=not (args.all or args.json))
    report = check_report.build_check_report("gate", [r.to_dict() for r in results])
    if args.json:
        check_report.atomic_write_json(report, args.json)
        print(f"\nreport: {args.json}")

    print()
    if report["status"] == "failed":
        ids = ", ".join(r.id for r in results if r.status != "passed")
        print(
            f"FAIL: deploy blocked -- {report['summary']['failed']} blocking check(s) failed: {ids}"
        )
        return 1
    print("OK: ready to deploy (cp-not-mv; keep one cycle of old assets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
