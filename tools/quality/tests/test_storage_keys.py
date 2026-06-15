#!/usr/bin/env python3
"""Tests for the browser-storage-key allowlist gate
(tools/quality/validate_storage_keys.py)."""

import pathlib
import sys
import unittest

_TOOLS = pathlib.Path(__file__).resolve().parents[2]
for _sub in ("lib", "build", "quality", "verify", "release"):
    sys.path.insert(0, str(_TOOLS / _sub))

import validate_storage_keys as vsk  # noqa: E402

EXACT = {"tp-theme", "tp-last-edition", "tp-last-read:/en-au/", "tp-last-read:/fr/"}
PREFIX = {"tp-welcomed:", "tp-typed-"}


class ParseAllowlist(unittest.TestCase):
    def test_splits_exact_and_prefix(self):
        src = (
            "var LOCAL_KEYS = [\n"
            "{ key: 'tp-theme', storage: 'local', prefix: false },\n"
            "{ key: 'tp-welcomed:', storage: 'session', prefix: true }\n"
            "];\n"
        )
        exact, prefix = vsk.parse_allowlist(src)
        self.assertEqual(exact, {"tp-theme"})
        self.assertEqual(prefix, {"tp-welcomed:"})


class Approved(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(vsk.approved("tp-theme", EXACT, PREFIX))

    def test_prefix_match(self):
        self.assertTrue(vsk.approved("tp-typed-/foo", EXACT, PREFIX))

    def test_concatenation_root_of_allowlisted_key(self):
        # 'tp-last-read:/' is the literal root of 'tp-last-read:/en-au/'
        self.assertTrue(vsk.approved("tp-last-read:/", EXACT, PREFIX))

    def test_bare_stem_rejected(self):
        # the 'tp-' loophole must not earn approval via the concat-root clause
        self.assertFalse(vsk.approved("tp-", EXACT, PREFIX))

    def test_unknown_key_rejected(self):
        self.assertFalse(vsk.approved("tp-evil-tracker", EXACT, PREFIX))


class Resolve(unittest.TestCase):
    def test_string_literal(self):
        self.assertEqual(vsk.resolve("'tp-theme'", {}), "tp-theme")

    def test_concatenation_takes_literal_root(self):
        self.assertEqual(vsk.resolve("'tp-last-read:/' + v", {}), "tp-last-read:/")

    def test_module_constant(self):
        self.assertEqual(vsk.resolve("KEY", {"KEY": "tp-last-edition"}), "tp-last-edition")

    def test_dynamic_key_unresolved(self):
        self.assertIsNone(vsk.resolve("someVar", {}))


class LiveTreeGreen(unittest.TestCase):
    def test_current_public_surface_passes(self):
        self.assertEqual(vsk.main(), 0)


if __name__ == "__main__":
    unittest.main()
