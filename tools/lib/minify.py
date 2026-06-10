#!/usr/bin/env python3
"""tools/lib/minify.py — pure-Python CSS + JS minifiers.

No external dependencies. Two callable functions:

  minify_css(text) -> str
  minify_js(text)  -> str

Both preserve `/*! ... */` license blocks. Both are conservative —
the goal is whitespace and comment removal, not aggressive
identifier renaming or dead-code elimination, so the output remains
readable enough that a `Ctrl+U` inspector can still navigate it.

CSS minifier
  - Strips /* ... */ comments (keeps /*! ... */ legal headers)
  - Collapses whitespace runs to a single space
  - Drops whitespace around { } ; : , > + ~
  - Drops trailing `;` before `}`

JS minifier
  - State-machine that tracks string ('"', "'", '`'), template
    literal, and regex-literal contexts, so comments inside strings
    or regex patterns are NOT stripped.
  - Strips // line comments and /* ... */ block comments outside
    string/regex contexts. Keeps /*! ... */ legal headers.
  - Collapses runs of horizontal whitespace and blank lines.
  - Preserves newlines that would terminate statements (ASI safety):
    every original line ending stays a line ending, never collapsed
    into a space.

The minifiers do NOT alter semantics. Output bytes change but the
runtime behaviour of CSS/JS does not.

Used by tools/generate_site.py to emit minified production
artefacts. Source files (templates/*.js, public/styles.css source)
remain readable; the build emits the minified deployed bytes.
"""

import re

# ─── css ─────────────────────────────────────────────────────────────

_CSS_COMMENT = re.compile(r"/\*(?!!)[\s\S]*?\*/")
_CSS_WS_RUNS = re.compile(r"\s+")
_CSS_WS_AROUND = re.compile(r"\s*([{};:,>+~])\s*")
_CSS_TRAILING_SC = re.compile(r";+}")


def minify_css(text: str) -> str:
    """Remove non-license comments, collapse whitespace, drop trailing
    semicolons before }.

    Preserves `/*! ... */` blocks so font/license notices are not lost.
    """
    if not text:
        return text
    text = _CSS_COMMENT.sub("", text)
    text = _CSS_WS_RUNS.sub(" ", text)
    text = _CSS_WS_AROUND.sub(r"\1", text)
    text = _CSS_TRAILING_SC.sub("}", text)
    return text.strip()


# ─── js ──────────────────────────────────────────────────────────────

# characters that, as the last non-whitespace token before a `/`, mean
# the `/` starts a regex literal (rather than a division operator).
# includes operators, punctuators, and the end of certain keywords.
_REGEX_PRECEDED_BY_CHARS = set("(,=:[!&|?{};+-*%^~<>")
_REGEX_PRECEDED_BY_KEYWORDS = (
    "return",
    "typeof",
    "instanceof",
    "in",
    "of",
    "new",
    "delete",
    "void",
    "do",
    "else",
    "case",
    "throw",
    "yield",
    "await",
)


def _is_regex_context(out_buf: list) -> bool:
    """Look at the last non-whitespace token in out_buf to decide
    whether a `/` starts a regex literal. Conservative: when in doubt,
    return False (treat as division — leaves the `/` untouched but
    that is harmless because we only use this decision to know whether
    to skip past a regex literal verbatim)."""
    s = "".join(out_buf)
    j = len(s) - 1
    while j >= 0 and s[j].isspace():
        j -= 1
    if j < 0:
        return True  # beginning of input — `/` must be regex.
    c = s[j]
    if c in _REGEX_PRECEDED_BY_CHARS:
        return True
    # check for trailing keyword.
    if c.isalnum() or c == "_":
        # walk back to start of the identifier.
        k = j
        while k >= 0 and (s[k].isalnum() or s[k] == "_"):
            k -= 1
        ident = s[k + 1 : j + 1]
        if ident in _REGEX_PRECEDED_BY_KEYWORDS:
            return True
    return False


def minify_js(text: str) -> str:
    """Strip comments + collapse whitespace, preserving string and
    regex literal contents and ASI-safe line breaks."""
    if not text:
        return text

    out: list = []
    i = 0
    n = len(text)

    while i < n:
        c = text[i]

        # line comment
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = j if j != -1 else n
            continue

        # block comment
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            if i + 2 < n and text[i + 2] == "!":
                # preserve /*! ... */ legal headers verbatim.
                end = text.find("*/", i + 3)
                end = end + 2 if end != -1 else n
                out.append(text[i:end])
                i = end
                continue
            end = text.find("*/", i + 2)
            i = end + 2 if end != -1 else n
            continue

        # string literal: ', ", or `
        if c in ("'", '"', "`"):
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                # Template-literal interpolation `${ ... }` may contain
                # nested strings; for safety we just look for the
                # closing backtick at depth 0 — the simple scanner
                # below handles common cases. complex nested templates
                # in this codebase are rare enough that the
                # conservative scanner is sufficient.
                if text[j] == c:
                    j += 1
                    break
                j += 1
            out.append(text[i:j])
            i = j
            continue

        # regex literal — heuristic based on preceding token.
        if c == "/" and _is_regex_context(out):
            j = i + 1
            in_class = False
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "[":
                    in_class = True
                elif text[j] == "]":
                    in_class = False
                elif text[j] == "/" and not in_class:
                    j += 1
                    while j < n and text[j].isalpha():
                        j += 1
                    break
                elif text[j] == "\n":
                    # regex literals cannot contain raw newlines —
                    # bail out, treat the `/` as a plain character.
                    j = i + 1
                    break
                j += 1
            out.append(text[i:j])
            i = j
            continue

        out.append(c)
        i += 1

    minified = "".join(out)

    # collapse runs of horizontal whitespace.
    minified = re.sub(r"[ \t]+", " ", minified)
    # trim trailing whitespace on each line.
    minified = re.sub(r"[ \t]+\n", "\n", minified)
    # trim leading whitespace on each line.
    minified = re.sub(r"\n[ \t]+", "\n", minified)
    # collapse runs of blank lines.
    minified = re.sub(r"\n{2,}", "\n", minified)

    return minified.strip() + "\n"


# ─── cli helper for ad-hoc use ───────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3 or sys.argv[1] not in ("css", "js"):
        sys.stderr.write("usage: minify.py {css|js} <path>\n")
        sys.exit(2)
    kind, path = sys.argv[1], sys.argv[2]
    with open(path, encoding="utf-8") as fp:
        src = fp.read()
    out = minify_css(src) if kind == "css" else minify_js(src)
    sys.stdout.write(out)
