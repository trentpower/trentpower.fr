"""tools/lib/repo.py — the filesystem evidence seam for the validator fleet.

A validator's job is evidence collection: read files, walk the tree, decide
whether a claim holds. `Repo` is the single injected seam that work crosses —
one root, three primitives (`read`, `is_file`, `glob`), everything resolved
relative to that root. The production adapter is `Repo(REPO_ROOT)`; a test
adapter is `Repo(tmp_fixture)`, so a validator's whole compute path runs over a
fixture repo with no monkeypatching.

This stays a PURE adapter. Domain-specific named accessors — "the release
workflow", "the active public HTML" — live in each validator, not here; the
exclusion policies and path knowledge are that validator's, and baking them in
would couple this seam to one caller. Two validators
(validate_claims_parity, validate_dates) agreed on exactly this surface before
it was extracted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Repo:
    root: Path

    def read(self, rel: str) -> str:
        """text of a repo-relative file, or "" if it does not exist."""
        p = self.root / rel
        return p.read_text(encoding="utf-8") if p.is_file() else ""

    def is_file(self, rel: str) -> bool:
        return (self.root / rel).is_file()

    def is_dir(self, rel: str) -> bool:
        """True iff a repo-relative path is a directory. The counterpart to
        is_file() for the few callers that probe a directory's presence
        (e.g. a `.git`/`node_modules` checkout marker) rather than a file's."""
        return (self.root / rel).is_dir()

    def size(self, rel: str) -> int:
        """on-disk byte size of a repo-relative file. callers guard with
        is_file() first; on a missing file this raises, like stat()."""
        return (self.root / rel).stat().st_size

    def glob(self, pattern: str) -> list[str]:
        """repo-relative posix paths of files matching a glob (supports `**`),
        sorted. directories are filtered out."""
        return sorted(
            p.relative_to(self.root).as_posix() for p in self.root.glob(pattern) if p.is_file()
        )
