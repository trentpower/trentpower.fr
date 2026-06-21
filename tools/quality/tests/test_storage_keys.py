#!/usr/bin/env python3
"""Tests for the browser-storage-key allowlist gate
(tools/quality/validate_storage_keys.py)."""

import unittest

import _fixture  # noqa: E402

_fixture.bootstrap("release")

import validate_storage_keys as vsk  # noqa: E402

# (key, is_prefix, store) triples — mirrors the LOCAL_KEYS contract.
ENTRIES = [
    ("tp-theme", False, "local"),
    ("tp-last-edition", False, "local"),
    ("tp-last-read:/en-au/", False, "local"),
    ("tp-last-read:/fr/", False, "local"),
    ("tp-welcomed:", True, "session"),
    ("tp-typed-", True, "session"),
]


class ParseAllowlist(unittest.TestCase):
    def test_parses_key_store_and_prefix(self):
        src = (
            "var LOCAL_KEYS = [\n"
            "{ key: 'tp-theme', storage: 'local', prefix: false },\n"
            "{ key: 'tp-welcomed:', storage: 'session', prefix: true }\n"
            "];\n"
        )
        self.assertEqual(
            vsk.parse_allowlist(src),
            [("tp-theme", False, "local"), ("tp-welcomed:", True, "session")],
        )

    def test_ignores_objects_outside_the_array(self):
        # a render-loop object literal after the array must not leak in.
        src = (
            "var LOCAL_KEYS = [\n"
            "{ key: 'tp-theme', storage: 'local', prefix: false }\n"
            "];\n"
            "rows.push({ key: k, value: v, storage: spec.storage });\n"
        )
        self.assertEqual(vsk.parse_allowlist(src), [("tp-theme", False, "local")])


class Approved(unittest.TestCase):
    def test_exact_match_same_store(self):
        self.assertTrue(vsk.approved("tp-theme", "local", ENTRIES))

    def test_prefix_match_same_store(self):
        self.assertTrue(vsk.approved("tp-typed-/foo", "session", ENTRIES))

    def test_concatenation_root_of_allowlisted_key(self):
        # 'tp-last-read:/' is the literal root of 'tp-last-read:/en-au/'
        self.assertTrue(vsk.approved("tp-last-read:/", "local", ENTRIES))

    def test_bare_stem_rejected(self):
        # the 'tp-' loophole must not earn approval via the concat-root clause
        self.assertFalse(vsk.approved("tp-", "local", ENTRIES))

    def test_unknown_key_rejected(self):
        self.assertFalse(vsk.approved("tp-evil-tracker", "local", ENTRIES))

    def test_wrong_store_rejected(self):
        # a session-only key written to localStorage must NOT be approved.
        self.assertTrue(vsk.approved("tp-welcomed:x", "session", ENTRIES))
        self.assertFalse(vsk.approved("tp-welcomed:x", "local", ENTRIES))
        self.assertFalse(vsk.approved("tp-theme", "session", ENTRIES))


class Resolve(unittest.TestCase):
    def test_string_literal(self):
        self.assertEqual(vsk.resolve("'tp-theme'", {}), "tp-theme")

    def test_concatenation_takes_literal_root(self):
        self.assertEqual(vsk.resolve("'tp-last-read:/' + v", {}), "tp-last-read:/")

    def test_module_constant(self):
        self.assertEqual(vsk.resolve("KEY", {"KEY": "tp-last-edition"}), "tp-last-edition")

    def test_dynamic_key_unresolved(self):
        self.assertIsNone(vsk.resolve("someVar", {}))


class ScanText(unittest.TestCase):
    def test_captures_store_and_key(self):
        hits, _ = vsk.scan_text("localStorage.setItem('tp-theme', '1')")
        self.assertEqual(hits, [(1, "tp-theme", "local")])
        hits, _ = vsk.scan_text("sessionStorage.getItem('tp-show-gate')")
        self.assertEqual(hits, [(1, "tp-show-gate", "session")])

    def test_literal_key_with_comma_is_resolved_not_skipped(self):
        # a quoted key containing a comma must be captured whole (not truncated
        # at the comma and dropped as an unresolved dynamic key).
        hits, unresolved = vsk.scan_text("localStorage.setItem('tp-a,b', '1')")
        self.assertEqual(hits, [(1, "tp-a,b", "local")])
        self.assertEqual(unresolved, [])


class LiveTreeGreen(unittest.TestCase):
    def test_current_public_surface_passes(self):
        self.assertEqual(vsk.main(), 0)


if __name__ == "__main__":
    unittest.main()
