#!/usr/bin/env python3
"""Tests for the checks.py registry query interface.

These pin the small public surface — is_blocking() and signature_check_ids() —
that validate_claims_parity and gate.py consume in place of regex-parsing this
module's source text.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import unittest

import _fixture  # noqa: E402

_fixture.bootstrap()

import checks  # noqa: E402


class IsBlocking(unittest.TestCase):
    def test_gpg_is_blocking(self):
        self.assertTrue(checks.is_blocking("gpg"))

    def test_a_known_advisory_is_not_blocking(self):
        # no_orphan_images is registered _A (advisory).
        self.assertFalse(checks.is_blocking("no_orphan_images"))

    def test_missing_id_is_not_blocking(self):
        # a removed/renamed check fails any meta-check that requires it blocking.
        self.assertFalse(checks.is_blocking("this_check_does_not_exist"))

    def test_agrees_with_blocking_list(self):
        blocking_ids = {c.id for c in checks.blocking()}
        for c in checks.REGISTRY:
            self.assertEqual(checks.is_blocking(c.id), c.id in blocking_ids, c.id)


class SignatureCheckIds(unittest.TestCase):
    def test_exact_set(self):
        self.assertEqual(checks.signature_check_ids(), ("gpg", "integrity_sig_freshness"))

    def test_every_flagged_check_is_blocking(self):
        for cid in checks.signature_check_ids():
            self.assertTrue(checks.is_blocking(cid), cid)

    def test_flag_matches_field(self):
        flagged = {c.id for c in checks.REGISTRY if c.requires_signature}
        self.assertEqual(set(checks.signature_check_ids()), flagged)


class RegistryIntegrity(unittest.TestCase):
    def test_ids_are_unique(self):
        ids = [c.id for c in checks.REGISTRY]
        self.assertEqual(len(ids), len(set(ids)), "duplicate check id in REGISTRY")

    def test_index_covers_registry(self):
        self.assertEqual(set(checks._BY_ID), {c.id for c in checks.REGISTRY})


if __name__ == "__main__":
    unittest.main()
