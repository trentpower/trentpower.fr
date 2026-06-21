#!/usr/bin/env python3
"""validate_source_mirror_readability.py — confirm /source/ asset
mirrors expose readable authored source rather than minified bytes.

The /source/ surface is a public editorial transparency mirror. The
six asset mirrors below are the operator's authored source, lightly
banner-prefixed. This gate fails the build if any of them looks
minified (≤ 5 lines) or is missing the "authored source" banner on
its first line.

Quiet on success, precise on failure.

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the whole gate runs over a fixture repo with no monkeypatching.
`evaluate(repo)` is the pure compute path returning a Result; `main()` is the
only adapter that prints/exits. The check logic is byte-identical to the former
inline main(): same constants, same messages, same line-count and banner rules.
"""

from __future__ import annotations

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

# repo-root-relative location of the public /source/ mirror surface.
SOURCE_DIR_REL = "public/source"

REMAPPED_MIRRORS = [
    "styles.css.txt",
    "print.css.txt",
    "fonts-full.css.txt",
    "theme.js.txt",
    "sw-register.js.txt",
    "reveal.js.txt",
    "overlay.js.txt",
    "fonts.js.txt",
    "copy.js.txt",
    "verify-modal.js.txt",
]

MIN_LINES = 6  # ≤ 5 strongly suggests minified / single-line content
BANNER_FRAGMENT = "authored source"


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    oks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


def evaluate(repo: Repo) -> Result:
    r = Result()
    source_dir = repo.root / SOURCE_DIR_REL
    if not source_dir.is_dir():
        r.fails.append(f"DIRMISSING:/source/ directory not found at {source_dir}")
        return r
    failures: list[str] = []
    for name in REMAPPED_MIRRORS:
        rel = f"{SOURCE_DIR_REL}/{name}"
        if not repo.is_file(rel):
            failures.append(f"{name} missing")
            continue
        text = (source_dir / name).read_text(encoding="utf-8", errors="replace")
        line_count = text.count("\n") + (0 if text.endswith("\n") else 1)
        first_line = text.split("\n", 1)[0]
        if line_count < MIN_LINES:
            failures.append(
                f"{name} has {line_count} line(s) — likely minified, expected readable authored source"
            )
            continue
        if BANNER_FRAGMENT not in first_line:
            failures.append(f"{name} first line missing 'authored source' banner: {first_line!r}")
    r.fails.extend(failures)
    if not failures:
        r.oks.append(
            f"source-mirror-readability — {len(REMAPPED_MIRRORS)} asset mirrors expose readable authored source"
        )
    return r


def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(repo)

    # the directory-missing case is a single top-level FAIL line, not the
    # itemised "N issue(s)" block; carried as a sentinel-prefixed fail.
    if r.fails and r.fails[0].startswith("DIRMISSING:"):
        print(f"FAIL: {r.fails[0][len('DIRMISSING:'):]}")
        return 1
    if r.fails:
        print(f"  FAIL: source-mirror-readability — {len(r.fails)} issue(s):")
        for f in r.fails:
            print(f"    {f}")
        return 1
    for line in r.oks:
        print(f"  OK: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
