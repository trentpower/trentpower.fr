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


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vss.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
