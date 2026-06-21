#!/usr/bin/env python3
"""Test tools/badges/sync_coverage.py — the published TEST COVERAGE figure is
derived from the measurement and kept in lock-step across the badge + docs.

Clean fixture (all four locations already match the measured figure) passes
--check; a seeded defect (one stale number) fails it; --write repairs it. The
module's path constants are redirected at a temp repo so nothing touches the real
tree. Stdlib unittest.
"""

import json
import tempfile
import unittest
from pathlib import Path

import _fixture

_fixture.bootstrap("badges")
import sync_coverage as sc  # noqa: E402


def _seed(root: Path, pct: int, files: int = 67, funcs: int = 1063) -> None:
    """Write a coherent fixture at TEST COVERAGE = pct% with inventory files/funcs."""
    (root / ".build" / "coverage").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "metadata" / "badges").mkdir(parents=True, exist_ok=True)
    sc.SUMMARY_PATH.write_text(
        json.dumps(
            {
                "test_coverage_pct": pct,
                "surface": "unit-testable-logic",
                "test_files": files,
                "test_functions": funcs,
            }
        ),
        encoding="utf-8",
    )
    sc.BADGES_JSON.write_text(
        json.dumps({"marks": [{"id": "coverage", "label": "Test Coverage", "value": f"{pct}%"}]}),
        encoding="utf-8",
    )
    sc.README.write_text(
        f"[![Test Coverage: {pct}%](metadata/badges/coverage.svg)]\n"
        f"The suite is **{funcs:,}** unit-test functions across **{files:,}** files.\n",
        encoding="utf-8",
    )
    sc.COVERAGE_DOC.write_text(
        f"> **Current figure: {pct}%** — auto-derived.\n"
        f"**{files:,}** unit-test files / **{funcs:,}** test functions.\n",
        encoding="utf-8",
    )
    sc.COVERAGE_SVG.write_text(
        sc.generate_badges.colophon_svg("Test Coverage", f"{pct}%"), encoding="utf-8"
    )


class SyncCoverage(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        # redirect every owned path at the temp repo
        sc.SUMMARY_PATH = root / ".build" / "coverage" / "coverage-summary.json"
        sc.BADGES_JSON = root / "metadata" / "badges" / "badges.json"
        sc.COVERAGE_SVG = root / "metadata" / "badges" / "coverage.svg"
        sc.README = root / "README.md"
        sc.COVERAGE_DOC = root / "docs" / "COVERAGE.md"

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_fixture_passes_check(self):
        _seed(Path(self._tmp.name), 94)
        self.assertEqual(sc.check(94), [])
        self.assertEqual(sc.main(["--check"]), 0)

    def test_seeded_defect_fails_check(self):
        # fixture stale on every surface (90%, inventory 1/1) but measured is
        # 94% / 67 files / 1,063 functions → drift on all seven owned locations.
        _seed(Path(self._tmp.name), 90, files=1, funcs=1)
        sc.SUMMARY_PATH.write_text(
            json.dumps({"test_coverage_pct": 94, "test_files": 67, "test_functions": 1063}),
            encoding="utf-8",
        )
        drift = sc.check(94)
        self.assertEqual(len(drift), 7, drift)
        self.assertEqual(sc.main(["--check"]), 1)

    def test_write_repairs_inventory(self):
        _seed(Path(self._tmp.name), 94, files=1, funcs=1)
        sc.SUMMARY_PATH.write_text(
            json.dumps({"test_coverage_pct": 94, "test_files": 67, "test_functions": 1063}),
            encoding="utf-8",
        )
        sc.write(94)
        self.assertIn(
            "**1,063** unit-test functions across **67** files",
            sc.README.read_text(encoding="utf-8"),
        )
        self.assertIn("**67** unit-test files", sc.COVERAGE_DOC.read_text(encoding="utf-8"))
        self.assertIn("**1,063** test functions", sc.COVERAGE_DOC.read_text(encoding="utf-8"))
        self.assertEqual(sc.check(94), [])

    def test_write_repairs_drift(self):
        _seed(Path(self._tmp.name), 90)
        changed = sc.write(94)
        # all four owned locations rewritten
        self.assertEqual(len(changed), 4, changed)
        self.assertIn('"value": "94%"', sc.BADGES_JSON.read_text(encoding="utf-8"))
        self.assertIn("Test Coverage: 94%", sc.README.read_text(encoding="utf-8"))
        self.assertIn("Current figure: 94%", sc.COVERAGE_DOC.read_text(encoding="utf-8"))
        self.assertIn("Test Coverage: 94%", sc.COVERAGE_SVG.read_text(encoding="utf-8"))
        self.assertEqual(sc.check(94), [])

    def test_write_is_idempotent(self):
        _seed(Path(self._tmp.name), 94)
        self.assertEqual(sc.write(94), [])  # nothing to change


if __name__ == "__main__":
    unittest.main()
