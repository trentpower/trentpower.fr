#!/usr/bin/env python3
"""fix_lowercase_comments.py — apply the lowercase-comments authorial rule.

walks a curated list of authored sources and lowercases comment
prose in place. preserves tokens that look like paths, urls,
identifiers, css variables, hex hashes, or python warning words.

scope (file types):
  html — only top-level <!-- ... --> comments; inline <script>
         blocks (without src=) are skipped to preserve csp hashes.
  css  — /* ... */ comments inside tools/*.src.css.
  js   — // and /* ... */ comments inside templates/*.template.js.
  py   — # line comments inside tools/*.py. docstrings (triple-
         quoted strings) are NOT processed — they are code-adjacent
         and best authored as written.
  htaccess — # line comments in public/.htaccess.
  txt  — entire file contents in selected short .txt files (each
         file treated as one long prose region).

excluded:
  public/changelog.txt          (grandfathered phases 1-18)
  public/pgp.txt                (pgp protocol data)
  public/robots.txt             (robot directives)
  public/.well-known/security.txt   (rfc 9116 protocol)
  public/sitemap.xml.sha256     (hash)
  public/integrity/releases/<edition>/*   (frozen archives)
  public/source/*               (generated mirrors)
  public/{app.js,verify-modal.js,i18n*.js,styles.css,print.css,*.html} post-build copies
  inline <script>...</script> bodies in html (csp-hashed)
  tools/build/copy/strings.json, public/*.json (data, no comments)
  this script and validate_lowercase_comments.py (self-reference)

usage:
  python3 tools/fix_lowercase_comments.py            # apply in place
  python3 tools/fix_lowercase_comments.py --dry-run  # report counts only
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

# files to process. authored sources only. order doesn't matter; each
# entry maps a path glob to a file-kind handler.
TARGETS = [
    # html (authored, not generated mirrors / not frozen archives)
    (
        "html",
        [
            "public/index.html",
            "public/privacy/index.html",
            "public/integrity/index.html",
            "public/integrity/releases/index.html",
            "public/security/index.html",
            "public/security/acknowledgments/index.html",
            "public/verify/index.html",
            "public/sw-reset/index.html",
            "public/source/index.html",
            "public/maintenance.html",
            "public/403.html",
            "public/404.html",
            "public/500.html",
        ],
    ),
    # css source
    (
        "css",
        [
            "styles/styles.src.css",
            "styles/print.src.css",
            "styles/fonts-full.src.css",
        ],
    ),
    # js templates
    (
        "js",
        [
            "templates/app.template.js",
            "templates/app-enhance.template.js",
            "templates/verify-modal.template.js",
        ],
    ),
    # python tools (with warning-word preservation)
    (
        "py",
        sorted(
            str(p.relative_to(ROOT))
            # the authored python tools — one level under each responsibility
            # pillar (build/ quality/ verify/ release/ lib/). score-ledger/ and
            # _retired/ keep their own conventions and stay out of scope.
            for p in (ROOT / "tools").glob("*/*.py")
            if p.parts[-2] in {"build", "quality", "verify", "release", "lib"}
            and p.name not in {"fix_lowercase_comments.py", "validate_lowercase_comments.py"}
        ),
    ),
    # apache
    ("htaccess", ["public/.htaccess"]),
    # short txt files (changelog/pgp/robots/security/sitemap excluded).
    # assertion.txt + statement.txt are PGP clear-signed and must keep
    # their uppercase armor headers — they are case-curated by hand and
    # not auto-lowercased.
    (
        "txt",
        [
            "public/humans.txt",
            "public/llms.txt",
            "public/ai-usage.txt",
            "public/.well-known/attribution.txt",
        ],
    ),
]

# tokens preserved as-written even inside a comment. anything matching
# one of these patterns keeps its case.
_HAS_PATHISH = re.compile(r"[/\\@:_]|[\w][.][\w]|[\w][-][\w]")
_PURE_HEX = re.compile(r"^[0-9a-f]{8,}$")
_CSS_VAR = re.compile(r"^--")
# camelCase identifier: a lowercase letter immediately followed by an
# uppercase letter inside the same token. catches function names like
# `renderLanguage`, `loadOptionalLang`, `updateLangControls`,
# `requestAnimationFrame` — code references in prose that must keep
# their case to remain valid identifiers when grepped.
_CAMEL_CASE = re.compile(r"[a-z][A-Z]")
# all-uppercase identifier of 2+ chars (with optional trailing
# punctuation): SHA256SUMS, BASENAME, URL, YAML, README. these read
# as identifiers / acronyms in prose; lowercasing them removes
# semantic content. matches the same rule the archive-casing
# validator uses (validate_archive_text_casing.py).
_ALL_UPPER_IDENT = re.compile(r"^[A-Z][A-Z0-9_]{1,}s?[.,;:!?)]?$")
PYTHON_WARNING_WORDS = {
    "IMPORTANT",
    "NOTE",
    "TODO",
    "WARNING",
    "FIXME",
    "XXX",
    "HACK",
}


def _is_preserve_token(tok: str, *, python: bool = False) -> bool:
    if not tok:
        return True
    if python and tok in PYTHON_WARNING_WORDS:
        return True
    if _CSS_VAR.match(tok):
        return True
    if _PURE_HEX.match(tok):
        return True
    if _HAS_PATHISH.search(tok):
        return True
    if _CAMEL_CASE.search(tok):
        return True
    if _ALL_UPPER_IDENT.match(tok):
        return True
    return False


def _has_upper(s: str) -> bool:
    return any("A" <= c <= "Z" for c in s)


def _lower_prose(s: str, *, python: bool = False) -> str:
    """lowercase prose tokens in `s`, preserving whitespace and
    preserve-eligible tokens. operates on whitespace-separated tokens
    so attached punctuation stays with the token (e.g. `Worker.` →
    `worker.` because `.` at end isn't a middle-dot trigger)."""
    parts = re.split(r"(\s+)", s)
    out = []
    for part in parts:
        if part.isspace() or not part:
            out.append(part)
            continue
        if _is_preserve_token(part, python=python):
            out.append(part)
            continue
        if _has_upper(part):
            out.append(part.lower())
        else:
            out.append(part)
    return "".join(out)


# ---------- per-file-kind handlers ----------

# html: <!-- ... --> comments. inline <script> blocks (no src= attribute)
# are sliced out and reassembled untouched so csp hashes don't drift.
_HTML_COMMENT_RE = re.compile(r"<!--([\s\S]*?)-->")
_HTML_SCRIPT_RE = re.compile(r"<script\b([^>]*)>([\s\S]*?)</script>", re.IGNORECASE)


def _process_html(text: str) -> tuple[str, int]:
    # carve out inline <script>...</script> bodies (those without src=)
    # so their contents are not touched. external <script src=...></script>
    # has empty body anyway.
    chunks: list[tuple[bool, str]] = []  # (process?, text)
    pos = 0
    for m in _HTML_SCRIPT_RE.finditer(text):
        attrs = m.group(1)
        if " src=" in attrs or " src ='" in attrs or 'src="' in attrs:
            # external script — body is empty, treat as normal content
            chunks.append((True, text[pos : m.end()]))
        else:
            # inline script — body must stay byte-stable (csp hashes)
            if m.start() > pos:
                chunks.append((True, text[pos : m.start()]))
            chunks.append((False, text[m.start() : m.end()]))
        pos = m.end()
    if pos < len(text):
        chunks.append((True, text[pos:]))

    changed = 0
    rebuilt = []
    for do_process, chunk in chunks:
        if not do_process:
            rebuilt.append(chunk)
            continue

        def repl(match: re.Match) -> str:
            nonlocal changed
            inner = match.group(1)
            new = _lower_prose(inner, python=False)
            if new != inner:
                changed += 1
            return f"<!--{new}-->"

        rebuilt.append(_HTML_COMMENT_RE.sub(repl, chunk))
    return "".join(rebuilt), changed


# css: /* ... */ multi-line.
_CSS_COMMENT_RE = re.compile(r"/\*([\s\S]*?)\*/")


def _process_css(text: str) -> tuple[str, int]:
    changed = 0

    def repl(match: re.Match) -> str:
        nonlocal changed
        inner = match.group(1)
        new = _lower_prose(inner, python=False)
        if new != inner:
            changed += 1
        return f"/*{new}*/"

    return _CSS_COMMENT_RE.sub(repl, text), changed


# js: both // (rest of line) and /* ... */ block comments. strings are
# not processed because the comment regex doesn't match inside them
# (we accept the false-positive risk where a string contains literal
# `/*` — none of the codebase's templates do).
_JS_BLOCK_RE = re.compile(r"/\*([\s\S]*?)\*/")
_JS_LINE_RE = re.compile(r"(//)([^\n]*)")


def _process_js(text: str) -> tuple[str, int]:
    changed = 0

    def block_repl(match: re.Match) -> str:
        nonlocal changed
        inner = match.group(1)
        new = _lower_prose(inner, python=False)
        if new != inner:
            changed += 1
        return f"/*{new}*/"

    text = _JS_BLOCK_RE.sub(block_repl, text)

    def line_repl(match: re.Match) -> str:
        nonlocal changed
        inner = match.group(2)
        new = _lower_prose(inner, python=False)
        if new != inner:
            changed += 1
        return f"{match.group(1)}{new}"

    text = _JS_LINE_RE.sub(line_repl, text)
    return text, changed


# python: # rest-of-line comments only. docstrings are NOT processed.
# warning-word preservation is active.
_PY_LINE_RE = re.compile(r"(^|\s)(#)([^\n]*)")


def _process_py(text: str) -> tuple[str, int]:
    changed = 0
    out_lines = []
    in_triple_single = False
    in_triple_double = False
    for line in text.splitlines(keepends=True):
        # track triple-quoted strings so we don't touch their content
        i = 0
        while i < len(line):
            triple_d = line.find('"""', i)
            triple_s = line.find("'''", i)
            cand = min((p for p in (triple_d, triple_s) if p != -1), default=-1)
            if cand == -1:
                break
            if cand == triple_d:
                in_triple_double = not in_triple_double
                i = cand + 3
            else:
                in_triple_single = not in_triple_single
                i = cand + 3
        if in_triple_single or in_triple_double:
            out_lines.append(line)
            continue
        # find `#` not inside a string. simple heuristic: walk the line
        # tracking single/double quote state.
        in_s = False
        in_d = False
        hash_pos = -1
        j = 0
        while j < len(line):
            ch = line[j]
            if ch == "\\" and j + 1 < len(line):
                j += 2
                continue
            if ch == "'" and not in_d:
                in_s = not in_s
            elif ch == '"' and not in_s:
                in_d = not in_d
            elif ch == "#" and not in_s and not in_d:
                hash_pos = j
                break
            j += 1
        if hash_pos == -1:
            out_lines.append(line)
            continue
        before = line[:hash_pos]
        comment = line[hash_pos:]  # includes the '#'
        # strip trailing newline for processing, re-attach after
        if comment.endswith("\n"):
            body = comment[1:-1]
            inner_new = _lower_prose(body, python=True)
            new_line = before + "#" + inner_new + "\n"
        else:
            body = comment[1:]
            inner_new = _lower_prose(body, python=True)
            new_line = before + "#" + inner_new
        if new_line != line:
            changed += 1
        out_lines.append(new_line)
    return "".join(out_lines), changed


# apache: # rest-of-line.
_HTACCESS_LINE_RE = re.compile(r"^(\s*)(#)([^\n]*)$", re.MULTILINE)


def _process_htaccess(text: str) -> tuple[str, int]:
    changed = 0

    def repl(match: re.Match) -> str:
        nonlocal changed
        inner = match.group(3)
        new = _lower_prose(inner, python=False)
        if new != inner:
            changed += 1
        return f"{match.group(1)}#{new}"

    return _HTACCESS_LINE_RE.sub(repl, text), changed


# txt: line-by-line prose. preserve rules protect paths / urls /
# identifiers / hex hashes per token, and Title-Case label lines
# (e.g. `Canonical URL:`, `Preferred Attribution:`, `Site:`) plus
# bare Title-Case section headers (`Records`, `Integrity`) — the
# casing matrix in docs/public-artefact-conventions.md authorises
# these as machine-facing labels.
_TXT_LABEL_LINE = re.compile(
    r"^\s*([A-Z][A-Za-z0-9-]*(?:\s+(?:[A-Za-z][A-Za-z0-9-]*|\([a-z]{2}\))){0,3}):(\s|$)"
)
_TXT_SECTION_HEADER = re.compile(r"^\s*([A-Z][A-Za-z0-9]*)(\s+[A-Z][A-Za-z0-9]*)*\s*$")


def _process_txt(text: str) -> tuple[str, int]:
    out_lines = []
    changed = 0
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        eol = line[len(body) :]
        if _TXT_LABEL_LINE.match(body) or _TXT_SECTION_HEADER.match(body):
            out_lines.append(line)
            continue
        new_body = _lower_prose(body, python=False)
        if new_body != body:
            changed = 1
        out_lines.append(new_body + eol)
    new = "".join(out_lines)
    return new, changed


HANDLERS = {
    "html": _process_html,
    "css": _process_css,
    "js": _process_js,
    "py": _process_py,
    "htaccess": _process_htaccess,
    "txt": _process_txt,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="report counts only; don't write files"
    )
    args = parser.parse_args()

    total_files = 0
    total_changes = 0
    total_touched = 0

    for kind, paths in TARGETS:
        handler = HANDLERS[kind]
        for rel in paths:
            p = ROOT / rel
            if not p.is_file():
                continue
            total_files += 1
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                print(f"  skip (non-utf8): {rel}", file=sys.stderr)
                continue
            new, changed = handler(text)
            if changed > 0 and new != text:
                total_changes += changed
                total_touched += 1
                if args.dry_run:
                    print(f"  would change ({changed:>4}): {rel}")
                else:
                    p.write_text(new, encoding="utf-8")
                    print(f"  changed     ({changed:>4}): {rel}")

    verb = "would touch" if args.dry_run else "touched"
    print()
    print(
        f"summary: {verb} {total_touched}/{total_files} files, "
        f"{total_changes} comment region(s) lowercased"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
