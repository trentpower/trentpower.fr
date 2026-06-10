#!/usr/bin/env python3
"""Tests for the {{ }} token engine in tools/build/render_pages.py."""

import pathlib
import sys
import unittest

_TOOLS = pathlib.Path(__file__).resolve().parents[2]
for _sub in ("lib", "build", "quality", "verify", "release"):
    sys.path.insert(0, str(_TOOLS / _sub))

from render_pages import RenderError, substitute  # noqa: E402


class TextTokens(unittest.TestCase):
    def test_plain_substitution(self):
        self.assertEqual(substitute("<p>{{ a.b }}</p>", {"a": {"b": "hello"}}), "<p>hello</p>")

    def test_text_is_escaped(self):
        out = substitute("<p>{{ v }}</p>", {"v": 'a < b & "c"'})
        self.assertEqual(out, '<p>a &lt; b &amp; "c"</p>')

    def test_unresolved_token_raises(self):
        with self.assertRaises(RenderError):
            substitute("{{ missing.key }}", {})

    def test_non_string_value_raises(self):
        with self.assertRaises(RenderError):
            substitute("{{ n }}", {"n": 42})


class KindPrefixes(unittest.TestCase):
    def test_html_inserted_raw(self):
        out = substitute("{{ html:v }}", {"v": "<em>raw</em>"})
        self.assertEqual(out, "<em>raw</em>")

    def test_attr_escapes_quotes(self):
        out = substitute('<a title="{{ attr:v }}">', {"v": 'say "hi" <now>'})
        self.assertEqual(out, '<a title="say &quot;hi&quot; &lt;now&gt;">')

    def test_url_percent_encodes(self):
        out = substitute("{{ url:v }}", {"v": "a b—c"})
        self.assertEqual(out, "a%20b%E2%80%94c")

    def test_list_from_list(self):
        out = substitute("<ul>{{ list:v }}</ul>", {"v": ["one", "two"]})
        self.assertEqual(out, "<ul><li>one</li><li>two</li></ul>")

    def test_list_from_newline_string(self):
        out = substitute("<ul>{{ list:v }}</ul>", {"v": "one\n\ntwo\n"})
        self.assertEqual(out, "<ul><li>one</li><li>two</li></ul>")

    def test_list_from_scalar_raises(self):
        with self.assertRaises(RenderError):
            substitute("{{ list:v }}", {"v": 42})


class FixedPoint(unittest.TestCase):
    def test_nested_shared_reference_expands(self):
        ctx = {"shared": {"name": "Trent"}, "v": "hello {{ shared.name }}"}
        self.assertEqual(substitute("<p>{{ html:v }}</p>", ctx), "<p>hello Trent</p>")

    def test_cyclic_reference_raises(self):
        ctx = {"a": "{{ html:b }}", "b": "{{ html:a }}"}
        with self.assertRaises(RenderError):
            substitute("{{ html:a }}", ctx)


class MultilineIndent(unittest.TestCase):
    def test_continuation_lines_inherit_token_indent(self):
        out = substitute("  <p>{{ v }}</p>", {"v": "line one\nline two"})
        self.assertEqual(out, "  <p>line one\n  line two</p>")


if __name__ == "__main__":
    unittest.main()
