#!/usr/bin/env python3
"""Tests for the claim-to-control honesty gate (tools/verify/validate_claims_parity.py).

These cross the module's interface — `evaluate(Repo, data) -> Result` and
`load_map(Repo)` — over a tiny fixture repo built per test. No monkeypatching:
the fixture repo IS the second adapter (production repo being the first), so the
control seam is real, not hypothetical. Tests assert on the returned Result,
never on stdout or internal state, so they survive internal refactors.

Stdlib unittest — no pytest dep.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_claims_parity as vcp  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent


def _make_fixture_repo(root: pathlib.Path) -> None:
    """A minimal repo where every backing control passes and the public surface
    (README.md) states every claimed token."""
    _write(
        root,
        ".github/workflows/release.yml",
        "steps:\n"
        "  - uses: actions/attest-build-provenance@v1\n"
        "    permissions: { id-token: write }\n"
        "  - run: python -m cyclonedx_py requirements\n"
        "  - run: jq .bomFormat sbom.json\n"
        "  - run: tar --sort=name --numeric-owner -cf a.tar . && gzip -n a.tar\n",
    )
    _write(
        root,
        ".github/workflows/pr-checks.yml",
        "steps:\n  - run: osv-scanner .\n  - run: reuse lint\n",
    )
    _write(root, ".github/workflows/scorecard.yml", "steps:\n  - uses: ossf/scorecard-action@v2\n")
    _write(root, "tools/build/build.sh", "#!/bin/sh\n# supports --check\n")
    _write(root, "REUSE.toml", "version = 1\n")
    _write(root, "public/.well-known/pgp-key.asc", "-----BEGIN PGP PUBLIC KEY BLOCK-----\n")
    # NOTE: the gpg/pr_gate "registered as blocking" meta-check now consults the
    # live checks.py registry through checks.is_blocking(), not a planted file —
    # so no fixture checks.py is written here (see test_checks_registry.py for the
    # is_blocking unit tests).
    _write(
        root,
        "README.md",
        "Trust: SLSA Sigstore Rekor attest CycloneDX SBOM PGP OpenSSF Scorecard "
        "OSV REUSE deterministic reproducible build.\n",
    )


def _claim(**over):
    base = {
        "public_wording": "wording",
        "severity": "high",
        "stated_in": ["README.md"],
        "verified_by": [],
        "enforced_at": ["release"],
        "status": "enforced",
        "release_blocking": False,
        "owner": "maintainer",
        "last_reviewed": "2026-06-18",
        "review_cadence": "per-release",
    }
    base.update(over)
    return base


def _base_data():
    """A full map binding every control_* once, so the orphan-control meta-check
    is satisfied by default and individual tests can break one thing at a time."""
    return {
        "claim_surface": {"include": ["*.md"], "exclude": []},
        "claims": {
            "SLSA": _claim(
                verified_by=["control_attestation"], severity="critical", release_blocking=True
            ),
            "SBOM": _claim(verified_by=["control_sbom"], release_blocking=True),
            "PGP": _claim(
                verified_by=["control_pgp"],
                enforced_at=["pr-gate"],
                pr_gate_check="gpg",
                severity="critical",
                release_blocking=True,
            ),
            "Scorecard": _claim(
                verified_by=["control_scorecard"], enforced_at=["pr-gate"], severity="medium"
            ),
            "OSV": _claim(verified_by=["control_osv"], enforced_at=["pr-gate"], severity="medium"),
            "REUSE": _claim(
                verified_by=["control_reuse"], enforced_at=["pr-gate"], severity="medium"
            ),
            "deterministic": _claim(verified_by=["control_deterministic"], release_blocking=True),
            "reproducib": _claim(
                verified_by=["control_reproducible"],
                enforced_at=["pr-gate"],
                status="goal",
                severity="low",
            ),
        },
    }


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _make_fixture_repo(self.root)
        self.repo = vcp.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pristine_all_backed(self):
        r = vcp.evaluate(self.repo, _base_data())
        self.assertTrue(r.ok, msg=f"meta={r.meta_fails} parity={r.parity_fails}")
        self.assertEqual(r.meta_fails, [])
        self.assertEqual(r.parity_fails, [])
        self.assertEqual(r.backed, 8)
        self.assertTrue(r.claimed_any)

    def test_unbacked_claim_cites_the_page(self):
        # remove the osv-scanner step so control_osv fails for the OSV claim.
        _write(self.root, ".github/workflows/pr-checks.yml", "steps:\n  - run: reuse lint\n")
        r = vcp.evaluate(self.repo, _base_data())
        self.assertFalse(r.ok)
        self.assertTrue(
            any('"OSV"' in f and "README.md" in f for f in r.parity_fails), r.parity_fails
        )

    def test_stated_in_outside_surface_fails(self):
        _write(self.root, "docs/x.md", "SLSA\n")  # exists but not matched by include "*.md"
        data = _base_data()
        data["claims"]["SLSA"]["stated_in"] = ["README.md", "docs/x.md"]
        r = vcp.evaluate(self.repo, data)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("outside the scanned" in f and "docs/x.md" in f for f in r.meta_fails), r.meta_fails
        )

    def test_nonexistent_control_fails(self):
        data = _base_data()
        data["claims"]["SLSA"]["verified_by"] = ["control_bogus"]
        r = vcp.evaluate(self.repo, data)
        self.assertFalse(r.ok)
        self.assertTrue(any("not a control_* function" in f for f in r.meta_fails), r.meta_fails)

    def test_orphan_control_fails(self):
        data = _base_data()
        del data["claims"]["reproducib"]  # leaves control_reproducible bound by nothing
        r = vcp.evaluate(self.repo, data)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("orphan control" in f and "control_reproducible" in f for f in r.meta_fails),
            r.meta_fails,
        )

    def test_goal_must_not_be_release_blocking(self):
        data = _base_data()
        data["claims"]["reproducib"]["release_blocking"] = True
        r = vcp.evaluate(self.repo, data)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("status goal must not be release_blocking" in f for f in r.meta_fails), r.meta_fails
        )

    def test_ruleset_enforced_at_is_a_note_not_a_failure(self):
        data = _base_data()
        data["claims"]["OSV"]["enforced_at"] = ["ruleset"]
        data["claims"]["OSV"]["release_blocking"] = True
        r = vcp.evaluate(self.repo, data)
        # ruleset wiring is advisory: it surfaces a note, never a meta failure.
        self.assertTrue(
            any('"OSV"' in n and "ruleset" in n for n in r.ruleset_notes), r.ruleset_notes
        )
        self.assertTrue(r.ok, msg=f"meta={r.meta_fails}")

    def test_pr_gate_check_pointing_at_non_blocking_fails(self):
        # a release_blocking pr-gate claim whose pr_gate_check names a check that
        # is NOT blocking in the live registry must fail — this is the regression
        # the former regex guarded, now via checks.is_blocking().
        data = _base_data()
        data["claims"]["PGP"]["pr_gate_check"] = "nav_regression"  # a real _A (advisory) id
        r = vcp.evaluate(self.repo, data)
        self.assertFalse(r.ok)
        self.assertTrue(
            any('"PGP"' in f and "not registered as blocking" in f for f in r.meta_fails),
            r.meta_fails,
        )

    def test_pr_gate_release_blocking_without_check_id_fails(self):
        data = _base_data()
        data["claims"]["PGP"].pop("pr_gate_check")
        r = vcp.evaluate(self.repo, data)
        self.assertFalse(r.ok)
        self.assertTrue(
            any('"PGP"' in f and "requires a pr_gate_check" in f for f in r.meta_fails),
            r.meta_fails,
        )

    def test_absent_token_requires_nothing(self):
        # a surface with no claimed tokens passes even with no controls exercised.
        _write(self.root, "README.md", "nothing to see here.\n")
        r = vcp.evaluate(self.repo, _base_data())
        self.assertTrue(r.ok)
        self.assertFalse(r.claimed_any)

    def test_missing_pgp_key_fails_the_pgp_claim(self):
        # control_pgp first checks the published key on disk; remove it and the
        # PGP claim is reported unbacked with the "published key missing" detail.
        (self.root / "public/.well-known/pgp-key.asc").unlink()
        r = vcp.evaluate(self.repo, _base_data())
        self.assertFalse(r.ok)
        self.assertTrue(
            any('"PGP"' in f and "published key missing" in f for f in r.parity_fails),
            r.parity_fails,
        )

    def test_missing_reuse_toml_fails_the_reuse_claim(self):
        # control_reuse first checks REUSE.toml on disk; remove it and the REUSE
        # claim is reported unbacked with the "REUSE.toml is missing" detail.
        (self.root / "REUSE.toml").unlink()
        r = vcp.evaluate(self.repo, _base_data())
        self.assertFalse(r.ok)
        self.assertTrue(
            any('"REUSE"' in f and "REUSE.toml is missing" in f for f in r.parity_fails),
            r.parity_fails,
        )

    def test_stated_in_path_does_not_exist_fails(self):
        # a stated_in path that is not on disk fails the integrity meta-check
        # with the "does not exist" message (distinct from the outside-surface case).
        data = _base_data()
        data["claims"]["SLSA"]["stated_in"] = ["README.md", "NOPE.md"]
        r = vcp.evaluate(self.repo, data)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("does not exist" in f and "NOPE.md" in f for f in r.meta_fails), r.meta_fails
        )

    def test_enforced_status_with_empty_verified_by_fails(self):
        # status enforced demands a non-empty verified_by; an enforced claim with
        # no bound control is an integrity failure.
        data = _base_data()
        data["claims"]["SBOM"]["verified_by"] = []
        r = vcp.evaluate(self.repo, data)
        self.assertFalse(r.ok)
        self.assertTrue(
            any('"SBOM"' in f and "verified_by is empty" in f for f in r.meta_fails), r.meta_fails
        )


class QuoteFirstLine(unittest.TestCase):
    def test_quotes_the_first_matching_line_stripped(self):
        text = "irrelevant\n  CycloneDX SBOM here  \nlater\n"
        self.assertEqual(vcp._quote_first_line(text, "CycloneDX"), "CycloneDX SBOM here")

    def test_returns_empty_when_token_absent(self):
        # the no-match path: token not on any line yields the empty-string fallback.
        self.assertEqual(vcp._quote_first_line("a\nb\nc\n", "ZZZ"), "")


class MainRender(unittest.TestCase):
    """Drive main()'s side-effecting render block over fixture repos: the
    schema-error path, the FAIL path, and the no-claims OK path."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _make_fixture_repo(self.root)
        # main() loads the map from disk + schema-validates, so a real schema and
        # a serialised valid map must be on the fixture repo.
        _write(
            self.root,
            "schemas/claims-map.schema.json",
            (REPO_ROOT / "schemas" / "claims-map.schema.json").read_text(encoding="utf-8"),
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _run_main(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vcp.main(self.root)
        return rc, buf.getvalue()

    def _write_map(self, data):
        import yaml

        _write(self.root, "policy-data/claims-map.yml", yaml.safe_dump(data))

    def test_main_schema_error_renders_fail_and_returns_1(self):
        # a structurally invalid map fails schema validation: main() renders the
        # schema-failure block and returns 1 before evaluate() runs.
        data = _base_data()
        del data["claims"]["SBOM"]["verified_by"]  # required key removed
        self._write_map(data)
        rc, out = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("does not satisfy", out)

    def test_main_parity_fail_renders_unbacked_block_and_returns_1(self):
        # remove the osv-scanner step so the OSV claim is unbacked: main() renders
        # the "unbacked supply-chain claim(s)" FAIL block and returns 1.
        _write(self.root, ".github/workflows/pr-checks.yml", "steps:\n  - run: reuse lint\n")
        self._write_map(_base_data())
        rc, out = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("unbacked supply-chain claim(s)", out)
        self.assertIn("OSV", out)

    def test_main_meta_fail_renders_integrity_block_and_returns_1(self):
        # an orphan control is an integrity (meta) failure: main() renders the
        # "claims-map integrity problem(s)" block and returns 1.
        data = _base_data()
        del data["claims"]["reproducib"]  # orphans control_reproducible
        self._write_map(data)
        rc, out = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("integrity problem(s)", out)

    def test_main_ruleset_note_rendered(self):
        # a ruleset-enforced claim surfaces a NOTE line; the run still passes.
        data = _base_data()
        data["claims"]["OSV"]["enforced_at"] = ["ruleset"]
        data["claims"]["OSV"]["release_blocking"] = True
        self._write_map(data)
        rc, out = self._run_main()
        self.assertEqual(rc, 0, msg=out)
        self.assertIn("NOTE:", out)

    def test_main_no_claims_on_surface_renders_ok(self):
        # a surface with no claimed tokens hits the "no supply-chain claims" OK
        # branch and returns 0.
        _write(self.root, "README.md", "nothing claimed here.\n")
        self._write_map(_base_data())
        rc, out = self._run_main()
        self.assertEqual(rc, 0, msg=out)
        self.assertIn("no supply-chain claims", out)


class LoadMap(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        # the real schema is the contract under test.
        _write(
            self.root,
            "schemas/claims-map.schema.json",
            (REPO_ROOT / "schemas" / "claims-map.schema.json").read_text(encoding="utf-8"),
        )
        self.repo = vcp.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_schema_break_returns_errors(self):
        import yaml

        data = _base_data()
        del data["claims"]["SBOM"]["verified_by"]  # required key missing
        _write(self.root, "policy-data/claims-map.yml", yaml.safe_dump(data))
        out, errors = vcp.load_map(self.repo)
        self.assertIsNone(out)
        self.assertTrue(errors)
        self.assertTrue(any("verified_by" in e for e in errors), errors)

    def test_valid_map_returns_data(self):
        import yaml

        _write(self.root, "policy-data/claims-map.yml", yaml.safe_dump(_base_data()))
        out, errors = vcp.load_map(self.repo)
        self.assertEqual(errors, [])
        self.assertIsNotNone(out)
        self.assertIn("claims", out)

    def test_missing_map_returns_missing_or_empty_error(self):
        # no claims-map.yml on disk: load_map returns (None, ["...missing or empty"]).
        out, errors = vcp.load_map(self.repo)
        self.assertIsNone(out)
        self.assertTrue(any("missing or empty" in e for e in errors), errors)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vcp.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
