#!/usr/bin/env python3
"""Tests for the signing-status trust-claim gate
(tools/verify/validate_signing_status.py).

Cross `evaluate(repo, Ctx)` over a fixture public/ tree and assert on the
Result; the ExternalInterface case runs `main(REPO_ROOT)` against the real repo
and asserts the baseline exit code.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import json
import pathlib
import tempfile
import unittest

import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_signing_status as vss  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

# a clearsigned prose header so a directly_signed artefact can carry an
# inline PGP block, exactly as assertion.txt / statement.txt do.
_CLEARSIGN = "-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA512\n\nbody\n"


def _seed_pristine(root: pathlib.Path) -> None:
    """write a minimal public/ tree where every classified artefact matches
    its declared signing class."""
    # the manifest covers exactly the covered_by_manifest paths (minus the
    # two self-evidencing ones the validator never expects in the manifest).
    covered = [
        rel
        for rel, klass in vss.CLASSIFICATION
        if klass == "covered_by_manifest" and rel not in ("integrity.json", "site-metadata.json")
    ]
    manifest = {"files": {rel: {} for rel in covered}}
    _write(root, "public/integrity.json", json.dumps(manifest))

    for rel, klass in vss.CLASSIFICATION:
        if klass == "directly_signed":
            # inline clearsigned form satisfies the gate.
            _write(root, f"public/{rel}", _CLEARSIGN)
        elif klass == "signature_carrier":
            # carrier needs its target present; carrier body is arbitrary.
            _write(root, f"public/{rel}", "signature bytes")
            target = rel[: -len(".sig")]
            # integrity.json.sig's target is the manifest, already written above;
            # don't clobber it with a stub.
            if target != "integrity.json":
                _write(root, f"public/{target}", "{}")
        elif klass == "covered_by_manifest":
            # integrity.json was already written above as the manifest; don't
            # clobber it. site-metadata.json is self-evidencing — a plain stub
            # is fine but it must not overwrite the manifest either.
            if rel == "integrity.json":
                continue
            # plain text-like body, no clearsign block (would trip the leak check).
            _write(root, f"public/{rel}", "{}" if rel.endswith(".json") else "text\n")


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vss.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _ctx(self) -> vss.Ctx:
        ctx, errors = vss.load(self.repo)
        self.assertEqual(errors, [], msg=errors)
        self.assertIsNotNone(ctx)
        return ctx

    def test_pristine_fixture_green(self):
        _seed_pristine(self.root)
        r = vss.evaluate(self.repo, self._ctx())
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.oks, len(vss.CLASSIFICATION))

    def test_directly_signed_missing_sig_caught(self):
        # seed everything, then strip the inline block AND the paired .sig
        # from a directly_signed artefact so neither coverage form is present.
        _seed_pristine(self.root)
        _write(self.root, "public/assertion.txt", "plain prose, no signature\n")
        r = vss.evaluate(self.repo, self._ctx())
        self.assertFalse(r.ok)
        self.assertTrue(
            any("assertion.txt: claims directly_signed" in f for f in r.fails), r.fails
        )

    def test_covered_by_manifest_class_mismatch_caught(self):
        # drop a covered_by_manifest artefact from integrity.json's file set:
        # the file is on disk but the manifest no longer covers it.
        _seed_pristine(self.root)
        manifest = json.loads((self.root / "public/integrity.json").read_text())
        manifest["files"].pop("humans.txt", None)
        _write(self.root, "public/integrity.json", json.dumps(manifest))
        r = vss.evaluate(self.repo, self._ctx())
        self.assertFalse(r.ok)
        self.assertTrue(
            any("humans.txt: claims covered_by_manifest" in f for f in r.fails), r.fails
        )

    def test_missing_on_disk_caught(self):
        # delete classified artefacts entirely: the missing-on-disk branch fires
        # before any per-class logic. deleting a covered_by_manifest file too
        # exercises the leak check's "file absent → skip" guard.
        _seed_pristine(self.root)
        (self.root / "public/statement.txt").unlink()
        (self.root / "public/humans.txt").unlink()
        r = vss.evaluate(self.repo, self._ctx())
        self.assertFalse(r.ok)
        self.assertTrue(
            any("statement.txt: missing on disk" in f for f in r.fails), r.fails
        )
        self.assertTrue(
            any("humans.txt: missing on disk" in f for f in r.fails), r.fails
        )

    def test_signature_carrier_orphan_target_caught(self):
        # the lone signature_carrier (integrity.json.sig) targets the manifest.
        # delete the manifest but keep its carrier on disk: the carrier now
        # points at a missing target. (the carrier file itself is reseeded since
        # the pristine seed treats integrity.json as the manifest body, not a
        # carrier stub.)
        _seed_pristine(self.root)
        _write(self.root, "public/integrity.json.sig", "signature bytes")
        (self.root / "public/integrity.json").unlink()
        # no manifest on disk → empty file set; that is the correct Ctx here.
        r = vss.evaluate(self.repo, self._ctx())
        self.assertFalse(r.ok)
        self.assertTrue(
            any("signature_carrier but target" in f for f in r.fails), r.fails
        )

    def test_covered_by_manifest_clearsign_leak_caught(self):
        # a covered_by_manifest text file must not carry an inline clearsigned
        # block — that is a hidden upgrade of its signing status (the leak check).
        _seed_pristine(self.root)
        _write(self.root, "public/humans.txt", _CLEARSIGN)
        r = vss.evaluate(self.repo, self._ctx())
        self.assertFalse(r.ok)
        self.assertTrue(
            any("contains a clearsigned block" in f for f in r.fails), r.fails
        )

    def test_no_manifest_yields_empty_ctx(self):
        # load() with no integrity.json on disk yields an empty file set, exactly
        # as the former _load_integrity_files() did.
        ctx, errors = vss.load(self.repo)
        self.assertEqual(errors, [])
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.integrity_files, set())


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vss.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_main_renders_fail_on_seeded_defect(self):
        # the FAIL-render adapter branch: seed a pristine fixture, then strip a
        # directly_signed artefact's coverage so evaluate() fails. main() over
        # that fixture root must print a FAIL line and return exit code 1.
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _seed_pristine(root)
            _write(root, "public/assertion.txt", "plain prose, no signature\n")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vss.main(root)

        out = buf.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("FAIL", out)
        self.assertIn("signing-status mismatch", out)


if __name__ == "__main__":
    unittest.main()
