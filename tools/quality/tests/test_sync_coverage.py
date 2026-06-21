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


def _seed(root: Path, pct: int, files: int = 65, funcs: int = 1029) -> None:
    """Write a coherent fixture at TEST COVERAGE = pct% with the given suite size."""
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
        f"[![Test Coverage: {pct}%](metadata/badges/coverage.svg)]\n", encoding="utf-8"
    )
    sc.COVERAGE_DOC.write_text(
        f"> **Current figure: {pct}%** — auto-derived.\n"
        f"The suite is currently **{files:,}** unit-test files / **{funcs:,}** test functions.\n",
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
        # measured 94 but every figure location still says 90 → drift on all four
        # (suite size stays coherent, so only the percentage drifts)
        _seed(Path(self._tmp.name), 90)
        sc.SUMMARY_PATH.write_text(
            json.dumps({"test_coverage_pct": 94, "test_files": 65, "test_functions": 1029}),
            encoding="utf-8",
        )
        drift = sc.check(94)
        self.assertEqual(len(drift), 4, drift)
        self.assertEqual(sc.main(["--check"]), 1)

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

    def test_seeded_count_drift_fails_check(self):
        # coverage figure matches, but the documented suite size is stale
        _seed(Path(self._tmp.name), 94, files=60, funcs=1000)
        sc.SUMMARY_PATH.write_text(
            json.dumps({"test_coverage_pct": 94, "test_files": 65, "test_functions": 1029}),
            encoding="utf-8",
        )
        drift = sc.check(94)
        self.assertEqual(len(drift), 2, drift)  # files + functions, nothing else
        self.assertEqual(sc.main(["--check"]), 1)

    def test_write_repairs_count_drift(self):
        _seed(Path(self._tmp.name), 94, files=60, funcs=1000)
        sc.SUMMARY_PATH.write_text(
            json.dumps({"test_coverage_pct": 94, "test_files": 65, "test_functions": 1029}),
            encoding="utf-8",
        )
        changed = sc.write(94)
        self.assertEqual(changed, ["docs/COVERAGE.md"])  # only the inventory shifted
        doc = sc.COVERAGE_DOC.read_text(encoding="utf-8")
        self.assertIn("**65** unit-test files", doc)
        self.assertIn("**1,029** test functions", doc)
        self.assertEqual(sc.check(94), [])


if __name__ == "__main__":
    unittest.main()
