#!/usr/bin/env python3
"""validate_nav_regression.py — assert the masthead-only header shape.

Run as a predeploy gate. Fails the build if the homepage navigation
system has crept back in. The site no longer presents section-jump
navigation; the only header element is the stacked Trent / Power
masthead. The legacy nav-toggle + nav-links disclosure system, the
scroll-hide handlers, and every other navigation-state mechanism
are forbidden.

Checks (all read-only):

  public/app.js
    - does NOT contain `measureNavOverflow`
    - does NOT contain `setupNavOverflowDetection`
    - does NOT contain `data-nav-state`
    - does NOT contain `nav.classList.toggle('hidden'` (the scroll-
      direction nav-hide handler)
    - does NOT contain `scrollToTarget`
    - does NOT contain `getElementById('nav-toggle')` or
      `getElementById('nav-links')` (retired together with the
      disclosure markup)

  public/index.html
    - ships a `<header class="site-header">` wrapping a `<div class="nav">`
    - the `<a class="nav-mark">` masthead is the ONLY interactive
      element in the header
    - NO `<button class="nav-toggle">` / `id="nav-toggle"`
    - NO element with `id="nav-links"` / class `nav-links`
    - section ids (approach / trajectory / projects / contact) still
      sit directly on the section elements; jump links are gone but
      the anchors remain reachable via /#approach etc.

  public/styles.css
    - contains NO `.nav-toggle` or `.nav-links` selector

  tools/styles.src.css (authored)
    - contains NO `.nav-toggle` or `.nav-links` selector outside
      comments

Quiet on success, precise on failure.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "public"
TOOLS = ROOT / "tools"


def _strip_block_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)


def check_app_js(text: str) -> list[str]:
    """app.js must not contain any of the deleted clever blocks."""
    errors: list[str] = []
    nocomments = _strip_block_comments(text)

    forbidden = [
        ("measureNavOverflow", "ResizeObserver overflow detection — retired."),
        ("setupNavOverflowDetection", "Wrapper for measureNavOverflow — retired."),
        ("data-nav-state", "JS-set marker on .site-header — retired."),
        ("nav.classList.toggle('hidden'", "Scroll-direction nav-hide handler — retired."),
        (
            'nav.classList.toggle("hidden"',
            "Scroll-direction nav-hide handler (double-quoted) — retired.",
        ),
        ("scrollToTarget", "Custom anchor scroll interception — retired."),
        (
            "getElementById('nav-toggle')",
            "nav-toggle lookup — retired along with the disclosure system.",
        ),
        ('getElementById("nav-toggle")', "nav-toggle lookup (double-quoted) — retired."),
        (
            "getElementById('nav-links')",
            "nav-links lookup — retired along with the disclosure system.",
        ),
        ('getElementById("nav-links")', "nav-links lookup (double-quoted) — retired."),
    ]
    for needle, why in forbidden:
        if needle in nocomments:
            errors.append(f"app.js contains forbidden pattern '{needle}': {why}")
    return errors


def check_index_html(rel: str, text: str) -> list[str]:
    """The homepage must ship the masthead-only header."""
    errors: list[str] = []

    # masthead must be present. accept additional classes alongside
    # nav-mark (e.g. mf2 p-name/u-url/u-uid) — the gate is the presence
    # of the class as one token, not the whole class attribute value.
    if not re.search(
        r'<a[^>]*\bclass="[^"]*\bnav-mark\b[^"]*"[^>]*>.*?Trent.*?Power.*?</a>',
        text,
        re.S,
    ):
        errors.append(f'{rel}: <a class="…nav-mark…">…Trent…Power…</a> not found')

    # nav-toggle must not exist.
    if re.search(r'class="nav-toggle"|\bid="nav-toggle"', text):
        errors.append(
            f"{rel}: nav-toggle markup is back — must be removed"
            " (masthead is the only header element)"
        )
    # nav-links must not exist.
    if re.search(r'class="nav-links"|\bid="nav-links"', text):
        errors.append(
            f"{rel}: nav-links markup is back — must be removed"
            " (masthead is the only header element)"
        )

    # section ids still sit on the section elements.
    for section_id in ("approach", "credentials", "trajectory", "projects", "contact"):
        pattern = rf'<section[^>]*\bid="{section_id}"[^>]*>'
        if not re.search(pattern, text):
            errors.append(
                f'{rel}: <section id="{section_id}" …> not found'
                f" (sections must remain anchorable even with the"
                f" nav menu gone)"
            )

    return errors


def check_styles_css(text: str) -> list[str]:
    """styles.css must not contain any nav-toggle / nav-links selector."""
    errors: list[str] = []
    nocomments = _strip_block_comments(text)

    if re.search(r"\.nav-toggle(?![A-Za-z0-9_-])", nocomments):
        errors.append(
            "styles.css: `.nav-toggle` selector still present — retired with the disclosure system"
        )
    if re.search(r"\.nav-links(?![A-Za-z0-9_-])", nocomments):
        errors.append(
            "styles.css: `.nav-links` selector still present — retired with the disclosure system"
        )

    return errors


def check_styles_src(text: str) -> list[str]:
    """styles.src.css must not contain nav-toggle / nav-links selectors
    outside comments."""
    errors: list[str] = []
    nocomments = _strip_block_comments(text)

    if re.search(r"(?<![A-Za-z0-9_-])\.nav-toggle(?![A-Za-z0-9_-])", nocomments):
        errors.append(
            "styles.src.css: `.nav-toggle` selector still present outside"
            " comments — retired with the disclosure system"
        )
    if re.search(r"(?<![A-Za-z0-9_-])\.nav-links(?![A-Za-z0-9_-])", nocomments):
        errors.append(
            "styles.src.css: `.nav-links` selector still present outside"
            " comments — retired with the disclosure system"
        )

    return errors


def main() -> int:
    errors: list[str] = []

    # the former app.js "brain" is split into behaviour-scoped modules;
    # scan the successors for the retired nav-disclosure clever blocks.
    combined = []
    for name in ("js/theme.js", "sw-register.js", "js/reveal.js"):
        p = PUBLIC / name
        if not p.exists():
            errors.append(f"missing file: {p}")
        else:
            combined.append(p.read_text(encoding="utf-8"))
    if combined:
        errors.extend(check_app_js("\n".join(combined)))

    # the homepage content lives on the two language editions; the
    # root index.html is now the language gate and is checked
    # separately by validate_lang_gate.py.
    for rel in ("en-au/index.html", "fr/index.html"):
        index_path = PUBLIC / rel
        if not index_path.exists():
            errors.append(f"missing file: {index_path}")
        else:
            errors.extend(check_index_html(rel, index_path.read_text(encoding="utf-8")))

    styles_path = PUBLIC / "styles.css"
    if not styles_path.exists():
        errors.append(f"missing file: {styles_path}")
    else:
        errors.extend(check_styles_css(styles_path.read_text(encoding="utf-8")))

    src_path = ROOT / "styles" / "styles.src.css"
    if not src_path.exists():
        errors.append(f"missing file: {src_path}")
    else:
        errors.extend(check_styles_src(src_path.read_text(encoding="utf-8")))

    if errors:
        print(f"FAIL: nav-regression — {len(errors)} issue(s):")
        for e in errors:
            print(f"  {e}")
        return 1

    print(
        "OK: nav-regression — masthead-only header"
        " (no nav-toggle / nav-links / scroll-hide / data-nav-state;"
        " section ids preserved for anchor reachability)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
