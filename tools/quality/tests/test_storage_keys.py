#!/usr/bin/env python3
"""Tests for the browser-storage-key allowlist gate
(tools/quality/validate_storage_keys.py)."""

import contextlib
import io
import pathlib
import tempfile
import unittest

import _fixture  # noqa: E402

_fixture.bootstrap("release")

import validate_storage_keys as vsk  # noqa: E402
from _fixture import write as _write  # noqa: E402

# the canonical local.js allowlist source, mirroring the LOCAL_KEYS contract the
# /local/ page renders. fixtures that need a valid allowlist write this.
_LOCAL_JS = (
    "var LOCAL_KEYS = [\n"
    "  { key: 'tp-theme', storage: 'local', prefix: false },\n"
    "  { key: 'tp-welcomed:', storage: 'session', prefix: true },\n"
    "];\n"
)

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

    def test_incomplete_entry_is_dropped(self):
        # an in-array object missing a required field (no prefix:) is skipped,
        # so only the fully-specified entry survives.
        src = (
            "var LOCAL_KEYS = [\n"
            "{ key: 'tp-theme', storage: 'local' },\n"
            "{ key: 'tp-last-edition', storage: 'local', prefix: false }\n"
            "];\n"
        )
        self.assertEqual(
            vsk.parse_allowlist(src), [("tp-last-edition", False, "local")]
        )


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


class MainOverFixture(unittest.TestCase):
    """main() reads the module-level PUBLIC / ALLOWLIST_SRC paths, so we point
    them at a built fixture tree and restore them after each test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.public = self.root / "public"
        self.public.mkdir(parents=True, exist_ok=True)
        self._saved_public = vsk.PUBLIC
        self._saved_allow = vsk.ALLOWLIST_SRC
        vsk.PUBLIC = self.public
        vsk.ALLOWLIST_SRC = self.public / "js" / "local.js"

    def tearDown(self):
        vsk.PUBLIC = self._saved_public
        vsk.ALLOWLIST_SRC = self._saved_allow
        self._tmp.cleanup()

    def _run_main(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vsk.main()
        return rc, buf.getvalue()

    def test_missing_allowlist_source_fails(self):
        # no public/js/local.js on disk at all.
        rc, out = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("allowlist source missing", out)

    def test_empty_allowlist_fails(self):
        # local.js exists but its LOCAL_KEYS array parses to no entries.
        _write(self.root, "public/js/local.js", "var LOCAL_KEYS = [];\n")
        rc, out = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("parsed empty", out)

    def test_undocumented_key_in_js_fails(self):
        # a real undocumented localStorage write in a shipped .js file. the
        # frozen release tree carries a retired key the gate must skip, proving
        # the SKIP_PREFIXES branch fires without producing a failure.
        _write(self.root, "public/js/local.js", _LOCAL_JS)
        _write(self.root, "public/js/app.js", "localStorage.setItem('tp-tracker', '1');\n")
        _write(
            self.root,
            "public/integrity/releases/2026-01-01/old.js",
            "localStorage.setItem('tp-lang', 'en');\n",
        )
        rc, out = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("undocumented key", out)
        self.assertIn("tp-tracker", out)
        # the frozen-tree retired key must NOT surface as a failure.
        self.assertNotIn("tp-lang", out)

    def test_undocumented_key_in_inline_html_script_fails(self):
        # an undocumented sessionStorage write inside an inline <script> block.
        _write(self.root, "public/js/local.js", _LOCAL_JS)
        _write(
            self.root,
            "public/page.html",
            "<html><head></head><body>\n"
            "<script>sessionStorage.setItem('tp-spy', 'x');</script>\n"
            "</body></html>\n",
        )
        rc, out = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("undocumented key", out)
        self.assertIn("tp-spy", out)

    def test_clean_surface_passes(self):
        # every write is on the allowlist for its declared store.
        _write(self.root, "public/js/local.js", _LOCAL_JS)
        _write(self.root, "public/js/app.js", "localStorage.setItem('tp-theme', 'dark');\n")
        rc, out = self._run_main()
        self.assertEqual(rc, 0)
        self.assertIn("OK: storage-keys", out)

    def test_many_failures_truncate_summary(self):
        # >30 undocumented keys exercises the truncated-overflow render line.
        _write(self.root, "public/js/local.js", _LOCAL_JS)
        body = "".join(f"localStorage.setItem('tp-bad{i}', '1');\n" for i in range(35))
        _write(self.root, "public/js/app.js", body)
        rc, out = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("more", out)


if __name__ == "__main__":
    unittest.main()
