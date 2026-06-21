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

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the whole gate runs over a fixture repo with no monkeypatching.
`evaluate(repo)` is the pure compute path returning a Result; `main()` is the
only adapter that prints/exits. Behaviour is byte-identical to the former
inline validate_no_dated_assets().
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
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

# the dated+hashed shape the refactor eliminated. matches
# `<anything>.YYYY-MM-DD.<shorthash>.css|js`. shorthash is hex,
# at least 4 chars (cover both 8-char and longer hashes).
_DATED_ASSET_RE = re.compile(r"\.(?P<date>\d{4}-\d{2}-\d{2})\.(?P<hash>[0-9a-f]{4,})\.(css|js)$")

# frozen-archive exemption — these bodies are sealed historical
# snapshots and legitimately ship the dated filenames that were
# in use when the edition was sealed. their immutability is enforced
# by a separate predeploy stage.
EXCLUDE_PREFIX = "integrity/releases/"


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


def evaluate(repo: Repo) -> Result:
    """Walk public/ and accumulate every dated+hashed CSS/JS path outside the
    frozen-archive exemption into the Result. This gate is binary — no warnings.
    """
    r = Result()
    prefix = "public/"
    for full in repo.glob(f"{prefix}**/*"):
        rel = full[len(prefix) :]
        if rel.startswith(EXCLUDE_PREFIX):
            continue
        m = _DATED_ASSET_RE.search(rel)
        if m:
            r.fails.append(f"{rel} (matched date={m.group('date')} hash={m.group('hash')})")
    return r


def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    if not (repo_root / "public").is_dir():
        print(f"  FAIL: {repo_root / 'public'} not a directory")
        return 1
    r = evaluate(repo)
    if r.fails:
        print(f"  FAIL: {len(r.fails)} dated CSS/JS asset(s) in active public tree:")
        for f in r.fails:
            print(f"    {f}")
        print(
            "       these filenames must converge on the clean-name + "
            "?v=YYYY-MM-DD.<hash> pattern; run "
            "tools/prune_legacy_versioned_assets.py to clear stale files."
        )
        return 1
    print("  OK: no dated CSS/JS in active public tree (frozen archives exempt)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
