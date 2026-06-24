#!/usr/bin/env python3
"""validate_archive_storage_policy.py — no archive binaries committed to git.

Historical edition archive binaries (trentpower-fr-<edition>.zip / .tar.gz) are
server-canonical: the live host at https://trentpower.fr/integrity/releases/ is
their store. Git keeps only the lightweight verification record (the .sha256
checksums, the .sig signatures and the manifests). A release build still writes
the binaries to public/integrity/releases/<edition>/ on disk at ship time — the
deploy mirror uploads them from there — but they are .gitignore'd and must never
be committed, or the repository (and every GitHub source download) re-bloats.

This gate is the guardrail that keeps them out. It inspects the set of files
GIT TRACKS (not the working tree — the on-disk binaries after a build are
expected and gitignored), and fails if any tracked path under
public/integrity/releases/ is an archive binary.

Shape (deep module, small interface). The injected seam is the list of
git-tracked paths, so `evaluate(tracked)` is a pure function over a plain list
and `main()` is the only adapter that shells out to git and prints/exits.

Exit 0 = no archive binaries tracked. Exit 1 = at least one is committed.
"""

from __future__ import annotations

import re
import subprocess
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

# archive-binary extensions forbidden under the release tree. the .sha256 / .sig
# sidecars end in those suffixes (not these), so they are never matched.
FORBIDDEN_RE = re.compile(r"^public/integrity/releases/.+\.(?:zip|tar\.gz|tgz|tar|7z|br)$")


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


def evaluate(tracked_paths: list[str]) -> Result:
    r = Result()
    for p in tracked_paths:
        if FORBIDDEN_RE.match(p):
            r.fails.append(p)
    return r


def _git_tracked(repo_root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "public/integrity/releases"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [ln for ln in out.stdout.splitlines() if ln]


def main(repo_root: Path = REPO_ROOT, *, tracked: list[str] | None = None) -> int:
    # `tracked` is an injected seam: tests pass a plain list so main()'s
    # reporting/exit paths are exercised without a real git subprocess (the
    # fast tier blocks subprocess). Production passes nothing -> reads git.
    paths = _git_tracked(repo_root) if tracked is None else tracked
    r = evaluate(paths)
    if r.fails:
        print(f"  FAIL: {len(r.fails)} archive binary(ies) committed to git:")
        for f in r.fails[:20]:
            print(f"    {f}")
        if len(r.fails) > 20:
            print(f"    ... and {len(r.fails) - 20} more")
        print("       archives are server-canonical — they must not enter git.")
        print("       see public/integrity/releases/README.md + .gitignore")
        return 1
    print("  OK: no archive binaries committed — releases store is server-canonical")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
