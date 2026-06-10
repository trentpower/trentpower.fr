#!/usr/bin/env python3
"""validate_lowercase_comments.py — enforce the lowercase-comments
authorial rule.

scans every authored source file in scope (same target list as
fix_lowercase_comments.py) and flags comment regions that still
contain uppercase prose. each violation reports file:line + the
offending comment snippet.

exits 0 on a clean tree; non-zero on any violation. registered in
tools/lib/checks.py (advisory tier).

scope, preserve heuristic, and exclusions match
fix_lowercase_comments.py byte-for-byte (same TARGETS list, same
_is_preserve_token + _lower_prose imports). public/changelog.txt
is grandfathered (phase 1-18 history sealed); the validator
does not scan it.
"""

from __future__ import annotations

import sys

# delegate to the fix script's logic. import the module from the
# same tools/ directory so we get one source of truth for tokens.
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
from fix_lowercase_comments import (  # noqa: E402
    HANDLERS,
    ROOT,
    TARGETS,
)


def main() -> int:
    fails: list[str] = []
    files_scanned = 0
    files_with_diff = 0
    for kind, paths in TARGETS:
        handler = HANDLERS[kind]
        for rel in paths:
            p = ROOT / rel
            if not p.is_file():
                continue
            files_scanned += 1
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            new, changed = handler(text)
            if changed > 0 and new != text:
                files_with_diff += 1
                # locate the lines where the source and fixed text differ
                # for a more helpful error message
                src_lines = text.splitlines()
                new_lines = new.splitlines()
                for ln, (src_line, new_line) in enumerate(
                    zip(src_lines, new_lines, strict=False), start=1
                ):
                    if src_line != new_line:
                        # report only the first 3 violations per file to
                        # keep the validator output scannable
                        if sum(1 for f in fails if f.startswith(f"{rel}:")) >= 3:
                            break
                        fails.append(
                            f"{rel}:{ln}: uppercase comment prose — {src_line.strip()[:120]}"
                        )

    if fails:
        print(
            f"FAIL: {len(fails)} lowercase-comments violation(s) in "
            f"{files_with_diff}/{files_scanned} file(s):",
            file=sys.stderr,
        )
        for f in fails[:30]:
            print(f"  ✗ {f}", file=sys.stderr)
        if len(fails) > 30:
            print(f"  … and {len(fails) - 30} more", file=sys.stderr)
        print(
            "",
            "run: python3 tools/fix_lowercase_comments.py",
            "to auto-fix in place. preserves paths, urls, identifiers,",
            "hex hashes, css variables, and python warning words "
            "(IMPORTANT NOTE TODO WARNING FIXME XXX HACK).",
            sep="\n",
            file=sys.stderr,
        )
        return 1
    print(f"OK: lowercase-comments — {files_scanned} file(s) scanned; all comment prose lowercase")
    return 0


if __name__ == "__main__":
    sys.exit(main())
