#!/usr/bin/env python3
"""coverage_summary.py — derive the coverage summary the badge + docs read.

`tools/quality/coverage.sh` measures the percentage; this module derives the
SUITE SIZE (test files + functions) and assembles `coverage-summary.json` —
the contract `tools/badges/sync_coverage.py` reads. It used to live as a heredoc
inside coverage.sh, where the count logic (which files count, how a test
function is recognised) had no test surface. As a module it gains an interface
that IS its test surface.

Shape mirrors render_proof.py — a pure `compute()` that returns the dict and a
thin `main()` that writes it — because there is no pass/fail here (the floors are
enforced in coverage.sh, not by this derive). The count crosses the injected
`Proc` (git) and `Repo` (file reads) seams so the unit test runs in the fast tier
(FakeProc + a tmp Repo), never touching real git.

    python3 tools/quality/coverage_summary.py --pct 96.0 --seal 95 --adr 95 --broad 95
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_TOOLS = next(_a for _a in Path(__file__).resolve().parents if _a.name == "tools")
sys.path.insert(0, str(_TOOLS / "lib"))

from paths import REPO_ROOT  # noqa: E402
from proc import Proc  # noqa: E402  (subprocess evidence seam — git ls-files)
from repo import Repo  # noqa: E402  (filesystem evidence seam — read each test file)

# where the suite lives + how a test function is recognised. The count is over
# TRACKED files (git ls-files), so an uncommitted scratch test never inflates it.
TESTS_DIR = "tools/quality/tests/"
SUMMARY_REL = ".build/coverage/coverage-summary.json"
_FN_RE = re.compile(r"^\s*def test_", re.MULTILINE)


def compute(pct: float, floors: dict, *, proc: Proc, repo: Repo) -> dict:
    """The coverage-summary dict: the measured percentage plus the source-derived
    suite size and the enforced floors. Pure — no I/O beyond the injected seams."""
    tracked = proc.run(["git", "ls-files", TESTS_DIR], cwd=repo.root).stdout.splitlines()
    files = sorted(
        p for p in tracked if p and Path(p).name.startswith("test_") and p.endswith(".py")
    )
    funcs = sum(len(_FN_RE.findall(repo.read(p))) for p in files)
    return {
        "test_coverage_pct": round(pct),
        "surface": "unit-testable-logic",
        "raw": round(pct, 2),
        "test_files": len(files),
        "test_functions": funcs,
        "floors": {"seal": floors["seal"], "adr": floors["adr"], "broad": floors["broad"]},
    }


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin write adapter
    ap = argparse.ArgumentParser(description="write coverage-summary.json")
    ap.add_argument("--pct", type=float, required=True, help="measured broad-surface percentage")
    ap.add_argument("--seal", type=int, required=True)
    ap.add_argument("--adr", type=int, required=True)
    ap.add_argument("--broad", type=int, required=True)
    args = ap.parse_args(argv)

    summary = compute(
        args.pct,
        {"seal": args.seal, "adr": args.adr, "broad": args.broad},
        proc=Proc(),
        repo=Repo(REPO_ROOT),
    )
    out = REPO_ROOT / SUMMARY_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
