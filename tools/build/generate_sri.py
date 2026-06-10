#!/usr/bin/env python3
"""
generate_sri.py , Add or refresh SHA-384 Subresource Integrity attributes
on every same-origin <link rel="stylesheet"> and <script src="..."> tag in
the active HTML files (and the frozen archive HTML files).

Run AFTER generate_site.py and BEFORE generate_integrity.py:

    python3 generate_site.py     # rebuild HTML / metadata
    python3 generate_sri.py      # this script , sets integrity="sha384-..."
    python3 generate_sw.py       # if cache list changes
    python3 generate_integrity.py
    gpg --detach-sign --armor -o integrity.json.sig integrity.json
    gpg --verify integrity.json.sig integrity.json

Idempotent. Same-origin only. Crossorigin attribute is intentionally NOT
added , it is not required for same-origin SRI and would change request
semantics. require-sri-for is intentionally NOT used in CSP , obsolete.

What this protects:
  - <link rel="stylesheet" href="/...css">  (and ./relative.css)
  - <script src="/...js" ...>               (and ./relative.js)

What this does NOT touch (out of scope or unsupported by SRI spec):
  - inline <script>...</script>             (covered by CSP hashes)
  - <script type="application/ld+json">     (CSP-aware; not script-src)
  - service worker registration             (not supported by SRI spec)
  - manifest.webmanifest, favicons, icons   (covered by signed integrity manifest)
  - @font-face url('/fonts/*.woff2')        (covered by signed integrity manifest)
  - external/cross-origin resources         (none on this site by design)

If a referenced local file is missing, this script aborts with a clear
error rather than silently writing a stale or incorrect hash.
"""

import base64
import hashlib
import os
import pathlib
import re
import sys

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
from paths import PUBLIC_DIR as ROOT

os.chdir(ROOT)


# active html — every .html under public/ except the frozen archive
# tree (swept below is forbidden). discovered by walk so the bilingual
# /en-au/ and /fr/ trees are picked up automatically.
def _discover_active_html() -> list:
    import glob

    out = []
    for p in sorted(glob.glob("**/*.html", recursive=True)):
        if p.startswith("integrity/releases/"):
            continue  # frozen archives — see ARCHIVE_HTML note below
        out.append(p)
    return out


ACTIVE_HTML = _discover_active_html()

# frozen archive html is intentionally not swept here. frozen archives
# under /integrity/releases/<YYYY-MM>/ are sealed at the time of release
# and the predeploy gate's frozen-archive immutability check enforces
# their byte-stability against metadata/archive-baseline.json. Re-sweeping
# sri on those files would silently re-derive bytes after a referenced
# asset changed (e.g. a stylesheet renamed) and either drift the
# archive (failing the immutability gate) or burn one through the
# baseline reseal. frozen means frozen.
ARCHIVE_HTML: list[str] = []

ALL_HTML = ACTIVE_HTML + ARCHIVE_HTML


def sri_hash(local_path: pathlib.Path) -> str:
    """SHA-384 SRI digest, prefixed."""
    digest = hashlib.sha384(local_path.read_bytes()).digest()
    return "sha384-" + base64.b64encode(digest).decode("ascii")


def resolve_local(href: str, html_path: pathlib.Path) -> pathlib.Path | None:
    """Resolve a same-origin href to a local Path under ROOT.
    Returns None for cross-origin or unsupported schemes. Query strings
    (e.g. ?v=cache-buster) and fragments are stripped before resolving
    so SRI generation works for cache-busted URLs."""
    if href.startswith("//") or href.startswith("http://") or href.startswith("https://"):
        return None
    # strip ?query and #fragment , both are used for cache-busting only
    # and don't affect the on-disk file path.
    for sep in ("?", "#"):
        if sep in href:
            href = href.split(sep, 1)[0]
    if href.startswith("/"):
        return ROOT / href.lstrip("/")
    if href.startswith("./") or not href.startswith(("data:", "mailto:", "javascript:")):
        return (ROOT / html_path.parent / href).resolve()
    return None


# match <link ...> tags. must include rel="stylesheet" (allowing other
# rel values like "stylesheet print" or with extra whitespace).
LINK_RE = re.compile(r"<link\b[^>]*?>", re.IGNORECASE)

# match external <script src="..."> ... </script>. requires src attribute,
# which excludes inline scripts and JSON-LD blocks (no src attr).
SCRIPT_RE = re.compile(
    r"<script\b[^>]*?\bsrc\s*=\s*\"[^\"]+\"[^>]*></script>",
    re.IGNORECASE,
)

ATTR_RE_TPL = r'\b{name}\s*=\s*"([^"]*)"'


def get_attr(tag: str, name: str) -> str | None:
    m = re.search(ATTR_RE_TPL.format(name=name), tag, re.IGNORECASE)
    return m.group(1) if m else None


def set_or_replace_integrity(tag: str, value: str, after_attr: str) -> str:
    """If integrity="..." exists, replace its value. Otherwise insert
    integrity="<value>" immediately after `after_attr`."""
    integ_re = re.compile(ATTR_RE_TPL.format(name="integrity"), re.IGNORECASE)
    if integ_re.search(tag):
        return integ_re.sub(f'integrity="{value}"', tag, count=1)
    after_re = re.compile(
        r"(\b" + after_attr + r'\s*=\s*"[^"]*")',
        re.IGNORECASE,
    )
    return after_re.sub(r'\1 integrity="' + value + r'"', tag, count=1)


def update_link(tag: str, html_path: pathlib.Path, errors: list) -> str:
    rel = get_attr(tag, "rel") or ""
    if "stylesheet" not in rel.lower().split():
        return tag  # icon, manifest, alternate, me, author, canonical , skip
    # /print.css is loaded with media="print" and is rejected by some
    # print engines when sri is combined with deferred-load stylesheets.
    # skip it so the browser can apply print rules at print time.
    # strip ?query before comparing so cache-busted urls are also skipped.
    href = get_attr(tag, "href") or ""
    href_path = href.split("?", 1)[0].split("#", 1)[0]
    if href_path == "/print.css":
        return tag
    href = get_attr(tag, "href")
    if not href:
        return tag
    local = resolve_local(href, html_path)
    if local is None:
        return tag  # cross-origin , leave alone (none expected on this site)
    if not local.is_file():
        errors.append(f'{html_path}: <link href="{href}"> -> {local} (file not found)')
        return tag
    return set_or_replace_integrity(tag, sri_hash(local), "href")


def update_script(tag: str, html_path: pathlib.Path, errors: list) -> str:
    src = get_attr(tag, "src")
    if not src:
        return tag  # inline script , skip
    src_path = src.split("?", 1)[0].split("#", 1)[0]
    # /verify/verification-data.js is the build's only self-referential
    # asset: its own bytes embed file hashes that include the html hash,
    # which in turn embeds this script's sri. including sri here creates
    # a cycle that prevents two consecutive builds from producing
    # byte-identical output. its integrity is still covered by
    # /integrity.json (signed manifest) , the signed manifest is the
    # authoritative public hash. browsers fetch it without per-tag sri.
    if src_path == "/verify/verification-data.js":
        # strip any pre-existing integrity attribute (left over from
        # earlier builds) so html stays byte-stable.
        integ_re = re.compile(ATTR_RE_TPL.format(name="integrity"), re.IGNORECASE)
        if integ_re.search(tag):
            tag = re.sub(r'\s+integrity\s*=\s*"[^"]*"', "", tag, count=1, flags=re.IGNORECASE)
        return tag
    local = resolve_local(src, html_path)
    if local is None:
        return tag  # cross-origin , leave alone (none expected on this site)
    if not local.is_file():
        errors.append(f'{html_path}: <script src="{src}"> -> {local} (file not found)')
        return tag
    return set_or_replace_integrity(tag, sri_hash(local), "src")


def process_file(html_rel: str, errors: list) -> tuple[bool, int, int]:
    p = ROOT / html_rel
    src = p.read_text(encoding="utf-8")

    link_count = 0
    script_count = 0

    def link_sub(m):
        nonlocal link_count
        new = update_link(m.group(0), pathlib.Path(html_rel), errors)
        if new != m.group(0):
            link_count += 1
        return new

    def script_sub(m):
        nonlocal script_count
        new = update_script(m.group(0), pathlib.Path(html_rel), errors)
        if new != m.group(0):
            script_count += 1
        return new

    new_src = LINK_RE.sub(link_sub, src)
    new_src = SCRIPT_RE.sub(script_sub, new_src)

    changed = new_src != src
    if changed:
        p.write_text(new_src, encoding="utf-8")
    return changed, link_count, script_count


def main() -> int:
    errors: list[str] = []
    total_changed = 0
    total_links = 0
    total_scripts = 0

    for h in ALL_HTML:
        if not (ROOT / h).is_file():
            errors.append(f"missing HTML: {h}")
            continue
        changed, lc, sc = process_file(h, errors)
        total_links += lc
        total_scripts += sc
        if changed:
            total_changed += 1
            print(f"  upd  {h:50}  links={lc} scripts={sc}")
        else:
            print(f"  ok   {h:50}  (no change)")

    if errors:
        print("\nERRORS:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print()
    print(f"✓ SRI applied: {total_changed}/{len(ALL_HTML)} HTML files updated")
    print(f"  link[rel=stylesheet] integrity refreshed: {total_links}")
    print(f"  external <script src> integrity refreshed: {total_scripts}")
    print()
    print("Build order reminder:")
    print("  1. python3 generate_site.py")
    print("  2. python3 generate_sri.py     ← you are here")
    print("  3. python3 generate_sw.py      (if cache list changes)")
    print("  4. python3 generate_integrity.py")
    print("  5. gpg --detach-sign --armor -o integrity.json.sig integrity.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
