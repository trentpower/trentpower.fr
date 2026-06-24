#!/usr/bin/env python3
"""sync_coverage.py — keep the published TEST COVERAGE figure in lock-step with
what the pipeline actually measured.

The number is NOT hand-set. `tools/quality/coverage.sh` measures the
unit-testable-logic surface (tools/quality + tools/lib + tools/verify, excluding
tests/gate/lint — the same set as its enforced "broad" floor, NOT the raw global
which counts the integration-tested build generators) and writes the integer
percentage — plus the source-derived suite size (test files + test functions) —
to `.build/coverage/coverage-summary.json`. This tool reads those figures and
propagates them to the places the numbers live:

  1. metadata/badges/badges.json   — the `coverage` mark's value
  2. metadata/badges/coverage.svg  — regenerated from badges.json
  3. README.md                     — the badge alt text `Test Coverage: N%` and
                                     the `**N** unit-test functions across **N** files` line
  4. docs/COVERAGE.md              — the `Current figure: N%` line and the
                                     test-inventory counts (`**N** unit-test files`,
                                     `**N,NNN** test functions`)

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
BUILD_DEPLOY_DOC = REPO_ROOT / "docs" / "BUILD-AND-DEPLOYMENT.md"

README_RE = re.compile(r"Test Coverage: \d+%")
DOC_RE = re.compile(r"Current figure: \d+%")
# the test-inventory counts (source-derived in coverage.sh; gated here).
README_INV_RE = re.compile(r"\*\*[\d,]+\*\* unit-test functions across \*\*[\d,]+\*\* files")
FILES_RE = re.compile(r"\*\*[\d,]+\*\* unit-test files")
FUNCS_RE = re.compile(r"\*\*[\d,]+\*\* test functions")


def _floor_entries(floors: dict) -> list[tuple[Path, re.Pattern, str]]:
    """(path, regex, replacement) for every place the coverage-surface FLOOR
    numbers are advertised. The floors live once in tools/quality/coverage-floors.sh
    and are written into the summary JSON; this keeps the docs that quote them in
    lock-step (same idea as the coverage figure above). The COVERAGE.md cell
    regexes capture the table padding so a same-width number swap stays aligned;
    drift is detected by "would a write change the file?", so no fragile parsing."""
    seal, adr, broad = floors["seal"], floors["adr"], floors["broad"]
    return [
        # docs/BUILD-AND-DEPLOYMENT.md prose: "floors 95/95/95" (every occurrence)
        (BUILD_DEPLOY_DOC, re.compile(r"floors \d+/\d+/\d+"), f"floors {seal}/{adr}/{broad}"),
        # docs/COVERAGE.md surface table — the floor cell of each row
        (
            COVERAGE_DOC,
            re.compile(r"(convergence \+ seal[^\n|]*\|\s*)\d+(%)"),
            rf"\g<1>{seal}\g<2>",
        ),
        (COVERAGE_DOC, re.compile(r"(ADR-0002 validators[^\n|]*\|\s*)\d+(%)"), rf"\g<1>{adr}\g<2>"),
        (
            COVERAGE_DOC,
            re.compile(r"(broad quality-policy[^\n|]*\|\s*)\d+(%)"),
            rf"\g<1>{broad}\g<2>",
        ),
    ]


def measured() -> dict:
    """The figures the pipeline measured. Raises if coverage has not run."""
    if not SUMMARY_PATH.is_file():
        raise SystemExit(
            f"sync_coverage: {SUMMARY_PATH.relative_to(REPO_ROOT)} missing — "
            "run `bash tools/quality/coverage.sh` first."
        )
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def measured_pct() -> int:
    """The integer coverage figure the pipeline measured."""
    return int(measured()["test_coverage_pct"])


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

    m = measured()
    files, funcs = int(m["test_files"]), int(m["test_functions"])
    for path, rx, repl, label in (
        (README, README_RE, f"Test Coverage: {pct}%", "README.md"),
        (
            README,
            README_INV_RE,
            f"**{funcs:,}** unit-test functions across **{files:,}** files",
            "README.md",
        ),
        (COVERAGE_DOC, DOC_RE, f"Current figure: {pct}%", "docs/COVERAGE.md"),
        (COVERAGE_DOC, FILES_RE, f"**{files:,}** unit-test files", "docs/COVERAGE.md"),
        (COVERAGE_DOC, FUNCS_RE, f"**{funcs:,}** test functions", "docs/COVERAGE.md"),
    ):
        text = path.read_text(encoding="utf-8")
        new = rx.sub(repl, text)
        if new != text:
            path.write_text(new, encoding="utf-8")
            if label not in changed:
                changed.append(label)

    # advertised coverage-surface floors, propagated from the single source.
    floors = m.get("floors")
    if floors:
        for path, rx, repl in _floor_entries(floors):
            text = path.read_text(encoding="utf-8")
            new = rx.sub(repl, text)
            if new != text:
                path.write_text(new, encoding="utf-8")
                if path.name not in changed:
                    changed.append(path.name)
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

    m = measured()
    files, funcs = int(m["test_files"]), int(m["test_functions"])
    readme = README.read_text(encoding="utf-8")
    if f"**{funcs:,}** unit-test functions across **{files:,}** files" not in readme:
        drift.append(
            f"README.md inventory is not '**{funcs:,}** unit-test functions "
            f"across **{files:,}** files'"
        )
    doc = COVERAGE_DOC.read_text(encoding="utf-8")
    if f"**{files:,}** unit-test files" not in doc:
        drift.append(f"docs/COVERAGE.md inventory is not '**{files:,}** unit-test files'")
    if f"**{funcs:,}** test functions" not in doc:
        drift.append(f"docs/COVERAGE.md inventory is not '**{funcs:,}** test functions'")

    # advertised coverage-surface floors — stale iff a --write would change them.
    floors = m.get("floors")
    if floors:
        fl = f"{floors['seal']}/{floors['adr']}/{floors['broad']}"
        for path, rx, repl in _floor_entries(floors):
            text = path.read_text(encoding="utf-8")
            if rx.sub(repl, text) != text:
                drift.append(
                    f"{path.name} advertises a stale coverage floor "
                    f"(expected {fl}; raise it in tools/quality/coverage-floors.sh)"
                )
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
