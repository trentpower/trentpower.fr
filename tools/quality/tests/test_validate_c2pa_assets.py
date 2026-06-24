#!/usr/bin/env python3
"""Tests for the C2PA Content-Credentials policy gate
(tools/quality/validate_c2pa_assets.py).

These cross the module's interface — `evaluate(Repo, data, inspect) -> Result`
and `load_policy(Repo)` — over a tiny fixture repo built per test. The C2PA
inspector is an injected seam, so no real signing keys and no c2pa library are
needed: a fake inspector IS the second adapter. Tests assert on the returned
Result, never on stdout, so they survive internal refactors.

Stdlib unittest — no pytest dep.

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

import validate_c2pa_assets as vca  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent

SVG_REL = "public/images/architecture/architecture.en.svg"
SVG_KEY = "images/architecture/architecture.en.svg"

# fake inspectors (the injected C2PA seam).
PRESENT = lambda repo, p: (True, "")  # noqa: E731
ABSENT = lambda repo, p: (False, "no manifest")  # noqa: E731
SKIP = lambda repo, p: (None, "c2pa tooling unavailable")  # noqa: E731


def _make_fixture_repo(root: pathlib.Path, *, integrity_has_svg: bool = True) -> None:
    _write(root, SVG_REL, "<svg xmlns='http://www.w3.org/2000/svg'></svg>\n")
    _write(
        root, "tools/config/identity_canonical.json", json.dumps({"url": "https://trentpower.fr"})
    )
    files = {SVG_KEY: "sha256-x"} if integrity_has_svg else {}
    _write(root, "public/integrity.json", json.dumps({"files": files}))


def _asset(**over):
    base = {
        "path": SVG_REL,
        "status": "required",
        "type": "diagram",
        "role": "authored-diagram",
        "canonical_url": "https://trentpower.fr/images/architecture/architecture.en.svg",
        "author": "Trent Power",
        "publisher": "trentpower.fr",
        "ai_involvement": "no-ai-in-release-path",
        "credential_mode": "embedded",
        "reason": "authored diagram",
    }
    base.update(over)
    return base


def _excluded(**over):
    base = {
        "path": "public/documentation/README.pdf",
        "status": "excluded",
        "reason": "no pdf embed",
    }
    base.update(over)
    return base


def _base_data(assets=None):
    return {
        "version": 1,
        "publisher": {"name": "trentpower.fr", "url": "https://trentpower.fr"},
        "ai_vocabulary": ["none", "no-ai-in-release-path", "unknown"],
        "credential_modes": ["embedded", "sidecar"],
        "assets": assets if assets is not None else [_asset(), _excluded()],
    }


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _make_fixture_repo(self.root)
        self.repo = vca.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pristine_required_signed_is_ok(self):
        r = vca.evaluate(self.repo, _base_data(), inspect=PRESENT)
        self.assertTrue(r.ok, msg=f"meta={r.meta_fails} asset={r.asset_fails}")
        self.assertEqual(r.declared, 2)
        self.assertEqual(r.by_status, {"required": 1, "excluded": 1})

    def test_required_missing_from_integrity_fails(self):
        _make_fixture_repo(self.root, integrity_has_svg=False)
        r = vca.evaluate(self.repo, _base_data(), inspect=PRESENT)
        self.assertFalse(r.ok)
        self.assertTrue(any("not listed in" in f for f in r.asset_fails), r.asset_fails)

    def test_required_without_credential_fails(self):
        r = vca.evaluate(self.repo, _base_data(), inspect=ABSENT)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("no embedded C2PA credential" in f for f in r.asset_fails), r.asset_fails
        )

    def test_required_credential_skip_is_note_not_fail(self):
        # tooling unavailable (None) must NOT fail the advisory gate — it notes.
        r = vca.evaluate(self.repo, _base_data(), inspect=SKIP)
        self.assertTrue(r.ok, msg=f"asset={r.asset_fails}")
        self.assertTrue(any("credential check skipped" in n for n in r.notes), r.notes)

    def test_future_asset_is_noted_not_required(self):
        # a `future` asset need not be in integrity nor carry a credential; it
        # only has to exist on disk. ABSENT inspector must not fail it.
        data = _base_data([_asset(status="future"), _excluded()])
        r = vca.evaluate(self.repo, data, inspect=ABSENT)
        self.assertTrue(r.ok, msg=f"asset={r.asset_fails}")
        self.assertTrue(any("status future" in n for n in r.notes), r.notes)

    def test_declared_asset_missing_on_disk_fails(self):
        (self.root / SVG_REL).unlink()
        r = vca.evaluate(self.repo, _base_data(), inspect=PRESENT)
        self.assertFalse(r.ok)
        self.assertTrue(any("not found on disk" in f for f in r.asset_fails), r.asset_fails)

    def test_ai_involvement_outside_vocabulary_fails(self):
        data = _base_data([_asset(ai_involvement="totally-made-up"), _excluded()])
        r = vca.evaluate(self.repo, data, inspect=PRESENT)
        self.assertFalse(r.ok)
        self.assertTrue(any("not in ai_vocabulary" in f for f in r.meta_fails), r.meta_fails)

    def test_canonical_url_not_under_publisher_fails(self):
        data = _base_data([_asset(canonical_url="https://evil.example/x.svg"), _excluded()])
        r = vca.evaluate(self.repo, data, inspect=PRESENT)
        self.assertFalse(r.ok)
        self.assertTrue(any("not under publisher url" in f for f in r.meta_fails), r.meta_fails)

    def test_publisher_disagrees_with_identity_fails(self):
        _write(
            self.root,
            "tools/config/identity_canonical.json",
            json.dumps({"url": "https://other.fr"}),
        )
        r = vca.evaluate(self.repo, _base_data(), inspect=PRESENT)
        self.assertFalse(r.ok)
        self.assertTrue(any("disagrees with identity" in f for f in r.meta_fails), r.meta_fails)

    def test_duplicate_path_fails(self):
        data = _base_data([_asset(), _asset(), _excluded()])
        r = vca.evaluate(self.repo, data, inspect=PRESENT)
        self.assertFalse(r.ok)
        self.assertTrue(any("duplicate asset entry" in f for f in r.meta_fails), r.meta_fails)

    def test_stale_excluded_pattern_is_note(self):
        data = _base_data(
            [_asset(), {"pattern": "public/nope/*.png", "status": "excluded", "reason": "x"}]
        )
        r = vca.evaluate(self.repo, data, inspect=PRESENT)
        self.assertTrue(r.ok, msg=f"meta={r.meta_fails} asset={r.asset_fails}")
        self.assertTrue(any("matches no files" in n for n in r.notes), r.notes)


class LoadPolicy(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _write(
            self.root,
            "schemas/c2pa-assets.schema.json",
            (REPO_ROOT / "schemas" / "c2pa-assets.schema.json").read_text(encoding="utf-8"),
        )
        self.repo = vca.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_policy_returns_error(self):
        out, errors = vca.load_policy(self.repo)
        self.assertIsNone(out)
        self.assertTrue(any("missing or empty" in e for e in errors), errors)

    def test_valid_policy_returns_data(self):
        _write(self.root, "policy-data/c2pa-assets.yml", _yaml(_base_data()))
        out, errors = vca.load_policy(self.repo)
        self.assertEqual(errors, [])
        self.assertIsNotNone(out)
        self.assertIn("assets", out)

    def test_excluded_without_reason_breaks_schema(self):
        data = _base_data([{"path": "public/x.png", "status": "excluded"}])  # no reason
        _write(self.root, "policy-data/c2pa-assets.yml", _yaml(data))
        out, errors = vca.load_policy(self.repo)
        self.assertIsNone(out)
        self.assertTrue(any("reason" in e for e in errors), errors)

    def test_in_scope_without_canonical_url_breaks_schema(self):
        bad = _asset()
        del bad["canonical_url"]
        _write(self.root, "policy-data/c2pa-assets.yml", _yaml(_base_data([bad])))
        out, errors = vca.load_policy(self.repo)
        self.assertIsNone(out)
        self.assertTrue(any("canonical_url" in e for e in errors), errors)


class MainRender(unittest.TestCase):
    """Drive main()'s side-effecting render over fixture repos."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _make_fixture_repo(self.root)
        _write(
            self.root,
            "schemas/c2pa-assets.schema.json",
            (REPO_ROOT / "schemas" / "c2pa-assets.schema.json").read_text(encoding="utf-8"),
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vca.main(self.root)
        return rc, buf.getvalue()

    def test_main_schema_error_returns_1(self):
        bad = _base_data([{"path": "public/x.png", "status": "excluded"}])  # missing reason
        _write(self.root, "policy-data/c2pa-assets.yml", _yaml(bad))
        rc, out = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("does not satisfy", out)

    def test_main_future_only_passes(self):
        # all assets future/excluded → coherent, no required conditions to meet.
        data = _base_data([_asset(status="future"), _excluded()])
        _write(self.root, "policy-data/c2pa-assets.yml", _yaml(data))
        rc, out = self._run()
        self.assertEqual(rc, 0, msg=out)
        self.assertIn("coherent", out)


class RealRepo(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vca.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


def _yaml(data):
    import yaml

    return yaml.safe_dump(data)


if __name__ == "__main__":
    unittest.main()
