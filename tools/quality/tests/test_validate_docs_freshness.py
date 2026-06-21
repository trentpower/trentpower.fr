#!/usr/bin/env python3
"""Tests for the documentation-freshness gate (validate_docs_freshness.py).

These cross the module's interface — `evaluate(repo, ctx, tracked, probe) ->
Result` and `load(repo)` — over a tiny fixture repo. The three environment seams
are injected: the fixture filesystem (`Repo(tmp)`), the git-tracked file SET
(passed directly, so no real `git`), and the coverage probe (a stub returning
(measured?, drift)). No monkeypatching, no .build tree, never the real repo.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import json
import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import render_proof  # noqa: E402
import validate_docs_freshness as vf  # noqa: E402
from _fixture import write as _write  # noqa: E402

# a coverage probe that reports a clean measurement.
_CLEAN_COV = lambda: (True, [])  # noqa: E731

_INVENTORY = {
    "required": ["README.md", "docs/COVERAGE.md", "docs/SCORE-LEDGER.md"],
    "flags": {
        "docs/COVERAGE.md": ["coverage_critical", "score_ledger_authority"],
        "docs/SCORE-LEDGER.md": ["score_ledger_authority"],
    },
}
_COMMANDS = {"_doc": "x", "gate": "python3 tools/quality/gate.py --all"}


def _make_fixture_repo(root: pathlib.Path) -> None:
    """A coherent docs repo: policy data, required docs, one canonical block, a
    positive score-ledger statement, and a correct README.pdf render proof."""
    _write(root, vf.INVENTORY_REL, json.dumps(_INVENTORY))
    _write(root, vf.COMMANDS_REL, json.dumps(_COMMANDS))
    _write(
        root,
        "README.md",
        "# Title\n\nRun the gate with `tools/quality/gate.py`.\n\n"
        "<!-- canonical-commands -->\n```sh\npython3 tools/quality/gate.py --all\n```\n",
    )
    _write(
        root,
        "docs/COVERAGE.md",
        "# Coverage\n\nScore-ledger is excluded; see [SCORE-LEDGER.md](SCORE-LEDGER.md).\n",
    )
    _write(
        root,
        "docs/SCORE-LEDGER.md",
        "# Score ledger\n\nScore-ledger **remains in this repository** by decision.\n",
    )
    # a correct render proof so the pristine fixture is fully green.
    _write(root, render_proof.README_HTML_REL, "<html>readme</html>")
    for rel in render_proof.ASSET_RELS:
        _write(root, rel, f"asset:{rel}")
    _write(root, render_proof.PDF_REL, "%PDF-1.4 fixture")
    _write(root, render_proof.PROOF_REL, json.dumps(render_proof.compute(root)))


def _tracked(root: pathlib.Path, *extra: str) -> set[str]:
    """The git-tracked set the fixture stands in for: every file on disk plus any
    extra repo-paths the docs reference but that need not exist as files."""
    files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    return files | set(extra)


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _make_fixture_repo(self.root)
        self.repo = vf.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _ctx(self):
        ctx, errors = vf.load(self.repo)
        self.assertEqual(errors, [])
        return ctx

    def _eval(self, tracked=None, probe=_CLEAN_COV):
        tracked = tracked if tracked is not None else _tracked(self.root, "tools/quality/gate.py")
        return vf.evaluate(self.repo, self._ctx(), tracked, probe)

    # --- pristine -----------------------------------------------------------
    def test_pristine_all_green(self):
        r = self._eval()
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.warns, [], msg=r.warns)

    # --- required docs ------------------------------------------------------
    def test_missing_required_doc_fails(self):
        (self.root / "docs/COVERAGE.md").unlink()
        r = self._eval()
        self.assertFalse(r.ok)
        self.assertTrue(any("required doc missing: docs/COVERAGE.md" in f for f in r.fails))

    # --- tracked paths ------------------------------------------------------
    def test_untracked_path_reference_fails(self):
        _write(self.root, "README.md", "See `tools/gone.py` for details.\n")
        r = self._eval()
        self.assertFalse(r.ok)
        self.assertTrue(any("tools/gone.py" in f for f in r.fails))

    def test_placeholder_glob_build_and_local_only_ignored(self):
        _write(
            self.root,
            "README.md",
            "Examples: `tools/quality/tests/test_<name>.py`, `tools/quality/*.py`, "
            "`.build/coverage/x.json`, `public/integrity/releases/<edition>/`, "
            "`public/integrity/releases/YYYY-MM/`, `docs/private/`, "
            "`tools/score-ledger/reports/`.\n",
        )
        # placeholders, globs, .build and gitignored local-only trees are skipped.
        r = self._eval()
        self.assertFalse(any("references" in f for f in r.fails), msg=r.fails)

    def test_interpreter_prefixed_command_path_checked(self):
        # the path inside `python3 tools/...` / `bash tools/...` must be checked,
        # not just the interpreter (Codex P2). a missing script fails.
        _write(self.root, "README.md", "Run `python3 tools/quality/gone.py --all`.\n")
        r = self._eval()
        self.assertFalse(r.ok)
        self.assertTrue(any("tools/quality/gone.py" in f for f in r.fails))

    def test_interpreter_prefixed_command_path_resolves(self):
        _write(self.root, "README.md", "Run `python3 tools/quality/gate.py --all`.\n")
        r = self._eval()
        self.assertTrue(r.ok, msg=r.fails)

    def test_directory_reference_validated(self):
        # a backticked directory reference must resolve via tracked prefix; a
        # renamed/deleted directory fails (Codex P2).
        _write(self.root, "README.md", "See `tools/quality/tests/` and `docs/gone-dir/`.\n")
        tracked = _tracked(self.root, "tools/quality/gate.py", "tools/quality/tests/test_x.py")
        r = self._eval(tracked=tracked)
        self.assertFalse(r.ok)
        self.assertTrue(any("docs/gone-dir/" in f for f in r.fails))
        self.assertFalse(any("tools/quality/tests/" in f for f in r.fails), msg=r.fails)

    # --- stale phrases ------------------------------------------------------
    def test_stale_phrase_fails(self):
        _write(
            self.root,
            "docs/COVERAGE.md",
            "# C\n\nThe coverage is advisory here.\n[x](SCORE-LEDGER.md)\n",
        )
        r = self._eval()
        self.assertFalse(r.ok)
        self.assertTrue(any("coverage is advisory" in f for f in r.fails))

    def test_stale_phrase_with_stale_ok_passes(self):
        _write(
            self.root,
            "docs/COVERAGE.md",
            "# C\n\nWe never say coverage is advisory. <!-- stale-ok -->\n[x](SCORE-LEDGER.md)\n",
        )
        r = self._eval()
        self.assertTrue(r.ok, msg=r.fails)

    # --- canonical commands -------------------------------------------------
    def test_canonical_block_drift_fails(self):
        _write(
            self.root,
            "README.md",
            "<!-- canonical-commands -->\n```sh\npython3 tools/quality/gate.py\n```\n",
        )
        r = self._eval()
        self.assertFalse(r.ok)
        self.assertTrue(any("canonical-commands block" in f for f in r.fails))

    def test_freeform_block_without_marker_ignored(self):
        _write(
            self.root,
            "README.md",
            "Run the gate with `tools/quality/gate.py`.\n\n"
            "```sh\npython3 tools/quality/gate.py --weird-flag\n```\n",
        )
        r = self._eval()
        self.assertTrue(r.ok, msg=r.fails)

    def test_canonical_command_missing_path_fails(self):
        _write(self.root, vf.COMMANDS_REL, json.dumps({"x": "bash tools/nope.sh"}))
        r = self._eval()
        self.assertFalse(r.ok)
        self.assertTrue(any("missing path" in f for f in r.fails))

    # --- coverage -----------------------------------------------------------
    def test_coverage_drift_fails(self):
        r = self._eval(probe=lambda: (True, ["badge says 90%, measured 94%"]))
        self.assertFalse(r.ok)
        self.assertTrue(any("coverage drift" in f for f in r.fails))

    def test_coverage_unmeasured_warns_not_fails(self):
        r = self._eval(probe=lambda: (False, []))
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("coverage not measured" in w for w in r.warns))

    # --- score ledger -------------------------------------------------------
    def test_score_ledger_decision_missing_fails(self):
        _write(self.root, "docs/SCORE-LEDGER.md", "# Score ledger\n\nIt is excluded.\n")
        r = self._eval()
        self.assertFalse(r.ok)
        self.assertTrue(any("positive retention statement" in f for f in r.fails))

    def test_coverage_doc_missing_crossref_fails(self):
        _write(self.root, "docs/COVERAGE.md", "# Coverage\n\nNo reference here.\n")
        r = self._eval()
        self.assertFalse(r.ok)
        self.assertTrue(any("cross-reference SCORE-LEDGER.md" in f for f in r.fails))

    # --- render proof -------------------------------------------------------
    def test_render_proof_mismatch_warns_not_fails(self):
        _write(self.root, render_proof.README_HTML_REL, "<html>CHANGED</html>")
        r = self._eval()
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("render proof stale" in w for w in r.warns))

    def test_render_proof_missing_warns_not_fails(self):
        (self.root / render_proof.PROOF_REL).unlink()
        r = self._eval()
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("render-proof.json missing" in w or "missing" in w for w in r.warns))

    # --- adr language -------------------------------------------------------
    def test_adr_language_warns(self):
        _write(
            self.root,
            "docs/COVERAGE.md",
            "# C\n\nWe prefer one big main() per script.\n[x](SCORE-LEDGER.md)\n",
        )
        r = self._eval()
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("ADR-0002" in w for w in r.warns))


class ExternalInterface(unittest.TestCase):
    """main() over the real repo — exercises the git + coverage-probe adapters
    and asserts the live documentation actually satisfies the gate."""

    def test_main_passes_against_the_real_repo(self):
        self.assertEqual(vf.main(TOOLS.parent), 0)


class Load(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_inventory_errors(self):
        ctx, errors = vf.load(vf.Repo(self.root))
        self.assertIsNone(ctx)
        self.assertTrue(errors)

    def test_invalid_json_errors(self):
        _write(self.root, vf.INVENTORY_REL, "{not json")
        _write(self.root, vf.COMMANDS_REL, "{}")
        ctx, errors = vf.load(vf.Repo(self.root))
        self.assertIsNone(ctx)
        self.assertTrue(any("invalid JSON" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
