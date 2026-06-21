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

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the whole gate runs over a fixture repo with no monkeypatching.
`evaluate(repo)` is the pure compute path returning a Result; `main()` is the
only adapter that prints/exits. Behaviour is byte-identical to the former
inline implementation.

Exit 0 = green; exit 1 = block.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
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
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

URL_RE = re.compile(r"""url\(\s*['"]?(/fonts/[^'")]+)['"]?\s*\)""")
PRELOAD_RE = re.compile(r'<link\s+[^>]*rel="preload"[^>]*as="font"[^>]*href="(/fonts/[^"]+)"')


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    # carry the OK-line counts so main() can render the exact summary line.
    css_refs: set[str] = field(default_factory=set)
    html_refs: set[str] = field(default_factory=set)
    sw_refs: set[str] = field(default_factory=set)
    integ_refs: set[str] = field(default_factory=set)

    @property
    def ok(self) -> bool:
        return not self.fails


def _collect_from_text(repo: Repo, rel: str, regex: re.Pattern) -> set:
    out = set()
    if not repo.is_file(rel):
        return out
    text = repo.read(rel)
    for m in regex.finditer(text):
        out.add(m.group(1))
    return out


def evaluate(repo: Repo) -> Result:
    r = Result()

    css_refs = _collect_from_text(repo, "public/styles.css", URL_RE) | _collect_from_text(
        repo, "public/fonts-full.css", URL_RE
    )
    html_refs = _collect_from_text(repo, "public/index.html", PRELOAD_RE)

    # service worker precache list.
    sw_refs: set = set()
    if repo.is_file("public/sw-cache-manifest.json"):
        try:
            data = json.loads(repo.read("public/sw-cache-manifest.json"))
            for key in ("critical", "optional"):
                for url in data.get(key, []):
                    if url.startswith("/fonts/"):
                        sw_refs.add(url)
        except json.JSONDecodeError as e:
            r.fails.append(f"sw-cache-manifest.json: {e}")

    # integrity manifest entries pointing at /fonts/.
    integ_refs: set = set()
    if repo.is_file("public/integrity.json"):
        try:
            data = json.loads(repo.read("public/integrity.json"))
            for k in data.get("files") or {}:
                if k.startswith("fonts/"):
                    integ_refs.add("/" + k)
        except json.JSONDecodeError as e:
            r.fails.append(f"integrity.json: {e}")

    all_refs = css_refs | html_refs | sw_refs | integ_refs

    for url in sorted(all_refs):
        rel = url.lstrip("/")
        if not repo.is_file(f"public/{rel}"):
            r.fails.append(f"MISSING: {url} referenced but not on disk")

    # Reverse: every /fonts/ file on disk should be referenced somewhere
    # (either in styles.css / fonts-full.css / sw-cache-manifest / integrity.
    # catches orphan fonts left over after a weight is dropped).
    for full in repo.glob("public/fonts/**/*.woff2"):
        rel = "/" + full[len("public/") :]
        if rel not in all_refs:
            r.fails.append(f"ORPHAN: {rel} on disk but not referenced anywhere")

    r.css_refs = css_refs
    r.html_refs = html_refs
    r.sw_refs = sw_refs
    r.integ_refs = integ_refs
    return r


def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(repo)

    if r.fails:
        print(f"FAIL: {len(r.fails)} font-asset issue(s):", file=sys.stderr)
        for f in r.fails[:30]:
            print(f"  ✗ {f}", file=sys.stderr)
        if len(r.fails) > 30:
            print(f"  … and {len(r.fails) - 30} more", file=sys.stderr)
        return 1

    print(
        f"OK: fonts — {len(r.css_refs)} CSS refs + {len(r.html_refs)} preloads "
        f"+ {len(r.sw_refs)} SW + {len(r.integ_refs)} integrity, "
        f"all resolved"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
