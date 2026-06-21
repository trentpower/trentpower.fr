#!/usr/bin/env python3
"""sync_coverage.py — keep the published TEST COVERAGE figure in lock-step with
what the pipeline actually measured.

The number is NOT hand-set. `tools/quality/coverage.sh` measures the
unit-testable-logic surface (tools/quality + tools/lib + tools/verify, excluding
tests/gate/lint — the same set as its enforced "broad" floor, NOT the raw global
which counts the integration-tested build generators) and writes the integer
percentage to `.build/coverage/coverage-summary.json`. This tool reads that figure
and propagates it to the four places the number lives:

  1. metadata/badges/badges.json   — the `coverage` mark's value
  2. metadata/badges/coverage.svg  — regenerated from badges.json
  3. README.md                     — the badge alt text `Test Coverage: N%`
  4. docs/COVERAGE.md              — the `Current figure: N%` line

All other coverage prose is referential (no hard-coded digits), so nothing else
drifts. `build.sh` runs `--write` (auto-update); CI runs `--check` (drift gate).

Usage:
    python3 tools/badges/sync_coverage.py --write   # update badge + docs from the measurement
    python3 tools/badges/sync_coverage.py --check    # exit 1 if any of them is stale
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(next(_a for _a in Path(__file__).resolve().parents if _a.name == "tools") / "lib"),
)
import generate_badges  # noqa: E402  (sibling renderer — single source of SVG geometry)
from paths import REPO_ROOT  # noqa: E402

SUMMARY_PATH = REPO_ROOT / ".build" / "coverage" / "coverage-summary.json"
BADGES_JSON = REPO_ROOT / "metadata" / "badges" / "badges.json"
COVERAGE_SVG = REPO_ROOT / "metadata" / "badges" / "coverage.svg"
README = REPO_ROOT / "README.md"
COVERAGE_DOC = REPO_ROOT / "docs" / "COVERAGE.md"

README_RE = re.compile(r"Test Coverage: \d+%")
DOC_RE = re.compile(r"Current figure: \d+%")


def measured_pct() -> int:
    """The integer figure the pipeline measured. Raises if coverage has not run."""
    if not SUMMARY_PATH.is_file():
        raise SystemExit(
            f"sync_coverage: {SUMMARY_PATH.relative_to(REPO_ROOT)} missing — "
            "run `bash tools/quality/coverage.sh` first."
        )
    return int(json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))["test_coverage_pct"])


def write(pct: int) -> list[str]:
    """Propagate `pct` to every owned location. Returns the list of files changed."""
    changed = []

    data = json.loads(BADGES_JSON.read_text(encoding="utf-8"))
    mark = next(m for m in data["marks"] if m["id"] == "coverage")
    if mark["value"] != f"{pct}%":
        mark["value"] = f"{pct}%"
        BADGES_JSON.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        changed.append("metadata/badges/badges.json")

    # regenerate the SVG from the (now-current) badges.json
    svg = generate_badges.colophon_svg(mark["label"], mark["value"])
    if not COVERAGE_SVG.is_file() or COVERAGE_SVG.read_text(encoding="utf-8") != svg:
        COVERAGE_SVG.write_text(svg, encoding="utf-8")
        changed.append("metadata/badges/coverage.svg")

    for path, rx, repl, label in (
        (README, README_RE, f"Test Coverage: {pct}%", "README.md"),
        (COVERAGE_DOC, DOC_RE, f"Current figure: {pct}%", "docs/COVERAGE.md"),
    ):
        text = path.read_text(encoding="utf-8")
        new = rx.sub(repl, text)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed.append(label)
    return changed


def check(pct: int) -> list[str]:
    """Return a list of human-readable drift descriptions (empty = coherent)."""
    drift = []

    data = json.loads(BADGES_JSON.read_text(encoding="utf-8"))
    mark = next(m for m in data["marks"] if m["id"] == "coverage")
    if mark["value"] != f"{pct}%":
        drift.append(f"badges.json coverage value is {mark['value']!r}, measured {pct}%")

    if f"Test Coverage: {pct}%" not in README.read_text(encoding="utf-8"):
        drift.append(f"README.md badge alt is not 'Test Coverage: {pct}%'")

    if f"Current figure: {pct}%" not in COVERAGE_DOC.read_text(encoding="utf-8"):
        drift.append(f"docs/COVERAGE.md is not 'Current figure: {pct}%'")

    svg = COVERAGE_SVG.read_text(encoding="utf-8") if COVERAGE_SVG.is_file() else ""
    if f"Test Coverage: {pct}%" not in svg:
        drift.append(f"coverage.svg does not render {pct}%")
    return drift


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    pct = measured_pct()
    if "--check" in argv:
        drift = check(pct)
        if drift:
            print(f"STALE: published TEST COVERAGE does not match the measured {pct}%:")
            for d in drift:
                print(f"  - {d}")
            print("run `python3 tools/badges/sync_coverage.py --write` and commit the result")
            return 1
        print(f"OK: published TEST COVERAGE matches the measured {pct}%")
        return 0

    changed = write(pct)
    if changed:
        print(f"synced TEST COVERAGE = {pct}% → {', '.join(changed)}")
    else:
        print(f"OK: TEST COVERAGE already {pct}% (no change)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
