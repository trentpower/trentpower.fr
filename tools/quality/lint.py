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
from checks import advisory, progress_line, run_registry  # noqa: E402


def _render_lint(done: int, total: int, result) -> None:
    print(progress_line(done, total, result), flush=True)


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

    # one captured loop. progress streams live for the text run + the --json PATH
    # run (back-compat); the json/markdown stdout formats emit only their block.
    show_progress = bool(args.json) or args.format == "text"
    results = run_registry(advisory(), on_result=_render_lint if show_progress else None)
    total = len(results)
    failed = [r for r in results if r.status != "passed"]

    if args.json:
        report = check_report.build_check_report("lint", [r.to_dict() for r in results])
        check_report.atomic_write_json(report, args.json)
        print(f"\nreport: {args.json}")
        if failed:
            print(f"advisory: {len(failed)}/{total} check(s) failed (non-blocking)")
        else:
            print(f"advisory: all {total} quality check(s) passed")
        return 1 if (args.strict and failed) else 0

    if args.format == "json":
        print(
            json.dumps(
                {
                    "advisory_total": total,
                    "advisory_failed": len(failed),
                    "results": [
                        {
                            "id": r.id,
                            "label": r.label,
                            "category": r.category,
                            "passed": r.status == "passed",
                            "rationale": r.rationale,
                        }
                        for r in results
                    ],
                },
                indent=2,
            )
        )
    elif args.format == "markdown":
        print(f"\n### Advisory lint -- {total - len(failed)}/{total} passed\n")
        print("| status | check | category |")
        print("|---|---|---|")
        for r in results:
            print(f"| {'pass' if r.status == 'passed' else '**FAIL**'} | {r.id} | {r.category} |")
    else:
        print()
        if failed:
            ids = ", ".join(r.id for r in failed)
            print(f"advisory: {len(failed)}/{total} check(s) failed (non-blocking): {ids}")
        else:
            print(f"advisory: all {total} quality check(s) passed")

    return 1 if (args.strict and failed) else 0


if __name__ == "__main__":
    sys.exit(main())
