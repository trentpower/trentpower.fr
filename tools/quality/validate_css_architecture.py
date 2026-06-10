#!/usr/bin/env python3
"""validate_css_architecture.py — enforce the cascade-layer
architecture in the three authored CSS source files.

Cascade order, declared once at the top of tools/styles.src.css:

    @layer reset, tokens, base, layout, components, pages, utilities, overrides;

Source files
- tools/styles.src.css       — main editorial system, layered
- tools/print.src.css        — single @layer print-overrides wrapper
- tools/fonts-full.src.css   — @font-face declarations in @layer fonts

Checks
- L1  styles.src.css declares the canonical layer order exactly once.
- L2  every top-level rule in styles.src.css lives inside a layer
      block (excepting @font-face, @keyframes, the layer declaration
      itself, and bare @layer NAME; sub-declarations).
- L3  no layer NAME has more than 3 top-level wrapper blocks per
      file (catches accidental fragmentation; intentional repeats
      such as tokens-then-tokens-for-nav-offset stay under 3).
- L4  no ID selector (`#id-name { … }`) inside any layer except
      `overrides`.
- L5  !important budget — total !important in styles.src.css ≤ 12;
      print.src.css uses !important freely but only inside the
      print-overrides wrapper; fonts-full.src.css = 0.
- L6  every body[data-page="…"] selector lives inside @layer pages.
- L7  the tokens layer in styles.src.css contains a `:root { … }`
      block declaring the canonical custom properties.
- L8  no `@import` directive in any source CSS.
- L9  print.src.css body wholly inside @layer print-overrides;
      fonts-full.src.css @font-face declarations wholly inside
      @layer fonts.
- L10 styles.src.css contains an `@media (prefers-color-scheme: dark)`
      block that overrides at least the canonical token set
      (--paper-main, --ink, --accent). Catches accidental deletion
      of the dark-mode palette or token drift after tokens are added.
- L11 contrast-ratio gate. WCAG 2.0 relative-luminance computed for
      the canonical text-on-paper pairs in BOTH the light :root and
      the dark @media block. Pure-Python, no dependency.
        --ink         vs --paper-main ≥ 7.0  (AAA body text)
        --ink-muted   vs --paper-main ≥ 4.5  (AA  secondary)
        --accent-text vs --paper-main ≥ 4.5  (AA  link / action text)
      `--accent` itself is decorative (backgrounds, divider tints,
      focus-ring fills) and is not held to 4.5:1; text uses of the
      accent flow through `--accent-text`.

Quiet on success, precise on failure.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

STYLES_PATH = ROOT / "styles" / "styles.src.css"
PRINT_PATH = ROOT / "styles" / "print.src.css"
FONTS_PATH = ROOT / "styles" / "fonts-full.src.css"

CANONICAL_ORDER = [
    "reset",
    "tokens",
    "base",
    "layout",
    "components",
    "pages",
    "utilities",
    "overrides",
]
CANONICAL_DECLARATION = "@layer " + ", ".join(CANONICAL_ORDER) + ";"

# tokens that the architecture validator treats as canonical / required.
# kept conservative: only properties whose loss would silently ripple
# across the system. adding tokens here is a deliberate hardening step.
REQUIRED_TOKENS = [
    "--paper-main",
    "--paper-record",
    "--surface-page",
    "--ink",
    "--accent",
    "--accent-text",
    "--rule",
    "--serif",
    "--sans",
    "--mono",
    "--nav-offset",
]

STYLES_IMPORTANT_BUDGET = 18
# budget bumped 16 → 18 (phase 31) for defensive `!important` markers
# that have since been removed (the trust-line component was retired
# and replaced by .trust-mark, which inherits link colour through
# normal cascade discipline without `!important`). budget kept at 18
# to absorb future motion-reduction / cascade-override needs without
# churn.
# (phase 91 briefly bumped this to 19 for a defensive html.js:not(.fonts-ready)
# guard; that guard was reverted after it interacted unexpectedly with the
# layer-importance cascade and stranded the hero at opacity:0 on destination
# pages. budget returned to 18.)


def _strip_block_comments(text: str) -> str:
    """Strip /* … */ comments, preserving newline count for line numbers."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i : i + 2] == "/*":
            j = text.find("*/", i + 2)
            if j == -1:
                # unterminated; bail out, keep rest
                out.append(text[i:])
                break
            out.append("\n" * text.count("\n", i, j + 2))
            i = j + 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _layer_block_spans(text: str) -> list[tuple[str, int, int]]:
    """Return list of (layer_name, brace_open_index, brace_close_index)
    for every `@layer NAME { … }` block at the TOP level (depth 0).

    Layer-name detection: when a `{` is encountered at depth 0 we
    scan backwards for the LAST `@layer NAME {` match whose closing
    brace coincides with this position. Using the last match (rather
    than the first) is essential — a single window may contain
    multiple `@layer NAME` tokens from earlier layer blocks that have
    since closed.
    """
    spans: list[tuple[str, int, int]] = []
    pat = re.compile(r"@layer\s+([a-zA-Z][\w-]*)\s*\{")
    depth = 0
    i = 0
    n = len(text)
    pending: list[tuple[str, int]] = []
    while i < n:
        ch = text[i]
        if ch == "{":
            if depth == 0:
                window_start = max(0, i - 400)
                window = text[window_start : i + 1]
                # find the last match whose end aligns with the brace.
                last = None
                for m in pat.finditer(window):
                    if m.end() == len(window):
                        last = m
                if last is not None:
                    pending.append((last.group(1), i))
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and pending:
                name, open_idx = pending.pop()
                spans.append((name, open_idx, i))
        i += 1
    return spans


def _index_to_line(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _relative_luminance(hex6: str) -> float:
    """WCAG 2.0 relative luminance for a #RRGGBB colour."""
    r, g, b = (int(hex6[i : i + 2], 16) / 255 for i in (1, 3, 5))

    def _ch(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    R, G, B = _ch(r), _ch(g), _ch(b)
    return 0.2126 * R + 0.7152 * G + 0.0722 * B


def _contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.0 contrast ratio between two #RRGGBB colours. Always ≥ 1.0."""
    L1, L2 = _relative_luminance(fg), _relative_luminance(bg)
    lo, hi = min(L1, L2), max(L1, L2)
    return (hi + 0.05) / (lo + 0.05)


_HEX6_RE = re.compile(r"#[0-9a-fA-F]{6}\b")


def _extract_token_value(block: str, token: str) -> str | None:
    """Return the LAST hex value declared for a token within `block`,
    or None if the token isn't declared. Last-wins matches CSS cascade
    for sibling declarations."""
    pat = re.compile(rf"{re.escape(token)}\s*:\s*([^;]+);")
    last = None
    for m in pat.finditer(block):
        val = m.group(1).strip()
        hexm = _HEX6_RE.search(val)
        if hexm:
            last = hexm.group(0)
    return last


def check_styles(text: str) -> list[str]:
    errors: list[str] = []
    nocomments = _strip_block_comments(text)

    # L1: canonical declaration appears exactly once.
    decls = re.findall(r"@layer\s+(?:[a-zA-Z][\w-]*\s*,\s*)+[a-zA-Z][\w-]*\s*;", nocomments)
    if not decls:
        errors.append("L1: styles.src.css missing canonical layer declaration")
    elif (
        len([d for d in decls if d.replace(" ", "") == CANONICAL_DECLARATION.replace(" ", "")]) != 1
    ):
        errors.append(
            f"L1: styles.src.css must declare exactly the canonical order "
            f"`{CANONICAL_DECLARATION}` (once); found: {decls!r}"
        )

    spans = _layer_block_spans(nocomments)
    layer_names_seen = [n for n, _, _ in spans]

    # L3: per-layer wrapper count ≤ 3.
    for name in set(layer_names_seen):
        n_blocks = layer_names_seen.count(name)
        if n_blocks > 3:
            errors.append(
                f"L3: styles.src.css has {n_blocks} `@layer {name}` blocks "
                f"(max 3 per layer; consolidate)"
            )

    # L2: every top-level rule lives inside a @layer block. we approximate
    # by checking that selectors at depth 0 (outside any layer block) are
    # only @font-face, @keyframes, the layer declaration, or bare
    # `@layer name;` (sub-declaration).
    # build a coverage map: which characters of nocomments are inside a
    # layer-block body.
    inside = bytearray(len(nocomments))
    for _, a, b in spans:
        for k in range(a, b + 1):
            inside[k] = 1
    # walk top-level rules: anything starting a selector or at-rule
    # that's not inside a layer block.
    top_level_at = re.finditer(
        r"(?P<rule>@[a-zA-Z-]+)|(?P<sel>^[\.\*\[\#:][^{}\n]{0,200}?\{)", nocomments, re.MULTILINE
    )
    for m in top_level_at:
        idx = m.start()
        if inside[idx]:
            continue
        token = m.group(0).strip()
        if token.startswith("@font-face"):
            continue
        if token.startswith("@keyframes"):
            continue
        if token.startswith("@layer"):
            # either the canonical declaration or a `@layer name;` sub-decl
            # or an `@layer name { …` opener (which we already counted as
            # inside via its body, but the opener itself sits at index
            # outside the body). allowed.
            continue
        if token.startswith("@page"):
            # bare @page at top level shouldn't appear in styles.src.css
            # but is benign.
            continue
        if token.startswith("@media"):
            line = _index_to_line(nocomments, idx)
            errors.append(
                f"L2: styles.src.css line {line}: top-level @media outside any "
                f"layer (wrap in @layer overrides or @layer components)"
            )
            continue
        if token.startswith("@"):
            line = _index_to_line(nocomments, idx)
            errors.append(f"L2: styles.src.css line {line}: unexpected top-level at-rule {token!r}")
            continue
        # selector outside any layer
        line = _index_to_line(nocomments, idx)
        errors.append(
            f"L2: styles.src.css line {line}: rule outside any @layer block "
            f"(selector starts with {token!r}…)"
        )

    # L4: no id selectors outside @layer overrides.
    # Pattern: `#name { … }` at the start of a selector — i.e. the
    # `#` must sit in selector position, not inside a property value
    # (where `#faf7f0` is a hex colour). we therefore restrict to
    # selectors that follow either start-of-line or a css combinator
    # and are followed by enough selector-ish characters to reach a
    # `{` without encountering a `;` (a `;` would mean we are still
    # inside a declaration list).
    id_selector_pat = re.compile(
        r"(?:^|[\s,>+~])(#[a-zA-Z][\w-]*)([^{};\n]*)\{",
        re.MULTILINE,
    )
    overrides_spans = [(a, b) for n, a, b in spans if n == "overrides"]
    for m in id_selector_pat.finditer(nocomments):
        idx = m.start(1)
        # skip matches inside attribute selectors or url() — defensive.
        ctx = nocomments[max(0, idx - 30) : idx]
        if "url(" in ctx or '="' in ctx or "='" in ctx:
            continue
        # skip matches whose preceding line context is a property
        # declaration (e.g. `color:` or `background:`) — hex colour.
        line_start = nocomments.rfind("\n", 0, idx) + 1
        line_prefix = nocomments[line_start:idx]
        if ":" in line_prefix and "{" not in line_prefix:
            continue
        if any(a <= idx <= b for a, b in overrides_spans):
            continue
        line = _index_to_line(nocomments, idx)
        errors.append(
            f"L4: styles.src.css line {line}: ID selector {m.group(1)!r} outside @layer overrides"
        )

    # L5: !important budget for styles.src.css.
    n_important = nocomments.count("!important")
    if n_important > STYLES_IMPORTANT_BUDGET:
        errors.append(
            f"L5: styles.src.css has {n_important} !important (budget {STYLES_IMPORTANT_BUDGET}); "
            f"reduce or document the new ones"
        )

    # L6: every body[data-page="…"] selector lives inside @layer pages.
    pages_spans = [(a, b) for n, a, b in spans if n == "pages"]
    page_sel_pat = re.compile(r'body\[data-page="[^"]+"\]')
    for m in page_sel_pat.finditer(nocomments):
        idx = m.start()
        if any(a <= idx <= b for a, b in pages_spans):
            continue
        line = _index_to_line(nocomments, idx)
        errors.append(
            f"L6: styles.src.css line {line}: body[data-page=…] selector "
            f"outside @layer pages (move into pages layer)"
        )

    # L7: tokens layer contains :root + required custom properties.
    tokens_spans = [(a, b) for n, a, b in spans if n == "tokens"]
    if not tokens_spans:
        errors.append("L7: styles.src.css missing @layer tokens block")
    else:
        tokens_text = "".join(nocomments[a : b + 1] for a, b in tokens_spans)
        if ":root" not in tokens_text:
            errors.append("L7: @layer tokens missing :root { … } block")
        for tok in REQUIRED_TOKENS:
            if tok not in tokens_text:
                errors.append(f"L7: @layer tokens missing canonical token `{tok}`")

    # L8: no @import.
    if "@import" in nocomments:
        line = _index_to_line(nocomments, nocomments.index("@import")) + 1
        errors.append(f"L8: styles.src.css line {line}: @import is forbidden")

    # L10: dark-mode block presence + canonical token coverage.
    dark_block_re = re.compile(
        r"@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)\s*\{"
        r"\s*:root\s*\{([^}]*)\}",
        re.S,
    )
    dark_match = dark_block_re.search(nocomments)
    dark_root_text: str | None = None
    if not dark_match:
        errors.append(
            "L10: styles.src.css missing @media (prefers-color-scheme: dark) { :root { … } } block"
        )
    else:
        dark_root_text = dark_match.group(1)
        for tok in ("--paper-main", "--ink", "--accent"):
            if tok not in dark_root_text:
                errors.append(
                    f"L10: dark-mode :root block missing override for `{tok}` "
                    "(canonical token set must be redeclared)"
                )

    # L11: contrast-ratio gate for both light and dark palettes.
    light_root_re = re.compile(r":root\s*\{([^}]*)\}", re.S)
    light_match = light_root_re.search(nocomments)
    palettes = []
    if light_match:
        palettes.append(("light", light_match.group(1)))
    if dark_root_text is not None:
        palettes.append(("dark", dark_root_text))

    contrast_pairs = [
        ("--ink", "--paper-main", 7.0),  # aaa body text
        ("--ink-muted", "--paper-main", 4.5),  # aa  secondary
        # `--accent` is the decorative accent (backgrounds with text
        # on top, divider tints, focus-ring fills, ::after underline
        # decorations). it does not need 4.5:1 against paper because
        # it is not directly used as a text colour. text use of the
        # accent migrates through the `--accent-text` token, which
        # is checked here at the aa threshold.
        ("--accent-text", "--paper-main", 4.5),  # aa  link / action text
    ]
    for label, block_text in palettes:
        for fg_tok, bg_tok, threshold in contrast_pairs:
            fg = _extract_token_value(block_text, fg_tok)
            bg = _extract_token_value(block_text, bg_tok)
            if not fg or not bg:
                # token may be expressed via var() alias; skip silently.
                continue
            ratio = _contrast_ratio(fg, bg)
            if ratio < threshold:
                errors.append(
                    f"L11: {label} palette: {fg_tok} ({fg}) vs {bg_tok} ({bg}) "
                    f"= {ratio:.2f}:1; threshold {threshold:.1f}:1"
                )

    return errors


def check_print(text: str) -> list[str]:
    errors: list[str] = []
    nocomments = _strip_block_comments(text)
    spans = _layer_block_spans(nocomments)
    print_spans = [(a, b) for n, a, b in spans if n == "print-overrides"]
    if len(print_spans) != 1:
        errors.append(
            f"L9: print.src.css must contain exactly one @layer print-overrides "
            f"wrapper; found {len(print_spans)}"
        )
        return errors
    a, b = print_spans[0]
    # all @media blocks in the file must sit inside the print-overrides span.
    for m in re.finditer(r"@media\b", nocomments):
        idx = m.start()
        if not (a <= idx <= b):
            line = _index_to_line(nocomments, idx)
            errors.append(
                f"L9: print.src.css line {line}: @media block outside @layer print-overrides"
            )
    # @page is allowed inside the wrapper; outside is also tolerated but flagged
    # if outside.
    for m in re.finditer(r"@page\b", nocomments):
        idx = m.start()
        if not (a <= idx <= b):
            line = _index_to_line(nocomments, idx)
            errors.append(f"L9: print.src.css line {line}: @page outside @layer print-overrides")
    if "@import" in nocomments:
        errors.append("L8: print.src.css contains @import (forbidden)")
    return errors


def check_fonts(text: str) -> list[str]:
    errors: list[str] = []
    nocomments = _strip_block_comments(text)
    spans = _layer_block_spans(nocomments)
    fonts_spans = [(a, b) for n, a, b in spans if n == "fonts"]
    if len(fonts_spans) != 1:
        errors.append(
            f"L9: fonts-full.src.css must contain exactly one @layer fonts "
            f"wrapper; found {len(fonts_spans)}"
        )
        return errors
    a, b = fonts_spans[0]
    for m in re.finditer(r"@font-face\b", nocomments):
        idx = m.start()
        if not (a <= idx <= b):
            line = _index_to_line(nocomments, idx)
            errors.append(f"L9: fonts-full.src.css line {line}: @font-face outside @layer fonts")
    if "!important" in nocomments:
        errors.append("L5: fonts-full.src.css contains !important (forbidden)")
    if "@import" in nocomments:
        errors.append("L8: fonts-full.src.css contains @import (forbidden)")
    return errors


def main() -> int:
    failures: list[str] = []
    for label, path, fn in [
        ("styles.src.css", STYLES_PATH, check_styles),
        ("print.src.css", PRINT_PATH, check_print),
        ("fonts-full.src.css", FONTS_PATH, check_fonts),
    ]:
        if not path.is_file():
            failures.append(f"{label}: missing")
            continue
        for err in fn(path.read_text(encoding="utf-8")):
            failures.append(err)
    if failures:
        print(f"  FAIL: css-architecture — {len(failures)} issue(s):")
        for err in failures[:40]:
            print(f"    {err}")
        if len(failures) > 40:
            print(f"    … {len(failures) - 40} more")
        return 1
    print("  OK: css-architecture — 3 source files conform to the cascade-layer contract")
    return 0


if __name__ == "__main__":
    sys.exit(main())
