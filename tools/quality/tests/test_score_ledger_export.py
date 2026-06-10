#!/usr/bin/env python3
"""Test the score-ledger audit JSON export.

The score-ledger SQLite is local-only (gitignored, lives on the Pi), so these
tests skip gracefully when no ledger DB is present. Where it exists, they
assert the export builds the standardized audit envelope from the latest
recorded run -- no fresh live audit is run. Stdlib unittest.
"""

import json
import pathlib
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SL_DIR = REPO_ROOT / "tools" / "score-ledger"
LEDGER_DB = SL_DIR / "data" / "score-ledger.sqlite"

sys.path.insert(0, str(SL_DIR))
sys.path.insert(0, str(REPO_ROOT / "tools" / "lib"))


@unittest.skipUnless(LEDGER_DB.exists(), "no local score-ledger DB (expected off the Pi)")
class AuditExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import db
        import lib
        import score_ledger

        cls.score_ledger = score_ledger
        cls.cfg = lib.load_config(None)
        cls.conn = db.connect(cls.cfg)
        db.migrate(cls.conn)
        cls.run_id = score_ledger._latest_run_id(cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_latest_run_exists(self):
        self.assertIsNotNone(self.run_id, "expected at least one finished run in the ledger")

    def test_envelope_shape(self):
        rep = self.score_ledger._audit_report(self.conn, self.cfg, self.run_id)
        self.assertEqual(rep["schema_version"], 1)
        self.assertEqual(rep["command"], "audit")
        self.assertIn(rep["status"], ("passed", "failed"))
        self.assertTrue(rep["generated_at"].endswith("Z"))
        self.assertEqual(rep["run"]["run_id"], self.run_id)
        self.assertIsInstance(rep["run"]["targets"], list)
        self.assertTrue(rep["scorecards"], "expected scorecards")
        # status must be observational-derived: failed iff a FAIL scorecard exists.
        has_fail = any(str(c["status"]).upper() == "FAIL" for c in rep["scorecards"])
        self.assertEqual(rep["status"], "failed" if has_fail else "passed")
        # headline metrics carry the rolling_median baseline key.
        for h in rep["headline_metrics"]:
            self.assertIn("rolling_median", h)

    def test_writes_valid_json_only_where_told(self):
        rep = self.score_ledger._audit_report(self.conn, self.cfg, self.run_id)
        import check_report

        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d) / "last-audit.json"
            check_report.atomic_write_json(rep, out)
            loaded = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(loaded["command"], "audit")


if __name__ == "__main__":
    unittest.main()
