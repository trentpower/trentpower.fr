#!/usr/bin/env python3
"""Tests for validate_release.py — the release verification gate, exercised
through its ADR-0002 seams.

The whole compute path runs over a fixture repo (Repo seam) and a FakeProc
(Proc seam): the gate re-run and every gpg verification are canned, so no real
gate.py, gpg, or host keyring is touched. Tests assert on the Result that
evaluate() returns, never on stdout — main() owns rendering and is verified
against the captured baseline separately.

Run:
    python3 -m unittest discover -s tools/quality/tests -p 'test_release.py'
"""

import unittest

import _fixture

_fixture.bootstrap()

import pathlib  # noqa: E402
import tempfile  # noqa: E402
import zipfile  # noqa: E402

import validate_release as vr  # noqa: E402
from _fixture import FakeProc, proc_result  # noqa: E402
from _fixture import write as _write  # noqa: E402
from hashing import sri_sha256  # noqa: E402
from repo import Repo  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

# a comfortably-future Expires so the 60-day window check is green.
FUTURE_EXPIRES = "2099-01-01T00:00:00.000Z"
EDITION = "2026-06-14"


def _make_fixture_repo(root: pathlib.Path, *, tamper_manifest: bool = False) -> None:
    """Build a minimal but coherent release tree the six checks read:
    gate.py (presence only), security.txt, a redistributable manifest whose
    declared hashes match a real zip, the trust-anchor + exclusion manifests
    with sidecar .sig files, the published key, and live integrity.json. The
    gpg verifications themselves are canned by the FakeProc, so the .sig and
    key files only need to EXIST; their bytes are never checked here."""
    # gate.py — run_predeploy only checks it exists (the Proc seam runs it).
    _write(root, "tools/quality/gate.py", "# fixture gate\n")

    # R1 — security.txt with a future Expires.
    _write(
        root,
        "public/.well-known/security.txt",
        f"Contact: mailto:trent@trentpower.fr\nExpires: {FUTURE_EXPIRES}\n",
    )

    # published key + live integrity manifest.
    _write(root, "public/.well-known/pgp-key.asc", "-----BEGIN PGP PUBLIC KEY BLOCK-----\n")
    _write(
        root,
        "public/integrity.json",
        '{"files": {"app.js": "sha256-LIVEHASH"}}',
    )

    rel = f"public/integrity/releases/{EDITION}"

    # R2 — a real zip plus a manifest whose declared hashes match its bytes.
    payload = {"index.html": b"<!doctype html>\n", "app.js": b"console.log(1)\n"}
    zip_path = root / rel / f"trentpower-fr-{EDITION}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, data in payload.items():
            zf.writestr(name, data)
    files = {name: sri_sha256(data) for name, data in payload.items()}
    if tamper_manifest:
        # claim a hash the archive bytes do not produce — manifest drift.
        files["app.js"] = "sha256-TAMPEREDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    _write(
        root,
        f"{rel}/integrity-redistributable.json",
        _json({"edition": EDITION, "files": files}),
    )
    _write(root, f"{rel}/integrity-redistributable.json.sig", "SIG\n")

    # R4 — trust anchor.
    _write(root, f"{rel}/release.json", _json({"edition": EDITION}))
    _write(root, f"{rel}/release.json.sig", "SIG\n")

    # R5 / R6 — exclusion manifest with a live_sha256 that matches integrity.json.
    _write(
        root,
        f"{rel}/EXCLUDED_FILES.json",
        _json({"exclusions": [{"path": "app.js", "live_sha256": "sha256-LIVEHASH"}]}),
    )
    _write(root, f"{rel}/EXCLUDED_FILES.json.sig", "SIG\n")


def _json(obj) -> str:
    import json

    return json.dumps(obj)


def _gpg_ok_handler(argv, cwd, env):
    """gate run -> rc 0; gpg import + verify -> rc 0 (Good signature)."""
    if argv[:1] == ["gpg"]:
        return proc_result(0, "", "Good signature")
    # the gate re-run (sys.executable gate.py).
    return proc_result(0, "GATE OK\n")


class GreenPath(unittest.TestCase):
    def test_all_six_checks_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture_repo(root)
            r = vr.evaluate(Repo(root), FakeProc(_gpg_ok_handler))
            self.assertTrue(r.ok, msg=f"unexpected fails: {r.fails}")
            self.assertEqual(r.gate_rc, 0)
            self.assertEqual(len(r.steps), 6)
            # every reached step passed.
            self.assertTrue(all(rc == 0 for _, _, _, rc in r.steps))


class GateShortCircuits(unittest.TestCase):
    def test_gate_nonzero_skips_release_checks(self):
        def handler(argv, cwd, env):
            if argv[:1] == ["gpg"]:
                return proc_result(0, "", "Good signature")
            return proc_result(1, "", "gate blocked")  # gate fails

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture_repo(root)
            r = vr.evaluate(Repo(root), FakeProc(handler))
            self.assertFalse(r.ok)
            self.assertEqual(r.gate_rc, 1)
            # short-circuit: no release step was reached.
            self.assertEqual(r.steps, [])

    def test_missing_gate_fails_before_release_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture_repo(root)
            (root / "tools/quality/gate.py").unlink()
            r = vr.evaluate(Repo(root), FakeProc(_gpg_ok_handler))
            self.assertFalse(r.ok)
            self.assertIsNotNone(r.gate_missing_line)
            self.assertEqual(r.steps, [])


class SignatureFailure(unittest.TestCase):
    def test_gpg_verify_failure_caught_at_first_signature_step(self):
        def handler(argv, cwd, env):
            if argv[:1] == ["gpg"]:
                if "--verify" in argv:
                    return proc_result(2, "", "BAD signature from key")
                return proc_result(0)  # import succeeds
            return proc_result(0, "GATE OK\n")

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture_repo(root)
            r = vr.evaluate(Repo(root), FakeProc(handler))
            self.assertFalse(r.ok)
            # R1 + R2 pass; R3 (redistributable signature) is the first verify.
            self.assertEqual(len(r.steps), 3)
            last_no, last_label, last_lines, last_rc = r.steps[-1]
            self.assertEqual(last_no, 3)
            self.assertEqual(last_rc, 1)
            joined = "\n".join(last_lines)
            self.assertIn("does not verify", joined)
            self.assertIn("BAD signature", joined)


class ManifestDrift(unittest.TestCase):
    def test_tampered_manifest_hash_caught_at_step_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture_repo(root, tamper_manifest=True)
            r = vr.evaluate(Repo(root), FakeProc(_gpg_ok_handler))
            self.assertFalse(r.ok)
            # R1 passes, R2 (manifest byte-equality) is the failing step.
            self.assertEqual(len(r.steps), 2)
            step_no, label, lines, rc = r.steps[-1]
            self.assertEqual(step_no, 2)
            self.assertEqual(rc, 1)
            joined = "\n".join(lines)
            self.assertIn("redistributable-manifest issue", joined)


if __name__ == "__main__":
    unittest.main()
