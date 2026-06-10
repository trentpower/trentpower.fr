#!/usr/bin/env python3
"""validate_source_mirror_readability.py — confirm /source/ asset
mirrors expose readable authored source rather than minified bytes.

The /source/ surface is a public editorial transparency mirror. The
six asset mirrors below are the operator's authored source, lightly
banner-prefixed. This gate fails the build if any of them looks
minified (≤ 5 lines) or is missing the "authored source" banner on
its first line.

Quiet on success, precise on failure.
"""

from __future__ import annotations

import pathlib
import sys

SOURCE_DIR = pathlib.Path(__file__).resolve().parents[2] / "public" / "source"

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


def main() -> int:
    if not SOURCE_DIR.is_dir():
        print(f"FAIL: /source/ directory not found at {SOURCE_DIR}")
        return 1
    failures: list[str] = []
    for name in REMAPPED_MIRRORS:
        path = SOURCE_DIR / name
        if not path.is_file():
            failures.append(f"{name} missing")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        line_count = text.count("\n") + (0 if text.endswith("\n") else 1)
        first_line = text.split("\n", 1)[0]
        if line_count < MIN_LINES:
            failures.append(
                f"{name} has {line_count} line(s) — likely minified, expected readable authored source"
            )
            continue
        if BANNER_FRAGMENT not in first_line:
            failures.append(f"{name} first line missing 'authored source' banner: {first_line!r}")
    if failures:
        print(f"  FAIL: source-mirror-readability — {len(failures)} issue(s):")
        for f in failures:
            print(f"    {f}")
        return 1
    print(
        f"  OK: source-mirror-readability — {len(REMAPPED_MIRRORS)} asset mirrors expose readable authored source"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
