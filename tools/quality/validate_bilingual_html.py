#!/usr/bin/env python3
"""validate_bilingual_html.py — SEO/GEO invariants for the rendered editions.

Scans the deployable bilingual tree (default public/, or --root DIR) and
asserts the migration's search/machine-readability contract:

  · bilingual completeness — every route key resolves to an /en/ and /fr/ file
  · self-canonical — each /en/** /fr/** page canonicalises to its own URL,
    never cross-language; / canonicalises to /
  · hreflang clusters — every page emits the reciprocal en/fr/x-default triplet
  · <html lang> matches the tree the file sits in
  · no runtime i18n — no window.I18N / applyLanguage / LANG_CYCLE / i18n-core /
    data-i18n leaks into the rendered HTML

Usage:
    python3 tools/validate_bilingual_html.py [--root DIR]
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
import routes as routemap  # noqa: E402

RUNTIME_I18N = [
    re.compile(r"window\.I18N"),
    re.compile(r"\bapplyLanguage\b"),
    re.compile(r"\bLANG_CYCLE\b"),
    re.compile(r"i18n-core"),
    re.compile(r"\bdata-i18n[a-z-]*="),
]


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    argv = sys.argv[1:]
    root = PUBLIC_DIR
    if "--root" in argv:
        root = Path(argv[argv.index("--root") + 1]).resolve()
    if not root.exists():
        print(
            f"✗ rendered tree not found: {root}\n  run: python3 tools/render_pages.py",
            file=sys.stderr,
        )
        return 1

    base = routemap.base_url()
    errors: list[str] = []

    # 1 — bilingual completeness + per-page invariants
    for key in routemap.route_keys():
        for lang in routemap.languages():
            rel = routemap.route_output(key, lang)
            path = root / rel
            if not path.exists():
                errors.append(f"missing rendered page: {rel}")
                continue
            html = _read(path)
            canonical = base + routemap.route_path(key, lang)

            m = re.search(r'<link rel="canonical" href="([^"]+)"', html)
            if not m:
                errors.append(f"{rel}: no canonical")
            elif m.group(1) != canonical:
                errors.append(f"{rel}: canonical {m.group(1)} != {canonical}")

            for hl, url in routemap.hreflang_cluster(key).items():
                if f'hreflang="{hl}" href="{url}"' not in html:
                    errors.append(f"{rel}: missing hreflang {hl} -> {url}")

            # the <html lang> attribute carries the BCP47 tag (en-AU, fr),
            # not the internal language key.
            lm = re.search(r'<html lang="([a-zA-Z-]+)"', html)
            expected = routemap.lang_bcp47(lang)
            if not lm or lm.group(1) != expected:
                errors.append(
                    f"{rel}: <html lang> is {lm and lm.group(1)!r}, expected {expected!r}"
                )

            for pat in RUNTIME_I18N:
                if pat.search(html):
                    errors.append(f"{rel}: runtime-i18n leak /{pat.pattern}/")

    for e in errors:
        print(f"  ✗ {e}", file=sys.stderr)
    if errors:
        print(f"\n✗ bilingual HTML: {len(errors)} error(s)", file=sys.stderr)
        return 1
    n = len(routemap.route_keys()) * len(routemap.languages())
    print(f"✓ bilingual HTML OK ({n} pages: canonical, hreflang, lang, no runtime i18n)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
