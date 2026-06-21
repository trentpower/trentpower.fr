#!/usr/bin/env python3
"""assert_seal_immutable.py — enforce the no-mutation-after-seal publication rule.

Once stage 04 seals the tree (the final generate_integrity.py hashes the bytes
the signature will cover), NO generator may mutate public bytes before stage 07
signs them — otherwise the signature signs bytes that differ from the sealed
manifest. The current build honours this by construction (stages 05–06 between
seal and sign are read-only), but nothing enforced it: add a mutating step there
and the signature would silently cover the wrong bytes.

Two modes, wired into build.sh around the seal→sign gap:
  --record   snapshot the whole public/ tree at end of stage 04, persist it.
  --verify   re-snapshot just before signing; FAIL (do not sign) if any file
             moved since the seal, naming what moved.

The compare logic (`moved_paths`) is pure and unit-tested; only main() does IO.
Reuses the same whole-tree content snapshot as the convergence work
(public_tree.snapshot_tree) so seal and sign hash the surface the same way.

Exit 0 = tree unchanged since seal (safe to sign). Exit 1 = moved (do not sign).
"""

from __future__ import annotations

import argparse
import json
import sys
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
from public_tree import snapshot_tree  # noqa: E402

# under the build scratch dir (.build/, gitignored). keyed off repo_root so the
# real build writes to REPO_ROOT/.build (== paths.TMP_DIR) while a test fixture
# gets its own isolated snapshot — no shared global state, no real-FS writes.
SNAPSHOT_REL = ".build/seal-snapshot.json"


def _snapshot_path(repo_root: Path) -> Path:
    return repo_root / SNAPSHOT_REL


def moved_paths(sealed: dict, current: dict) -> list[str]:
    """Pure compare: sorted list of rels that differ between the seal snapshot
    and the current one — added, removed, or content-changed."""
    return sorted(rel for rel in set(sealed) | set(current) if sealed.get(rel) != current.get(rel))


def record(repo_root: Path = REPO_ROOT) -> int:
    snap = snapshot_tree(repo_root / "public")
    out = _snapshot_path(repo_root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, sort_keys=True) + "\n", encoding="utf-8")
    print(f"  OK: sealed snapshot recorded ({len(snap)} files) -> {out.name}")
    return 0


def verify(repo_root: Path = REPO_ROOT) -> int:
    snap_path = _snapshot_path(repo_root)
    if not snap_path.is_file():
        print(f"  FAIL: no seal snapshot at {snap_path} — run --record after stage 04 seal")
        return 1
    sealed = json.loads(snap_path.read_text(encoding="utf-8"))
    current = snapshot_tree(repo_root / "public")
    moved = moved_paths(sealed, current)
    if not moved:
        print(f"  OK: public tree unchanged since seal ({len(current)} files) — safe to sign")
        return 0
    print(f"  FAIL: {len(moved)} file(s) MUTATED between seal and sign — DO NOT SIGN:")
    for rel in moved:
        state = "added" if rel not in sealed else "removed" if rel not in current else "changed"
        print(f"    {rel} ({state})")
    print(
        "       a generator ran after stage 04 seal; the signature would cover "
        "bytes that differ from the sealed manifest. Re-seal, do not sign."
    )
    return 1


def main(argv: list[str] | None = None, repo_root: Path = REPO_ROOT) -> int:
    ap = argparse.ArgumentParser(description="enforce no-mutation-after-seal")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--record", action="store_true", help="snapshot the sealed tree")
    group.add_argument("--verify", action="store_true", help="assert no change since seal")
    args = ap.parse_args(argv)
    return record(repo_root) if args.record else verify(repo_root)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
