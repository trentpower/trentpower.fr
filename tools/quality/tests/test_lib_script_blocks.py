#!/usr/bin/env python3
"""Tests for tools/lib/script_blocks.py — the shared <script> locator.

The load-bearing property is byte-exactness: callers slice the original
text by the reported offsets (csp hashes are computed from those bytes),
so reconstruction from gaps + block slices must reproduce the input.
"""

import unittest

import _fixture  # noqa: E402

_fixture.bootstrap("release")

from script_blocks import iter_script_blocks, strip_script_blocks  # noqa: E402

DOC = (
    "<!doctype html>\n"
    "<html><head>\n"
    '<script nonce="n1">var a = 1 < 2; var s = "</scr" + "ipt>";</script>\n'
    '<SCRIPT TYPE="application/ld+json">{"@context": "https://schema.org"}</SCRIPT>\n'
    '<script src="/app.js?v=abc"></script>\n'
    "<script type='module'>import x from './x.js';</script>\n"
    "</head><body>\n"
    "<p>27 KB of prose &amp; entities</p>\n"
    "</body></html>\n"
)

# DOC with every script element removed — exactly what the regexes this
# module replaced would have produced. pinned as a literal so this test
# file carries no html-filtering regex of its own.
DOC_STRIPPED = (
    "<!doctype html>\n"
    "<html><head>\n"
    "\n\n\n\n"
    "</head><body>\n"
    "<p>27 KB of prose &amp; entities</p>\n"
    "</body></html>\n"
)


class Offsets(unittest.TestCase):
    def test_round_trip_is_byte_exact(self):
        blocks = iter_script_blocks(DOC)
        self.assertEqual(len(blocks), 4)
        out, pos = [], 0
        for blk in blocks:
            out.append(DOC[pos : blk.start])
            out.append(DOC[blk.start : blk.end])
            pos = blk.end
        out.append(DOC[pos:])
        self.assertEqual("".join(out), DOC)

    def test_body_equals_offset_slice(self):
        for blk in iter_script_blocks(DOC):
            self.assertEqual(blk.body, DOC[blk.body_start : blk.body_end])
            self.assertEqual(blk.raw_start_tag, DOC[blk.start : blk.body_start])

    def test_literal_end_tag_in_js_string_terminates(self):
        # parity with the old regexes: "</scr" + "ipt>" does NOT split,
        # but a literal </script inside a string WOULD. pin both.
        blk = iter_script_blocks(DOC)[0]
        self.assertIn('"</scr" + "ipt>"', blk.body)
        doc = "<script>var s = '</script>'; rest</script>"
        blk = iter_script_blocks(doc)[0]
        self.assertEqual(blk.body, "var s = '")

    def test_unterminated_block_ignored(self):
        self.assertEqual(iter_script_blocks("<p>x</p><script>var a = 1;"), [])

    def test_line_numbers(self):
        lines = [blk.line for blk in iter_script_blocks(DOC)]
        self.assertEqual(lines, [3, 4, 5, 6])


class Classification(unittest.TestCase):
    def test_executable_matrix(self):
        blocks = iter_script_blocks(DOC)
        self.assertTrue(blocks[0].is_executable())  # no type
        self.assertFalse(blocks[1].is_executable())  # ld+json data block
        self.assertFalse(blocks[2].is_executable())  # external src
        self.assertTrue(blocks[3].is_executable())  # module

    def test_attrs_parsed(self):
        blocks = iter_script_blocks(DOC)
        self.assertEqual(blocks[0].attrs.get("nonce"), "n1")
        self.assertEqual(blocks[1].type_attr, "application/ld+json")
        self.assertEqual(blocks[2].src, "/app.js?v=abc")
        self.assertEqual(blocks[3].type_attr, "module")

    def test_uppercase_tag_found(self):
        self.assertEqual(iter_script_blocks(DOC)[1].line, 4)


class Strip(unittest.TestCase):
    def test_strip_parity_with_old_regex(self):
        self.assertEqual(strip_script_blocks(DOC), DOC_STRIPPED)

    def test_strip_replacement(self):
        doc = "a<script>x</script>b"
        self.assertEqual(strip_script_blocks(doc, "_"), "a_b")


if __name__ == "__main__":
    unittest.main()
