#!/usr/bin/env python3
"""lint.py -- advisory quality / editorial lint.

Runs only the Tier.ADVISORY checks from tools/lib/checks.py: SEO refinement,
CSS architecture, editorial copy, comment style, nav/anchor shape, etc.
These protect polish and maintainability but do NOT make the site unsafe to
deploy, so this script exits 0 by default even when checks fail -- the
failures are reported, not enforced.

Usage:
    python3 tools/lint.py                  # report advisory results, always exit 0
    python3 tools/lint.py --strict         # exit non-zero if any advisory check fails
    python3 tools/lint.py --format json     # machine-readable summary (text|json|markdown)

In CI, run this as a non-blocking job so quality findings are visible without
blocking an urgent content or security deploy.
"""

from __future__ import annotations

import argparse
import json
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
from checks import advisory, run_check, run_check_captured  # noqa: E402


def _run_json_file(out_path: str, strict: bool) -> int:
    """Run advisory checks captured and write the standardized report to PATH.

    Distinct from --format json (a stdout summary kept for back-compat): this
    writes the same envelope shape as gate.py to reports/checks/. Advisory
    failures land in summary.warnings, so top-level status stays "passed";
    exit code is 0 unless --strict and something failed.
    """
    checks = advisory()
    total = len(checks)
    results = []
    for i, c in enumerate(checks, 1):
        print(f"[{i}/{total}] {c.category.value} {c.label}", flush=True)
        results.append(run_check_captured(c))

    report = check_report.build_check_report("lint", [r.to_dict() for r in results])
    check_report.atomic_write_json(report, out_path)
    failed = report["summary"]["warnings"]
    print(f"\nreport: {out_path}")
    if failed:
        print(f"advisory: {failed}/{total} check(s) failed (non-blocking)")
    else:
        print(f"advisory: all {total} quality check(s) passed")
    return 1 if (strict and failed) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="advisory quality / editorial lint (never blocks deploy)"
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero if any advisory check fails (for local quality sweeps)",
    )
    ap.add_argument(
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="summary format (default: text)",
    )
    ap.add_argument(
        "--json",
        metavar="PATH",
        help="write the standardized machine-readable report to PATH "
        "(reports/checks/ contract; distinct from --format json stdout summary)",
    )
    args = ap.parse_args(argv)

    if args.json:
        return _run_json_file(args.json, args.strict)

    checks = advisory()
    total = len(checks)
    results = []
    for i, c in enumerate(checks, 1):
        if args.format == "text":
            print(f"[{i}/{total}] {c.category.value} {c.label}", flush=True)
        rc = run_check(c)
        results.append((c, rc))

    failed = [(c, rc) for c, rc in results if rc != 0]

    if args.format == "json":
        print(
            json.dumps(
                {
                    "advisory_total": total,
                    "advisory_failed": len(failed),
                    "results": [
                        {
                            "id": c.id,
                            "label": c.label,
                            "category": c.category.value,
                            "passed": rc == 0,
                            "rationale": c.rationale,
                        }
                        for c, rc in results
                    ],
                },
                indent=2,
            )
        )
    elif args.format == "markdown":
        print(f"\n### Advisory lint -- {total - len(failed)}/{total} passed\n")
        print("| status | check | category |")
        print("|---|---|---|")
        for c, rc in results:
            print(f"| {'pass' if rc == 0 else '**FAIL**'} | {c.id} | {c.category.value} |")
    else:
        print()
        if failed:
            ids = ", ".join(c.id for c, _ in failed)
            print(f"advisory: {len(failed)}/{total} check(s) failed (non-blocking): {ids}")
        else:
            print(f"advisory: all {total} quality check(s) passed")

    if args.strict and failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
