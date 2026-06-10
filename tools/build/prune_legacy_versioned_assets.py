#!/usr/bin/env python3
"""prune_legacy_versioned_assets.py — delete dated+hashed CSS/JS drift.

The asset-versioning refactor converged `fonts-full.css` and
`verify/verification-data.js` onto the same clean-filename +
`?v=YYYY-MM-DD.<hash>` pattern as every other asset. Before the
refactor, each build emitted a dated copy alongside the clean alias
(`fonts-full.<edition>.<hash>.css`, `verification-data.<edition>.<hash>.js`)
and no pruner ever swept the older copies, so stale dated files
accumulated on disk.

This script implements the one-time cleanup of that accumulated
drift and runs on every build as a guard against regression. It is
bounded by an explicit allow-deletion glob list so it can never
delete authored content — anything that fails the bounded-pattern
check is refused even if a glob accidentally expands too broadly.

Allow-deletion globs (relative to `public/`):
    fonts-full.????-??-??.*.css
    verify/verification-data.????-??-??.*.js

Excluded path prefix:
    integrity/releases/   (frozen historical archives — never touched)

Usage:
    python3 tools/prune_legacy_versioned_assets.py            # delete + report
    python3 tools/prune_legacy_versioned_assets.py --dry-run  # list, don't delete
    python3 tools/prune_legacy_versioned_assets.py --verbose  # extra logging

Idempotent. Exits 0 on success (including no-op). Exits non-zero on
an unexpected error (e.g. a permission failure during deletion).
"""

from __future__ import annotations

import argparse
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
from paths import PUBLIC_DIR as ROOT  # noqa: E402

# allow-deletion globs (posix, relative to root). every candidate
# file MUST match one of these AND the bounded-pattern check below
# before it is eligible for deletion.
ALLOW_DELETION_GLOBS = (
    "fonts-full.????-??-??.*.css",
    "verify/verification-data.????-??-??.*.js",
)

# defensive bounded pattern: the same regex the validator uses to
# detect dated assets. a candidate path must match this even after
# passing the glob, so a malformed glob can never widen the blast
# radius into authored content.
_DATED_ASSET_RE = re.compile(r"\.(?P<date>\d{4}-\d{2}-\d{2})\.(?P<hash>[0-9a-f]{4,})\.(css|js)$")

# frozen-archive exemption — never touched by the pruner.
EXCLUDE_PREFIX = "integrity/releases/"


def _eligible_for_deletion(rel: str) -> bool:
    """True only if `rel` is in the bounded allow-list AND matches
    the dated-asset shape. Refuses anything under the frozen-archive
    prefix even if a glob accidentally matched it."""
    if rel.startswith(EXCLUDE_PREFIX):
        return False
    return bool(_DATED_ASSET_RE.search(rel))


def _candidates() -> list[pathlib.Path]:
    """Return every file under ROOT matching any allow-deletion glob,
    sorted for deterministic output."""
    seen: set[pathlib.Path] = set()
    for glob in ALLOW_DELETION_GLOBS:
        for fp in ROOT.glob(glob):
            if fp.is_file():
                seen.add(fp)
    return sorted(seen)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Prune dated+hashed legacy CSS/JS from active public/."
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="list what would be deleted; do not unlink",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="extra logging (lists scanned globs even on a clean tree)",
    )
    args = ap.parse_args()

    if not ROOT.is_dir():
        print(f"prune_legacy_versioned_assets: {ROOT} not a directory", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"  scanning {ROOT} for legacy versioned assets:")
        for glob in ALLOW_DELETION_GLOBS:
            print(f"    glob: {glob}")
        print(f"    exclude prefix: {EXCLUDE_PREFIX}")

    deleted = 0
    refused = 0
    errors: list[str] = []
    for fp in _candidates():
        rel = fp.relative_to(ROOT).as_posix()
        if not _eligible_for_deletion(rel):
            # defensive — glob expanded onto something that doesn't
            # match the bounded dated-asset shape OR sits inside the
            # frozen-archive prefix. refuse to act.
            refused += 1
            if args.verbose:
                print(f"  REFUSE: {rel} (failed bounded-pattern check)")
            continue
        if args.dry_run:
            print(f"  would delete: {rel}")
            deleted += 1
            continue
        try:
            fp.unlink()
        except OSError as e:
            errors.append(f"{rel}: {e}")
            continue
        print(f"  deleted: {rel}")
        deleted += 1

    if errors:
        print(f"  FAIL: {len(errors)} deletion error(s):", file=sys.stderr)
        for e in errors:
            print(f"    {e}", file=sys.stderr)
        return 1

    if deleted == 0:
        if args.verbose:
            print("  OK: no legacy versioned assets present (no-op)")
        else:
            print("  OK: no legacy versioned assets present")
    else:
        verb = "would delete" if args.dry_run else "deleted"
        print(
            f"  OK: {verb} {deleted} legacy versioned asset(s)"
            + (f"; refused {refused}" if refused else "")
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
