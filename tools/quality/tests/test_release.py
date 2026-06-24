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

import contextlib  # noqa: E402
import datetime as dt  # noqa: E402
import io  # noqa: E402
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


class SecurityTxtExpires(unittest.TestCase):
    """R1 — check_security_txt_expires branches, called directly over a repo."""

    def _repo(self, root: pathlib.Path) -> Repo:
        return Repo(root)

    def test_missing_security_txt_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rc, lines = vr.check_security_txt_expires(self._repo(root))
            self.assertEqual(rc, 1)
            self.assertIn("missing", "\n".join(lines))

    def test_no_expires_line_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root, "public/.well-known/security.txt", "Contact: mailto:x@y\n")
            rc, lines = vr.check_security_txt_expires(self._repo(root))
            self.assertEqual(rc, 1)
            self.assertIn("no Expires", "\n".join(lines))

    def test_unparseable_expires_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root, "public/.well-known/security.txt", "Expires: not-a-date\n")
            rc, lines = vr.check_security_txt_expires(self._repo(root))
            self.assertEqual(rc, 1)
            self.assertIn("not parseable", "\n".join(lines))

    def test_expires_inside_window_fails(self):
        # an Expires only a few days out is inside the 60-day cushion.
        soon = (dt.datetime.now(dt.UTC) + dt.timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root, "public/.well-known/security.txt", f"Expires: {soon}\n")
            rc, lines = vr.check_security_txt_expires(self._repo(root))
            self.assertEqual(rc, 1)
            joined = "\n".join(lines)
            self.assertIn("window is", joined)

    def test_future_expires_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root, "public/.well-known/security.txt", f"Expires: {FUTURE_EXPIRES}\n")
            rc, lines = vr.check_security_txt_expires(self._repo(root))
            self.assertEqual(rc, 0)
            self.assertIn("OK", "\n".join(lines))


class FindReleaseDir(unittest.TestCase):
    """_find_release_dir + _current_exclusion_manifest pure helpers."""

    def test_no_releases_dir_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertIsNone(vr._find_release_dir(Repo(root)))

    def test_non_date_child_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            # a non-date directory must not be returned as a release dir.
            (root / "public/integrity/releases/scratch").mkdir(parents=True)
            self.assertIsNone(vr._find_release_dir(Repo(root)))
            # add a proper date dir; it is the one selected.
            (root / f"public/integrity/releases/{EDITION}").mkdir(parents=True)
            found = vr._find_release_dir(Repo(root))
            self.assertIsNotNone(found)
            self.assertEqual(found.name, EDITION)

    def test_dated_exclusion_manifest_preferred(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rel = root / f"public/integrity/releases/{EDITION}"
            rel.mkdir(parents=True)
            (rel / "EXCLUDED_FILES.json").write_text("{}")
            (rel / "EXCLUDED_FILES-2026-06-20.json").write_text("{}")
            chosen = vr._current_exclusion_manifest(rel)
            self.assertEqual(chosen.name, "EXCLUDED_FILES-2026-06-20.json")


class RedistributableManifest(unittest.TestCase):
    """R2 — check_redistributable_manifest failure branches."""

    def test_no_release_dir_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rc, lines = vr.check_redistributable_manifest(Repo(root))
            self.assertEqual(rc, 0)
            self.assertIn("nothing to check", "\n".join(lines))

    def test_manifest_missing_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / f"public/integrity/releases/{EDITION}").mkdir(parents=True)
            rc, lines = vr.check_redistributable_manifest(Repo(root))
            self.assertEqual(rc, 1)
            self.assertIn("missing", "\n".join(lines))

    def test_invalid_json_manifest_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rel = f"public/integrity/releases/{EDITION}"
            _write(root, f"{rel}/integrity-redistributable.json", "{not json")
            rc, lines = vr.check_redistributable_manifest(Repo(root))
            self.assertEqual(rc, 1)
            self.assertIn("invalid JSON", "\n".join(lines))

    def test_missing_files_map_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rel = f"public/integrity/releases/{EDITION}"
            _write(root, f"{rel}/integrity-redistributable.json", _json({"edition": EDITION}))
            rc, lines = vr.check_redistributable_manifest(Repo(root))
            self.assertEqual(rc, 1)
            self.assertIn("missing 'files' map", "\n".join(lines))

    def test_no_zip_and_no_checksum_seal_fails(self):
        # no local archive AND no committed .sha256 seal -> hard fail.
        # (server-canonical archives keep their checksum sidecar in git; an
        # edition with neither the binary nor its seal is genuinely broken.)
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rel = f"public/integrity/releases/{EDITION}"
            _write(
                root,
                f"{rel}/integrity-redistributable.json",
                _json({"edition": "9999-99-99", "files": {"a": "sha256-x"}}),
            )
            rc, lines = vr.check_redistributable_manifest(Repo(root))
            self.assertEqual(rc, 1)
            self.assertIn("neither a local archive nor a checksum seal", "\n".join(lines))

    def test_no_zip_but_checksum_seal_passes_server_canonical(self):
        # server-canonical state: the heavy .zip lives only on the live host,
        # but its committed .sha256 seal is present in git -> OK, with archive
        # byte-content verification deferred to an explicit remote step.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rel = f"public/integrity/releases/{EDITION}"
            _write(
                root,
                f"{rel}/integrity-redistributable.json",
                _json({"edition": "9999-99-99", "files": {"a": "sha256-x"}}),
            )
            _write(root, f"{rel}/trentpower-fr-9999-99-99.zip.sha256", "sha256-x  archive\n")
            rc, lines = vr.check_redistributable_manifest(Repo(root))
            self.assertEqual(rc, 0)
            self.assertIn("server-canonical", "\n".join(lines))

    def test_declared_path_not_in_zip_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rel = f"public/integrity/releases/{EDITION}"
            zip_path = root / rel / f"trentpower-fr-{EDITION}.zip"
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("index.html", b"<x>")
            # declare a path the archive does not contain.
            _write(
                root,
                f"{rel}/integrity-redistributable.json",
                _json(
                    {
                        "edition": EDITION,
                        "files": {
                            "index.html": sri_sha256(b"<x>"),
                            "ghost.js": "sha256-deadbeef",
                        },
                    }
                ),
            )
            rc, lines = vr.check_redistributable_manifest(Repo(root))
            self.assertEqual(rc, 1)
            joined = "\n".join(lines)
            self.assertIn("not in", joined)

    def test_archive_path_not_declared_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rel = f"public/integrity/releases/{EDITION}"
            zip_path = root / rel / f"trentpower-fr-{EDITION}.zip"
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("index.html", b"<x>")
                zf.writestr("extra.js", b"y")
            # declare only one of the two archive members.
            _write(
                root,
                f"{rel}/integrity-redistributable.json",
                _json({"edition": EDITION, "files": {"index.html": sri_sha256(b"<x>")}}),
            )
            rc, lines = vr.check_redistributable_manifest(Repo(root))
            self.assertEqual(rc, 1)
            self.assertIn("does not declare it", "\n".join(lines))

    def test_many_fails_truncated_to_twelve(self):
        # 14 ghost declarations exercise the ">12 -> ... (N more)" tail.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rel = f"public/integrity/releases/{EDITION}"
            zip_path = root / rel / f"trentpower-fr-{EDITION}.zip"
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("index.html", b"<x>")
            ghosts = {f"ghost{i}.js": "sha256-x" for i in range(14)}
            ghosts["index.html"] = sri_sha256(b"<x>")
            _write(
                root,
                f"{rel}/integrity-redistributable.json",
                _json({"edition": EDITION, "files": ghosts}),
            )
            rc, lines = vr.check_redistributable_manifest(Repo(root))
            self.assertEqual(rc, 1)
            joined = "\n".join(lines)
            self.assertIn("more)", joined)

    def test_canonical_zip_absent_uses_glob_candidate(self):
        # canonical name absent but a dated rebuild zip exists -> glob fallback.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rel = f"public/integrity/releases/{EDITION}"
            zip_path = root / rel / "trentpower-fr-2026-06-20.zip"
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("index.html", b"<x>")
            _write(
                root,
                f"{rel}/integrity-redistributable.json",
                _json({"edition": EDITION, "files": {"index.html": sri_sha256(b"<x>")}}),
            )
            rc, lines = vr.check_redistributable_manifest(Repo(root))
            self.assertEqual(rc, 0)
            self.assertIn("byte-for-byte", "\n".join(lines))


class RedistributableSignature(unittest.TestCase):
    """R3 — check_redistributable_signature branches."""

    def test_no_release_dir_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rc, lines = vr.check_redistributable_signature(Repo(root), FakeProc(_gpg_ok_handler))
            self.assertEqual(rc, 0)
            self.assertIn("nothing to verify", "\n".join(lines))

    def test_missing_manifest_or_sig_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / f"public/integrity/releases/{EDITION}").mkdir(parents=True)
            rc, lines = vr.check_redistributable_signature(Repo(root), FakeProc(_gpg_ok_handler))
            self.assertEqual(rc, 1)
            self.assertIn("missing", "\n".join(lines))

    def test_missing_published_key_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rel = f"public/integrity/releases/{EDITION}"
            _write(root, f"{rel}/integrity-redistributable.json", "{}")
            _write(root, f"{rel}/integrity-redistributable.json.sig", "SIG\n")
            rc, lines = vr.check_redistributable_signature(Repo(root), FakeProc(_gpg_ok_handler))
            self.assertEqual(rc, 1)
            self.assertIn("public key", "\n".join(lines))

    def test_key_import_failure_fails(self):
        def handler(argv, cwd, env):
            if argv[:1] == ["gpg"] and "--import" in argv:
                return proc_result(1, "", "import broke")
            return proc_result(0)

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture_repo(root)
            rc, lines = vr.check_redistributable_signature(Repo(root), FakeProc(handler))
            self.assertEqual(rc, 1)
            self.assertIn("could not import", "\n".join(lines))


class ReleaseJsonSignature(unittest.TestCase):
    """R4 — check_release_json_signature branches."""

    def test_no_release_dir_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rc, lines = vr.check_release_json_signature(Repo(root), FakeProc(_gpg_ok_handler))
            self.assertEqual(rc, 0)
            self.assertIn("nothing to verify", "\n".join(lines))

    def test_release_json_absent_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / f"public/integrity/releases/{EDITION}").mkdir(parents=True)
            rc, lines = vr.check_release_json_signature(Repo(root), FakeProc(_gpg_ok_handler))
            self.assertEqual(rc, 0)
            self.assertIn("predates phase 2", "\n".join(lines))

    def test_signature_failure_fails(self):
        def handler(argv, cwd, env):
            if argv[:1] == ["gpg"]:
                if "--verify" in argv:
                    return proc_result(2, "", "BAD")
                return proc_result(0)
            return proc_result(0)

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture_repo(root)
            rc, lines = vr.check_release_json_signature(Repo(root), FakeProc(handler))
            self.assertEqual(rc, 1)
            self.assertIn("does not verify", "\n".join(lines))


class VerifyDetachedSig(unittest.TestCase):
    """_verify_detached_sig low-level branches not hit elsewhere."""

    def test_missing_target_or_sig_reports_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root, "public/.well-known/pgp-key.asc", "KEY\n")
            target = root / "public/integrity/releases/x/release.json"
            sig = root / "public/integrity/releases/x/release.json.sig"
            target.parent.mkdir(parents=True, exist_ok=True)
            # neither target nor sig exist.
            ok, err = vr._verify_detached_sig(Repo(root), FakeProc(_gpg_ok_handler), target, sig)
            self.assertFalse(ok)
            self.assertIn("missing", err)

    def test_missing_published_key_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            # no public/.well-known/pgp-key.asc -> key-missing branch.
            target = root / "t.json"
            sig = root / "t.json.sig"
            target.write_text("{}")
            sig.write_text("SIG")
            ok, err = vr._verify_detached_sig(Repo(root), FakeProc(_gpg_ok_handler), target, sig)
            self.assertFalse(ok)
            self.assertIn("public key", err)

    def test_import_failure_reports(self):
        def handler(argv, cwd, env):
            if argv[:1] == ["gpg"] and "--import" in argv:
                return proc_result(1, "", "nope")
            return proc_result(0)

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root, "public/.well-known/pgp-key.asc", "KEY\n")
            target = root / "t.json"
            sig = root / "t.json.sig"
            target.write_text("{}")
            sig.write_text("SIG")
            ok, err = vr._verify_detached_sig(Repo(root), FakeProc(handler), target, sig)
            self.assertFalse(ok)
            self.assertIn("could not import", err)


class ExclusionManifestSignature(unittest.TestCase):
    """R5 — check_exclusion_manifest_signature branches."""

    def test_no_release_dir_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rc, lines = vr.check_exclusion_manifest_signature(Repo(root), FakeProc(_gpg_ok_handler))
            self.assertEqual(rc, 0)
            self.assertIn("nothing to verify", "\n".join(lines))

    def test_no_exclusion_manifest_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / f"public/integrity/releases/{EDITION}").mkdir(parents=True)
            rc, lines = vr.check_exclusion_manifest_signature(Repo(root), FakeProc(_gpg_ok_handler))
            self.assertEqual(rc, 0)
            self.assertIn("predates phase 1", "\n".join(lines))

    def test_signature_failure_fails(self):
        def handler(argv, cwd, env):
            if argv[:1] == ["gpg"]:
                if "--verify" in argv:
                    return proc_result(2, "", "BAD")
                return proc_result(0)
            return proc_result(0)

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture_repo(root)
            rc, lines = vr.check_exclusion_manifest_signature(Repo(root), FakeProc(handler))
            self.assertEqual(rc, 1)
            self.assertIn("does not verify", "\n".join(lines))


class ExclusionLiveCross(unittest.TestCase):
    """R6 — check_exclusion_live_sha256_cross branches."""

    def test_no_release_dir_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rc, lines = vr.check_exclusion_live_sha256_cross(Repo(root))
            self.assertEqual(rc, 0)
            self.assertIn("nothing to verify", "\n".join(lines))

    def test_no_integrity_json_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rel = f"public/integrity/releases/{EDITION}"
            _write(root, f"{rel}/EXCLUDED_FILES.json", _json({"exclusions": []}))
            # no public/integrity.json present.
            rc, lines = vr.check_exclusion_live_sha256_cross(Repo(root))
            self.assertEqual(rc, 0)
            self.assertIn("nothing to cross-check", "\n".join(lines))

    def test_invalid_json_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rel = f"public/integrity/releases/{EDITION}"
            _write(root, f"{rel}/EXCLUDED_FILES.json", "{not json")
            _write(root, "public/integrity.json", "{}")
            rc, lines = vr.check_exclusion_live_sha256_cross(Repo(root))
            self.assertEqual(rc, 1)
            self.assertIn("cannot parse", "\n".join(lines))

    def test_path_absent_from_live_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rel = f"public/integrity/releases/{EDITION}"
            _write(
                root,
                f"{rel}/EXCLUDED_FILES.json",
                _json({"exclusions": [{"path": "ghost.js", "live_sha256": "sha256-x"}]}),
            )
            _write(root, "public/integrity.json", _json({"files": {"app.js": "sha256-y"}}))
            rc, lines = vr.check_exclusion_live_sha256_cross(Repo(root))
            self.assertEqual(rc, 1)
            self.assertIn("not present in live", "\n".join(lines))

    def test_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rel = f"public/integrity/releases/{EDITION}"
            _write(
                root,
                f"{rel}/EXCLUDED_FILES.json",
                _json(
                    {
                        "exclusions": [
                            {"path": "app.js", "live_sha256": "sha256-CLAIMED"},
                            {"path": "skip.js"},  # no live_sha256 -> skipped
                        ]
                    }
                ),
            )
            _write(
                root,
                "public/integrity.json",
                _json({"files": {"/app.js": "sha256-ACTUAL"}}),
            )
            rc, lines = vr.check_exclusion_live_sha256_cross(Repo(root))
            self.assertEqual(rc, 1)
            joined = "\n".join(lines)
            self.assertIn("exclusion-cross-check issue", joined)

    def test_many_mismatches_truncated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rel = f"public/integrity/releases/{EDITION}"
            exclusions = [{"path": f"miss{i}.js", "live_sha256": "sha256-x"} for i in range(14)]
            _write(root, f"{rel}/EXCLUDED_FILES.json", _json({"exclusions": exclusions}))
            _write(root, "public/integrity.json", _json({"files": {}}))
            rc, lines = vr.check_exclusion_live_sha256_cross(Repo(root))
            self.assertEqual(rc, 1)
            self.assertIn("more)", "\n".join(lines))

    def test_all_match_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rel = f"public/integrity/releases/{EDITION}"
            _write(
                root,
                f"{rel}/EXCLUDED_FILES.json",
                _json({"exclusions": [{"path": "app.js", "live_sha256": "sha256-LIVEHASH"}]}),
            )
            _write(root, "public/integrity.json", _json({"files": {"app.js": "sha256-LIVEHASH"}}))
            rc, lines = vr.check_exclusion_live_sha256_cross(Repo(root))
            self.assertEqual(rc, 0)
            self.assertIn("match live integrity.json", "\n".join(lines))


class MainRender(unittest.TestCase):
    """main() owns stdout + exit codes; drive each render arm by canning the
    Result that evaluate() returns — no real gate.py / gpg / host keyring."""

    def setUp(self):
        self._saved = vr.evaluate
        self.addCleanup(self._restore)

    def _restore(self):
        vr.evaluate = self._saved

    def _run(self, result):
        vr.evaluate = lambda repo, proc: result
        with tempfile.TemporaryDirectory() as tmp:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vr.main(pathlib.Path(tmp))
        return rc, buf.getvalue()

    def test_gate_missing_returns_gate_rc(self):
        r = vr.Result(gate_rc=2, gate_missing_line="FAIL: gate.py not found")
        rc, out = self._run(r)
        self.assertEqual(rc, 2)
        self.assertIn("gate.py not found", out)

    def test_gate_failure_short_circuits(self):
        r = vr.Result(gate_rc=1, gate_stdout="gate ran\n")
        rc, out = self._run(r)
        self.assertEqual(rc, 1)
        self.assertIn("Running gate.py", out)

    def test_release_step_failure_returns_1(self):
        r = vr.Result(
            gate_rc=0,
            steps=[(1, "step one", ["line a"], 0), (2, "step two", ["bad"], 1)],
        )
        rc, out = self._run(r)
        self.assertEqual(rc, 1)
        self.assertIn("step two", out)

    def test_all_green_returns_0(self):
        r = vr.Result(gate_rc=0, steps=[(1, "step one", ["ok"], 0)])
        rc, out = self._run(r)
        self.assertEqual(rc, 0)
        self.assertIn("validate_release green", out)


if __name__ == "__main__":
    unittest.main()
