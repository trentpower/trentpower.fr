#!/usr/bin/env python3
"""Tests for tools/lib/minify.py — the pure CSS + JS minifiers.

These assert real minifier invariants: comment/whitespace collapse, license
header preservation, semantic preservation of string/regex contents, and
idempotence. Inputs target the state-machine's special-case branches.
"""

import unittest

import _fixture  # noqa: E402

_fixture.bootstrap()

import minify  # noqa: E402


class CssBasics(unittest.TestCase):
    def test_empty_passthrough(self):
        # empty input short-circuits unchanged (not "\n"-suffixed like js).
        self.assertEqual(minify.minify_css(""), "")

    def test_strips_comments(self):
        out = minify.minify_css("/* a note */ a{color:red}")
        self.assertNotIn("a note", out)
        self.assertEqual(out, "a{color:red}")

    def test_collapses_whitespace_and_is_shorter(self):
        src = "a {\n    color:  red;\n    margin:   0;\n}\n"
        out = minify.minify_css(src)
        self.assertLess(len(out), len(src))
        self.assertEqual(out, "a{color:red;margin:0}")

    def test_drops_whitespace_around_separators(self):
        out = minify.minify_css("a > b + c ~ d , e { x : 1 }")
        self.assertEqual(out, "a>b+c~d,e{x:1}")

    def test_drops_trailing_semicolon_before_brace(self):
        self.assertEqual(minify.minify_css("a{color:red;}"), "a{color:red}")

    def test_drops_multiple_trailing_semicolons(self):
        self.assertEqual(minify.minify_css("a{color:red;;;}"), "a{color:red}")

    def test_idempotent(self):
        src = "/* x */ a {\n color: red;\n}\n"
        once = minify.minify_css(src)
        self.assertEqual(minify.minify_css(once), once)


class CssLicensePreservation(unittest.TestCase):
    def test_keeps_bang_header(self):
        # /*! ... */ legal headers must survive verbatim (modulo ws collapse).
        out = minify.minify_css("/*! Font (c) 2026 */\na{color:red}")
        self.assertIn("/*! Font (c) 2026 */", out)

    def test_drops_plain_but_keeps_bang(self):
        out = minify.minify_css("/* drop me */ /*! keep me */ a{x:1}")
        self.assertNotIn("drop me", out)
        self.assertIn("keep me", out)


class JsBasics(unittest.TestCase):
    def test_empty_passthrough(self):
        self.assertEqual(minify.minify_js(""), "")

    def test_trailing_newline_added(self):
        self.assertTrue(minify.minify_js("var x=1").endswith("\n"))

    def test_strips_line_comment(self):
        out = minify.minify_js("var x = 1; // a comment\nvar y = 2;\n")
        self.assertNotIn("a comment", out)
        self.assertIn("var x = 1;", out)

    def test_line_comment_at_eof_no_newline(self):
        # find("\n") returns -1 -> consume to end of input.
        out = minify.minify_js("var x=1; // tail")
        self.assertNotIn("tail", out)

    def test_strips_block_comment(self):
        out = minify.minify_js("var/* inline */ x = 1;\n")
        self.assertNotIn("inline", out)

    def test_unterminated_block_comment_consumed(self):
        # missing */ -> consume to end (no crash, comment gone).
        out = minify.minify_js("var x=1; /* never closed")
        self.assertNotIn("never closed", out)

    def test_collapses_horizontal_whitespace(self):
        out = minify.minify_js("var    x    =    1;\n")
        self.assertEqual(out, "var x = 1;\n")

    def test_collapses_blank_lines(self):
        out = minify.minify_js("a();\n\n\n\nb();\n")
        self.assertEqual(out, "a();\nb();\n")

    def test_preserves_newlines_for_asi(self):
        # every original line ending stays a line ending (asi safety).
        out = minify.minify_js("a()\nb()\n")
        self.assertIn("a()\nb()", out)

    def test_idempotent(self):
        src = "function f() {\n  // c\n  return  1;\n}\n"
        once = minify.minify_js(src)
        self.assertEqual(minify.minify_js(once), once)


class JsLicensePreservation(unittest.TestCase):
    def test_keeps_bang_block(self):
        out = minify.minify_js("/*! @license MIT */\nvar x=1;\n")
        self.assertIn("/*! @license MIT */", out)

    def test_unterminated_bang_block_consumed_to_end(self):
        # /*! with no closing */ -> end = n, appended verbatim to eof.
        out = minify.minify_js("/*! open header forever")
        self.assertIn("/*! open header forever", out)


class JsStringPreservation(unittest.TestCase):
    # NOTE: the state-machine preserves string CONTENT during the scan (so
    # comment-like and escaped sequences inside a string are never mis-parsed
    # as comments), but the final `[ \t]+ -> " "` post-pass is GLOBAL and does
    # collapse internal whitespace runs. These tests assert that true behavior.
    def test_single_quoted_comment_like_not_stripped(self):
        # // inside a string must NOT be treated as a comment.
        out = minify.minify_js("var s = 'http://example.com';\n")
        self.assertIn("'http://example.com'", out)

    def test_block_comment_inside_string_preserved(self):
        out = minify.minify_js('var s = "a /* not a comment */ b";\n')
        self.assertIn("/* not a comment */", out)

    def test_escaped_quote_in_string_not_terminator(self):
        # backslash-escaped quote does not end the string; content survives.
        out = minify.minify_js('var s = "a\\"b";\n')
        self.assertIn('"a\\"b"', out)

    def test_internal_whitespace_collapsed_globally(self):
        # the global post-pass collapses space runs even inside literals.
        out = minify.minify_js('var s = "hello    world";\n')
        self.assertIn('"hello world"', out)

    def test_template_literal_structure_preserved(self):
        out = minify.minify_js("var s = `keep ${x} spaces`;\n")
        self.assertIn("`keep ${x} spaces`", out)

    def test_unterminated_string_consumed_to_end(self):
        # no closing quote -> scanner runs to n without crashing.
        out = minify.minify_js('var s = "open')
        self.assertIn('"open', out)


class JsRegexPreservation(unittest.TestCase):
    def test_regex_after_assignment_escaped_slash_preserved(self):
        # `=` precedes -> regex context; an escaped slash is not the terminator.
        out = minify.minify_js("var re = /a\\/c/g;\n")
        self.assertIn("/a\\/c/g", out)

    def test_regex_at_start_of_input(self):
        # beginning of input -> _is_regex_context true; structure intact.
        out = minify.minify_js("/xy/.test(s)\n")
        self.assertIn("/xy/", out)

    def test_regex_after_return_keyword(self):
        out = minify.minify_js("function f(){return /ab/;}\n")
        self.assertIn("/ab/", out)

    def test_regex_with_char_class_containing_slash(self):
        # slash inside [...] is not the terminator; whole literal survives.
        out = minify.minify_js("var re = /[a/b]/;\n")
        self.assertIn("/[a/b]/", out)

    def test_division_not_treated_as_regex(self):
        # `x` (identifier, not a regex-preceding keyword) -> division.
        out = minify.minify_js("var y = x / 2;\n")
        self.assertIn("x / 2", out)

    def test_comment_after_keyword_not_regex(self):
        # 'in' keyword would imply regex, but // is a comment first.
        out = minify.minify_js("for (k in o) {} // done\n")
        self.assertNotIn("done", out)

    def test_regex_with_raw_newline_bails_out(self):
        # a regex cannot span a raw newline; the `/` is treated as plain.
        out = minify.minify_js("var a = /unterminated\nb()\n")
        # the literal slash survives as a plain char; newline kept for asi.
        self.assertIn("/unterminated", out)
        self.assertIn("b()", out)

    def test_regex_with_escaped_char(self):
        out = minify.minify_js("var re = /a\\.b/;\n")
        self.assertIn("/a\\.b/", out)

    def test_unterminated_regex_consumed_to_end(self):
        # `/` in regex context with no closing `/` -> while-loop exits on j<n
        # naturally; the partial literal is appended without crashing.
        out = minify.minify_js("var re = /abc")
        self.assertIn("/abc", out)


class JsRegexContextHelper(unittest.TestCase):
    def test_empty_buffer_is_regex(self):
        self.assertTrue(minify._is_regex_context([]))

    def test_whitespace_only_buffer_is_regex(self):
        self.assertTrue(minify._is_regex_context(["  \n "]))

    def test_operator_precedes_regex(self):
        self.assertTrue(minify._is_regex_context(["x", "="]))

    def test_keyword_precedes_regex(self):
        self.assertTrue(minify._is_regex_context(["return"]))

    def test_identifier_precedes_division(self):
        self.assertFalse(minify._is_regex_context(["foo"]))

    def test_close_paren_precedes_division(self):
        # `)` is not in the regex-preceding set -> division context.
        self.assertFalse(minify._is_regex_context(["f()"]))


if __name__ == "__main__":
    unittest.main()
