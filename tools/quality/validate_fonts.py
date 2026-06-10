#!/usr/bin/env python3
"""tools/validate_fonts.py — predeploy font-existence gate.

Walks every font URL referenced from the deployed bundle and verifies
the matching file exists under public/. Catches:

  • Stale preload references that survived a font rename.
  • @font-face declarations pointing at deleted weights.
  • Service-Worker precache list referencing fonts that no longer
    ship.
  • Integrity manifest entries pointing at missing bytes.

Sources scanned
  • public/styles.css        (Critical subset @font-face)
  • public/fonts-full.css    (full editorial @font-face)
  • public/index.html        (preload links)
  • public/sw-cache-manifest.json (precache list)
  • public/integrity.json    (manifest)

The gate intentionally does not chase below-fold pages; styles.css
and fonts-full.css are the only stylesheets that own @font-face
declarations, and index.html is the only page that preloads fonts.

Exit 0 = green; exit 1 = block.
"""

import json
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
from paths import PUBLIC_DIR  # noqa: E402

URL_RE = re.compile(r"""url\(\s*['"]?(/fonts/[^'")]+)['"]?\s*\)""")
PRELOAD_RE = re.compile(r'<link\s+[^>]*rel="preload"[^>]*as="font"[^>]*href="(/fonts/[^"]+)"')


def _collect_from_text(path: pathlib.Path, regex: re.Pattern) -> set:
    out = set()
    if not path.is_file():
        return out
    text = path.read_text(encoding="utf-8")
    for m in regex.finditer(text):
        out.add(m.group(1))
    return out


def main() -> int:
    fails: list = []

    css_refs = _collect_from_text(PUBLIC_DIR / "styles.css", URL_RE) | _collect_from_text(
        PUBLIC_DIR / "fonts-full.css", URL_RE
    )
    html_refs = _collect_from_text(PUBLIC_DIR / "index.html", PRELOAD_RE)

    # service worker precache list.
    sw_refs: set = set()
    sw_manifest = PUBLIC_DIR / "sw-cache-manifest.json"
    if sw_manifest.is_file():
        try:
            data = json.loads(sw_manifest.read_text(encoding="utf-8"))
            for key in ("critical", "optional"):
                for url in data.get(key, []):
                    if url.startswith("/fonts/"):
                        sw_refs.add(url)
        except json.JSONDecodeError as e:
            fails.append(f"sw-cache-manifest.json: {e}")

    # integrity manifest entries pointing at /fonts/.
    integ_refs: set = set()
    integ = PUBLIC_DIR / "integrity.json"
    if integ.is_file():
        try:
            data = json.loads(integ.read_text(encoding="utf-8"))
            for k in data.get("files") or {}:
                if k.startswith("fonts/"):
                    integ_refs.add("/" + k)
        except json.JSONDecodeError as e:
            fails.append(f"integrity.json: {e}")

    all_refs = css_refs | html_refs | sw_refs | integ_refs

    for url in sorted(all_refs):
        rel = url.lstrip("/")
        on_disk = PUBLIC_DIR / rel
        if not on_disk.is_file():
            fails.append(f"MISSING: {url} referenced but not on disk")

    # Reverse: every /fonts/ file on disk should be referenced somewhere
    # (either in styles.css / fonts-full.css / sw-cache-manifest / integrity.
    # catches orphan fonts left over after a weight is dropped).
    for fp in sorted((PUBLIC_DIR / "fonts").rglob("*.woff2")):
        rel = "/" + fp.relative_to(PUBLIC_DIR).as_posix()
        if rel not in all_refs:
            fails.append(f"ORPHAN: {rel} on disk but not referenced anywhere")

    if fails:
        print(f"FAIL: {len(fails)} font-asset issue(s):", file=sys.stderr)
        for f in fails[:30]:
            print(f"  ✗ {f}", file=sys.stderr)
        if len(fails) > 30:
            print(f"  … and {len(fails) - 30} more", file=sys.stderr)
        return 1

    print(
        f"OK: fonts — {len(css_refs)} CSS refs + {len(html_refs)} preloads "
        f"+ {len(sw_refs)} SW + {len(integ_refs)} integrity, "
        f"all resolved"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
