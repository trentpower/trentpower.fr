#!/usr/bin/env python3
"""validate_no_dated_assets.py — block dated+hashed CSS/JS in active public.

Every active asset on the live tree must carry its cache-busting
metadata in a `?v=YYYY-MM-DD.<shorthash>` query string, not baked
into the filename itself. The two outliers that historically used a
dated filename (`fonts-full.<edition>.<hash>.css` and
`verify/verification-data.<edition>.<hash>.js`) have been retired in
favour of clean stable filenames + query-string versioning; this
validator is the gate that keeps the active tree from drifting back.

Scope
-----
Walks `public/` and FAILS on any path matching:

    re.compile(r"\\.(?P<date>\\d{4}-\\d{2}-\\d{2})\\.(?P<hash>[0-9a-f]{4,})\\.(css|js)$")

Excluded: `public/integrity/releases/` — frozen historical release
bodies legitimately contain dated assets; their immutability is
gated by the "frozen-archive immutability" check.

Acceptance: green only when every active CSS/JS in `public/` has a
clean filename. Registered in tools/lib/checks.py (blocking tier,
after "ASSET_VERSION coherence"), and runnable standalone:

    python3 tools/validate_no_dated_assets.py

Exit 0 = clean active tree.
Exit 1 = at least one dated asset on disk outside the frozen-archive
exemption; offending paths are printed with their matched date+hash.
"""

from __future__ import annotations

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
from paths import PUBLIC_DIR as ROOT  # noqa: E402

# the dated+hashed shape the refactor eliminated. matches
# `<anything>.YYYY-MM-DD.<shorthash>.css|js`. shorthash is hex,
# at least 4 chars (cover both 8-char and longer hashes).
_DATED_ASSET_RE = re.compile(r"\.(?P<date>\d{4}-\d{2}-\d{2})\.(?P<hash>[0-9a-f]{4,})\.(css|js)$")

# frozen-archive exemption — these bodies are sealed historical
# snapshots and legitimately ship the dated filenames that were
# in use when the edition was sealed. their immutability is enforced
# by a separate predeploy stage.
EXCLUDE_PREFIX = "integrity/releases/"


def validate_no_dated_assets() -> tuple[int, int]:
    """Walk public/ and return (error_count, warning_count).

    Errors: every dated+hashed CSS/JS path outside the frozen-archive
    exemption. Warnings: none (this gate is binary).
    """
    fails: list[str] = []
    if not ROOT.is_dir():
        print(f"  FAIL: {ROOT} not a directory")
        return 1, 0
    for fp in sorted(ROOT.rglob("*")):
        if not fp.is_file():
            continue
        rel = fp.relative_to(ROOT).as_posix()
        if rel.startswith(EXCLUDE_PREFIX):
            continue
        m = _DATED_ASSET_RE.search(rel)
        if m:
            fails.append(f"{rel} (matched date={m.group('date')} hash={m.group('hash')})")

    if fails:
        print(f"  FAIL: {len(fails)} dated CSS/JS asset(s) in active public tree:")
        for f in fails:
            print(f"    {f}")
        print(
            "       these filenames must converge on the clean-name + "
            "?v=YYYY-MM-DD.<hash> pattern; run "
            "tools/prune_legacy_versioned_assets.py to clear stale files."
        )
        return len(fails), 0
    print("  OK: no dated CSS/JS in active public tree (frozen archives exempt)")
    return 0, 0


def main() -> int:
    errors, _warnings = validate_no_dated_assets()
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
