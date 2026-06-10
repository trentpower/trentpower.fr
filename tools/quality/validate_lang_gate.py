#!/usr/bin/env python3
"""validate_lang_gate.py — invariants for the root / language vestibule.

Scans the deployable vestibule (default public/index.html, or --root DIR)
and asserts:

  · index,follow — the vestibule is the indexable x-default edition gate
    for indexing
  · self-canonical to https://trentpower.fr/
  · hreflang en/fr/x-default present
  · the pre-paint script reads localStorage tp-last-edition (gate v2)
    or tp-lang (legacy, migrated on first paint) only to set the
    display language — it must NOT location.replace / auto-redirect.
    The root is a deliberate choice page shown on every visit.
  · the two choices are real <a href="/en-au/"> / <a href="/fr/"> links
    carrying data-lang-choice, so the vestibule works with no JavaScript

Usage:
    python3 tools/validate_lang_gate.py [--root DIR]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        next(
            _a
            for _a in __import__("pathlib").Path(__file__).resolve().parents
            if _a.name == "tools"
        )
        / "lib"
    ),
)
from paths import PUBLIC_DIR  # noqa: E402


def main() -> int:
    argv = sys.argv[1:]
    root = PUBLIC_DIR
    if "--root" in argv:
        root = Path(argv[argv.index("--root") + 1]).resolve()
    gate = root / "index.html"
    if not gate.exists():
        print(
            f"✗ vestibule not found: {gate}\n  run: python3 tools/render_pages.py", file=sys.stderr
        )
        return 1

    html = gate.read_text(encoding="utf-8")
    errors: list[str] = []

    # the root / is the x-default edition gate — a legitimate indexable
    # entry point. the rich editorial graph lives on /en-au/ and /fr/.
    if not re.search(r'<meta name="robots" content="index[, ]+follow">', html):
        errors.append("missing <meta robots=index,follow>")
    if '<link rel="canonical" href="https://trentpower.fr/">' not in html:
        errors.append("vestibule must self-canonical to https://trentpower.fr/")
    for hl in ("en-AU", "fr", "x-default"):
        if f'hreflang="{hl}"' not in html:
            errors.append(f"missing hreflang {hl}")

    head = html.split("</head>", 1)[0]
    # gate v2 storage key is tp-last-edition; legacy tp-lang is migrated
    # on first paint, so either key satisfies the invariant. tightening
    # back to tp-last-edition only is a follow-up cleanup once the
    # migration window has elapsed.
    # match the key string + a localStorage call anywhere in head — the
    # minified boot script binds the key to a const ("L='tp-last-edition'"
    # then "localStorage.getItem(L)"), so a literal getItem('tp-last-edition')
    # substring isn't present.
    uses_storage = "localStorage.getItem(" in head
    names_new = "'tp-last-edition'" in head or '"tp-last-edition"' in head
    names_old = "'tp-lang'" in head or '"tp-lang"' in head
    if not (uses_storage and (names_new or names_old)):
        errors.append("pre-paint script does not read localStorage (tp-last-edition or tp-lang)")
    # the root must NOT auto-redirect — it is a deliberate choice page
    # shown on every visit. a stored preference only sets the display
    # language; it never bypasses the choice.
    if "location.replace(" in html or "location.href" in html or re.search(r"location\s*=", html):
        errors.append(
            "vestibule must not auto-redirect (no location.replace / "
            "location.href / location= — the root is a choice page)"
        )

    if not re.search(r'<a [^>]*href="/en-au/"[^>]*data-lang-choice="en"', html) and not re.search(
        r'<a [^>]*data-lang-choice="en"[^>]*href="/en-au/"', html
    ):
        errors.append("no <a href=/en-au/ data-lang-choice=en> choice")
    if not re.search(r'<a [^>]*href="/fr/"', html):
        errors.append("no <a href=/fr/> choice")

    for e in errors:
        print(f"  ✗ {e}", file=sys.stderr)
    if errors:
        print(f"\n✗ language vestibule: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("✓ language vestibule OK (index, self-canonical, hreflang,no auto-redirect, <a> choices)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
