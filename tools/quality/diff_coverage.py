#!/usr/bin/env python3
"""tools/quality/diff_coverage.py — the changed-line coverage ratchet.

The surface floors in tools/quality/coverage.sh gate the whole-tree TOTAL, so a
weak new module hides in the average: a file could ship at 60% and the broad 85%
floor never fires. This gate closes that hole — it judges the lines a change
actually touches. Every changed, executable line in an in-scope source file must
be covered at or above DIFF_MIN, or the gate fails and names the uncovered lines.

It adds NO measurement pass: it reads the per-file `executed_lines` / `missing_lines`
that coverage.sh already wrote to `.build/coverage/coverage.json`, intersects them
with the added/modified lines from `git diff`, and reports. `# pragma: no cover`
lines land in coverage.py's `excluded_lines` (neither executed nor missing), so
they never count against a change — the native escape hatch.

ADR-0002 shape: load()/evaluate()/main() with the work behind injected seams
(Repo for the coverage JSON, Proc for `git diff`), so evaluate() is pure and the
whole gate is testable from a fixture coverage map + a canned diff string
(tools/quality/tests/test_diff_coverage.py).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_TOOLS = next(_a for _a in Path(__file__).resolve().parents if _a.name == "tools")
sys.path.insert(0, str(_TOOLS / "lib"))

from paths import REPO_ROOT  # noqa: E402
from proc import Proc  # noqa: E402  (subprocess evidence seam)
from repo import Repo  # noqa: E402  (filesystem evidence seam)

# the bar for changed lines. >= the broad floor (85); raise it as code climbs,
# never lower. escape an unavoidable line with `# pragma: no cover`.
DIFF_MIN = 90

# where coverage.sh writes the per-file line map (gitignored, .build/).
COVERAGE_JSON = ".build/coverage/coverage.json"

# the in-scope surface — mirrors coverage.sh surface 3 (the broad quality-policy
# set). only changes to these files are judged; everything else is reported and
# skipped, exactly as the surface floors ignore it.
_SCOPE_PREFIXES = ("tools/quality/", "tools/lib/", "tools/verify/")
_SCOPE_EXCLUDE = ("tools/quality/gate.py", "tools/quality/lint.py")

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def in_scope(path: str) -> bool:
    """True iff a changed file is part of the unit-testable-logic surface."""
    if not path.endswith(".py"):
        return False
    if path.startswith("tools/quality/tests/"):
        return False
    if path in _SCOPE_EXCLUDE:
        return False
    return path.startswith(_SCOPE_PREFIXES)


# ── report shape ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FileVerdict:
    path: str
    status: str  # pass | fail | unmeasured | skip-out-of-scope | skip-no-coverable
    covered: int = 0
    coverable: int = 0
    ratio: float = 100.0  # percent; 100.0 when nothing coverable changed
    uncovered_lines: list[int] = field(default_factory=list)


@dataclass
class DiffCoverageReport:
    threshold: int
    files: list[FileVerdict] = field(default_factory=list)
    ok: bool = True


_FAILING = ("fail", "unmeasured")


# ── parse: added/modified NEW-file line numbers per path ─────────────────────


def parse_changed_lines(diff_text: str) -> dict[str, set[int]]:
    """Map each path to the set of its added/modified NEW-file line numbers.

    A line is "changed" if the diff marks it `+` (added or the new side of a
    modification). Removed lines have no new-file number and are ignored.
    """
    changed: dict[str, set[int]] = {}
    path: str | None = None
    newno = 0
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            if target == "/dev/null":
                path = None
            else:
                # strip the leading "b/" git prefix when present.
                path = target[2:] if target.startswith("b/") else target
            continue
        if line.startswith("--- ") or line.startswith("diff --git") or line.startswith("index "):
            continue
        if line.startswith("\\"):
            # "\ No newline at end of file" — refers to the preceding -/+ line and
            # consumes no new-file line number; advancing here would shift the
            # following added line one too high and slip an uncovered change past.
            continue
        m = _HUNK_RE.match(line)
        if m:
            newno = int(m.group(1))
            continue
        if path is None:
            continue
        if line.startswith("+"):
            changed.setdefault(path, set()).add(newno)
            newno += 1
        elif line.startswith("-"):
            # removed line — no advance on the new side.
            pass
        else:
            # context (or "\ No newline at end of file" — harmless to advance).
            newno += 1
    return changed


# ── evaluate: pure. no print, no exit, no I/O ────────────────────────────────


def evaluate(coverage_data: dict, diff_text: str, threshold: int) -> DiffCoverageReport:
    files_cov = coverage_data.get("files", {})
    changed = parse_changed_lines(diff_text)
    verdicts: list[FileVerdict] = []

    for path in sorted(changed):
        added = changed[path]
        if not in_scope(path):
            verdicts.append(FileVerdict(path, "skip-out-of-scope"))
            continue
        fdata = files_cov.get(path)
        if fdata is None:
            # an in-scope source file the suite never imported — untested by
            # construction. Fail, listing the changed lines.
            verdicts.append(
                FileVerdict(
                    path,
                    "unmeasured",
                    covered=0,
                    coverable=len(added),
                    ratio=0.0,
                    uncovered_lines=sorted(added),
                )
            )
            continue
        executed = set(fdata.get("executed_lines", []))
        missing = set(fdata.get("missing_lines", []))
        coverable = added & (executed | missing)
        if not coverable:
            # the changed lines were comments / blanks / pragma-excluded.
            verdicts.append(FileVerdict(path, "skip-no-coverable"))
            continue
        covered = added & executed
        ratio = 100.0 * len(covered) / len(coverable)
        status = "pass" if ratio >= threshold else "fail"
        verdicts.append(
            FileVerdict(
                path,
                status,
                covered=len(covered),
                coverable=len(coverable),
                ratio=round(ratio, 1),
                uncovered_lines=sorted(added & missing),
            )
        )

    ok = not any(v.status in _FAILING for v in verdicts)
    return DiffCoverageReport(threshold=threshold, files=verdicts, ok=ok)


# ── load + main: build real seams, emit ──────────────────────────────────────


def load_coverage(repo: Repo, rel: str) -> dict:
    raw = repo.read(rel)
    if not raw:
        raise SystemExit(
            f"diff_coverage: {rel} missing — run `bash tools/quality/coverage.sh` first."
        )
    return json.loads(raw)


def git_diff(proc: Proc, base: str) -> str:
    """Changes between the merge-base with `base` and the WORKING TREE.

    Diffing the working tree (not HEAD) against the merge-base means the gate
    judges exactly the code coverage.sh measured — including uncommitted local
    edits, so `make diff-coverage` is useful before a commit. In CI the working
    tree equals the PR head, so this is identical to the PR's `base...HEAD` diff.
    """
    mb = proc.run(["git", "merge-base", base, "HEAD"], cwd=REPO_ROOT)
    if mb.returncode != 0:
        raise SystemExit(
            f"diff_coverage: `git merge-base {base} HEAD` failed (rc={mb.returncode}): "
            f"{mb.stderr.strip()}"
        )
    base_sha = mb.stdout.strip()
    res = proc.run(["git", "diff", "--unified=0", "--no-color", base_sha], cwd=REPO_ROOT)
    if res.returncode != 0:
        raise SystemExit(
            f"diff_coverage: `git diff {base_sha}` failed (rc={res.returncode}): "
            f"{res.stderr.strip()}"
        )
    return res.stdout


def _render(report: DiffCoverageReport) -> None:
    print(f"diff coverage — changed lines must be >= {report.threshold}%")
    judged = [v for v in report.files if v.status in ("pass", "fail")]
    if not judged and not any(v.status == "unmeasured" for v in report.files):
        print("  no in-scope changed lines — nothing to gate.")
    for v in report.files:
        if v.status == "pass":
            print(f"  [ok]   {v.path}  {v.covered}/{v.coverable} ({v.ratio}%)")
        elif v.status == "fail":
            print(f"  [FAIL] {v.path}  {v.covered}/{v.coverable} ({v.ratio}%)")
            print(f"         uncovered changed lines: {v.uncovered_lines}")
        elif v.status == "unmeasured":
            print(f"  [FAIL] {v.path}  not exercised by the suite (no test imports it)")
            print(f"         changed lines: {v.uncovered_lines}")
        elif v.status == "skip-out-of-scope":
            print(f"  [skip] {v.path}  out of coverage surface")
        elif v.status == "skip-no-coverable":
            print(f"  [skip] {v.path}  no executable lines changed")
    print("OK: changed lines meet the bar." if report.ok else "FAIL: changed lines below the bar.")


def main(
    argv: list[str] | None = None, *, repo: Repo | None = None, proc: Proc | None = None
) -> int:
    # seams are injectable so tests drive main() over a fixture coverage map + a
    # canned diff, with no real repo / git (ADR-0002). Production passes neither.
    ap = argparse.ArgumentParser(description="gate coverage of changed lines")
    ap.add_argument("--base", default="origin/main", help="base ref/sha to diff against")
    ap.add_argument("--threshold", type=int, default=DIFF_MIN, help="minimum percent")
    ap.add_argument("--coverage-json", default=COVERAGE_JSON, help="coverage.json path")
    ap.add_argument("--json", action="store_true", help="emit the machine-readable report")
    args = ap.parse_args(argv)

    repo = repo or Repo(REPO_ROOT)
    coverage_data = load_coverage(repo, args.coverage_json)
    diff_text = git_diff(proc or Proc(), args.base)
    report = evaluate(coverage_data, diff_text, args.threshold)

    if args.json:
        print(json.dumps(dataclasses.asdict(report), indent=2))
    else:
        _render(report)

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
