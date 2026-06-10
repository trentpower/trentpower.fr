#!/usr/bin/env python3
"""extract_from_data_i18n.py — one-time migration bridge (phase A).

Converts the hand-authored runtime-i18n HTML in public/*.html into clean
editorial templates: every data-i18n* directive becomes a {{ token }} and
the directive attribute is stripped. The token key is the directive's value
verbatim — it already maps to a dotted path in the content/<lang>/ YAML
(e.g. data-i18n="privacy.page_h1" -> {{ privacy.page_h1 }}).

Tokens are typed so the renderer knows the insertion context:
    {{ K }}        text      — HTML-escaped on insert
    {{ html:K }}   markup    — inserted raw
    {{ list:K }}   list      — rendered as <li>…</li> items (raw)
    {{ attr:K }}   attribute — attribute-escaped on insert

Directive handling:
    data-i18n="K"             element text content   -> {{ K }}
    data-i18n-html="K"        element inner HTML      -> {{ html:K }}
    data-i18n-list="K"        <ul>/<ol> children      -> {{ list:K }}
    data-i18n-title="K"       -> title="{{ attr:K }}"
    data-i18n-aria-label="K"  -> aria-label="{{ attr:K }}" (drops the static one)
    data-i18n-copied="K"      -> data-copied="{{ attr:K }}"

Output: templates/pages/<route>.html — full-document templates. Partial
factoring (head/masthead/footer) and runtime-chrome removal are handled in
later phases; this bridge only performs the directive -> token rewrite.

After cut-over this script is one-time tooling; no build stage depends on it.

Usage:
    python3 tools/build/copy/extract_from_data_i18n.py            # write templates
    python3 tools/build/copy/extract_from_data_i18n.py --check    # report only
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(next(_a for _a in __import__("pathlib").Path(__file__).resolve().parents if _a.name == "tools") / "lib"))
from paths import PUBLIC_DIR, TEMPLATES_DIR  # noqa: E402

# route template name -> source HTML under public/
PAGE_SOURCES = {
    "home": "index.html",
    "privacy": "privacy/index.html",
    "security": "security/index.html",
    "security-acknowledgments": "security/acknowledgments/index.html",
    "integrity": "integrity/index.html",
    "integrity-releases": "integrity/releases/index.html",
    "integrity-verify-locally": "integrity/verify-locally/index.html",
    "verify": "verify/index.html",
    "source": "source/index.html",
    "source-view": "source/view/index.html",
    "403": "403.html",
    "404": "404.html",
    "500": "500.html",
    "maintenance": "maintenance.html",
    "sw-reset": "sw-reset/index.html",
}

# content-consuming directives: <TAG ... data-i18nX="K" ...>old</TAG> -> {{ K }}
_HTML_RE = re.compile(r'<(\w+)([^>]*?)\s+data-i18n-html="([^"]+)"([^>]*?)>.*?</\1>', re.DOTALL)
_TEXT_RE = re.compile(r'<(\w+)([^>]*?)\s+data-i18n="([^"]+)"([^>]*?)>.*?</\1>', re.DOTALL)
_LIST_RE = re.compile(r'<(ul|ol)([^>]*?)\s+data-i18n-list="([^"]+)"([^>]*?)>.*?</\1>', re.DOTALL)
# whole opening tag carrying data-i18n-aria-label
_ARIA_TAG_RE = re.compile(r'<\w+[^>]*\sdata-i18n-aria-label="[^"]+"[^>]*>')
_ARIA_LABEL_ATTR = re.compile(r'\s+aria-label="[^"]*"')
_DIRECTIVE_SCAN = re.compile(r"data-i18n[a-z-]*")

# runtime-i18n chrome removed from the static editions (phase E):
#   · the head IIFE combined language + theme bootstrap — language is now
#     fixed in <html lang>, so it collapses to a theme-only bootstrap;
#   · the /i18n-core.js bundle disappears entirely.
_BOOTSTRAP_RE = re.compile(
    r"<script>\(\(\)=>\{const e=document\.documentElement;.*?\}\)\(\);</script>",
    re.DOTALL,
)
_I18N_CORE_RE = re.compile(r'[ \t]*<script src="/i18n-core\.js[^"]*"[^>]*></script>\n?')
_THEME_BOOTSTRAP = (
    "<script>(()=>{const e=document.documentElement;e.classList.add('js');"
    "try{const m=localStorage.getItem('tp-theme');"
    "if(m==='dark'||m==='light')e.dataset.theme=m}catch(_){}})();</script>"
)


def _strip_aria(tag: str) -> str:
    """Within one opening tag: promote data-i18n-aria-label to aria-label,
    dropping any static aria-label that was the English default."""
    m = re.search(r'\s+data-i18n-aria-label="([^"]+)"', tag)
    key = m.group(1)
    tag = tag[: m.start()] + tag[m.end() :]
    tag = _ARIA_LABEL_ATTR.sub("", tag, count=0)
    # re-insert a single resolved aria-label just before the closing '>'
    return tag[:-1].rstrip() + f' aria-label="{{{{ attr:{key} }}}}">'


def transform(html: str) -> str:
    html = _HTML_RE.sub(lambda m: f"<{m[1]}{m[2]}{m[4]}>{{{{ html:{m[3]} }}}}</{m[1]}>", html)
    html = _LIST_RE.sub(lambda m: f"<{m[1]}{m[2]}{m[4]}>{{{{ list:{m[3]} }}}}</{m[1]}>", html)
    html = _TEXT_RE.sub(lambda m: f"<{m[1]}{m[2]}{m[4]}>{{{{ {m[3]} }}}}</{m[1]}>", html)
    html = re.sub(
        r'\sdata-i18n-title="([^"]+)"',
        lambda m: f' title="{{{{ attr:{m[1]} }}}}"',
        html,
    )
    html = re.sub(
        r'\sdata-i18n-copied="([^"]+)"',
        lambda m: f' data-copied="{{{{ attr:{m[1]} }}}}"',
        html,
    )
    html = _ARIA_TAG_RE.sub(lambda m: _strip_aria(m[0]), html)
    # phase E — drop runtime-i18n chrome
    html = _BOOTSTRAP_RE.sub(_THEME_BOOTSTRAP, html, count=1)
    html = _I18N_CORE_RE.sub("", html)
    return html


def main() -> int:
    check = "--check" in sys.argv
    out_dir = TEMPLATES_DIR / "pages"
    errors = 0

    for name, rel in PAGE_SOURCES.items():
        src = PUBLIC_DIR / rel
        if not src.exists():
            print(f"  ERROR missing source: {rel}", file=sys.stderr)
            errors += 1
            continue
        original = src.read_text(encoding="utf-8")
        before = len(_DIRECTIVE_SCAN.findall(original))
        result = transform(original)
        leftover = _DIRECTIVE_SCAN.findall(result)
        status = "OK" if not leftover else f"LEFTOVER {len(leftover)}"
        if leftover:
            errors += 1
        print(f"  {name:28s}  {before:4d} directives -> {status}")
        if not check:
            dest = out_dir / f"{name}.html"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(result, encoding="utf-8")

    if not check and not errors:
        print(f"\n✓ wrote {len(PAGE_SOURCES)} templates to templates/pages/")
    if errors:
        print(f"\n✗ {errors} page(s) with unresolved directives", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
