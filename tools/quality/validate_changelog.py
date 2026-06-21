#!/usr/bin/env python3
"""validate_changelog.py — the canonical edition must not advance past the
topmost changelog entry's date.

Edition bumps are deliberate; if the edition is newer than the newest changelog
entry, an editorial entry is owed before the build can ship (raw material in
reports/changelog-draft.txt).

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the whole gate runs over a fixture repo with no monkeypatching.
`load(repo)` reads the two inputs; `evaluate(ctx)` is pure (it parses + compares,
catching a malformed changelog as a warning, never raising); `main()` is the
only adapter that prints and exits. Behaviour is byte-identical to the former
inline_checks.check_changelog_freshness.

Exit 0 = edition <= topmost changelog entry (or inputs absent — skip).
Exit 1 = edition is newer than the topmost changelog entry.
"""

from __future__ import annotations

import json
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

CHANGELOG_REL = "public/changelog.txt"
IDENTITY_CANONICAL_REL = "tools/config/identity_canonical.json"

_TOP_ENTRY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\b", re.MULTILINE)


@dataclass(frozen=True)
class Ctx:
    present: bool  # both inputs exist
    changelog_text: str
    canon_text: str


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    oks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


def load(repo: Repo) -> Ctx:
    present = repo.is_file(CHANGELOG_REL) and repo.is_file(IDENTITY_CANONICAL_REL)
    return Ctx(
        present=present,
        changelog_text=repo.read(CHANGELOG_REL),
        canon_text=repo.read(IDENTITY_CANONICAL_REL),
    )


def evaluate(ctx: Ctx) -> Result:
    r = Result()
    if not ctx.present:
        # inputs absent — nothing to assert (mirrors the inline skip-and-pass).
        return r
    try:
        ed = json.loads(ctx.canon_text).get("edition", "") if ctx.canon_text else ""
        top_match = _TOP_ENTRY_RE.search(ctx.changelog_text)
        top = top_match.group(1) if top_match else ""
        if ed and top and ed > top:
            r.fails.append(
                f"changelog freshness — canonical edition {ed} "
                f"is newer than the topmost changelog entry ({top}). "
                f"Add an entry to public/changelog.txt; raw diff at "
                f"reports/changelog-draft.txt."
            )
        elif ed and top:
            relation = "matches" if top == ed else f"ahead of (>= {ed})"
            r.oks.append(f"changelog top entry {top} {relation} edition {ed}")
    except Exception as _e:  # noqa: BLE001 — parse failure is a warning, never fatal
        r.warns.append(f"changelog freshness check did not complete ({_e})")
    return r


def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(load(repo))
    for line in r.oks:
        print(f"  OK: {line}")
    for line in r.warns:
        print(f"  WARN: {line}")
    for line in r.fails:
        print(f"  FAIL: {line}")
    return 1 if r.fails else 0


if __name__ == "__main__":
    sys.exit(main())
