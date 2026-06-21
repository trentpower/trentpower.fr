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

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the whole gate runs over a fixture repo with no monkeypatching.
`evaluate(repo, tree_prefix)` is the pure compute path returning a Result; `main()`
is the only adapter that reads argv, prints, and exits. The per-page invariants,
patterns, page set (from the routes library) and messages are lifted verbatim
from the former inline scan.
"""

from __future__ import annotations

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
import routes as routemap  # noqa: E402
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

# the rendered tree lives under public/ in the repo; the Repo seam reads
# "<tree_prefix>/<route_output>". --root points the prefix at an arbitrary tree.
TREE_PREFIX = "public"

RUNTIME_I18N = [
    re.compile(r"window\.I18N"),
    re.compile(r"\bapplyLanguage\b"),
    re.compile(r"\bLANG_CYCLE\b"),
    re.compile(r"i18n-core"),
    re.compile(r"\bdata-i18n[a-z-]*="),
]


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    # set when the rendered tree itself is absent — a load failure, not an
    # invariant failure; main() renders it with the original run-hint message.
    missing: str | None = None

    @property
    def ok(self) -> bool:
        return not self.fails and self.missing is None


def evaluate(repo: Repo, tree_prefix: str = TREE_PREFIX) -> Result:
    r = Result()
    if not (repo.root / tree_prefix).exists():
        r.missing = tree_prefix
        return r

    base = routemap.base_url()
    errors: list[str] = r.fails

    # 1 — bilingual completeness + per-page invariants
    for key in routemap.route_keys():
        for lang in routemap.languages():
            rel = routemap.route_output(key, lang)
            tree_rel = f"{tree_prefix}/{rel}" if tree_prefix else rel
            if not repo.is_file(tree_rel):
                errors.append(f"missing rendered page: {rel}")
                continue
            html = repo.read(tree_rel)
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

    return r


def main(repo_root: Path = REPO_ROOT) -> int:
    argv = sys.argv[1:]
    if "--root" in argv:
        # --root points at an arbitrary deployable tree; resolve it relative
        # to repo_root so the Repo seam reads "<prefix>/<route_output>".
        root = Path(argv[argv.index("--root") + 1]).resolve()
        try:
            prefix = root.relative_to(repo_root).as_posix()
        except ValueError:
            # outside the repo tree — read it directly via its own Repo root.
            return _run(Repo(root), "")
        return _run(Repo(repo_root), prefix)
    return _run(Repo(repo_root), TREE_PREFIX)


def _run(repo: Repo, tree_prefix: str) -> int:
    r = evaluate(repo, tree_prefix)
    if r.missing is not None:
        tree = repo.root / r.missing
        print(
            f"✗ rendered tree not found: {tree}\n  run: python3 tools/render_pages.py",
            file=sys.stderr,
        )
        return 1
    for e in r.fails:
        print(f"  ✗ {e}", file=sys.stderr)
    if r.fails:
        print(f"\n✗ bilingual HTML: {len(r.fails)} error(s)", file=sys.stderr)
        return 1
    n = len(routemap.route_keys()) * len(routemap.languages())
    print(f"✓ bilingual HTML OK ({n} pages: canonical, hreflang, lang, no runtime i18n)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
