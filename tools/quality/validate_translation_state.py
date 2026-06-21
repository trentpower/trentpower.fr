#!/usr/bin/env python3
"""validate_translation_state.py — content/fr/ translation freshness gate.

Every content/fr/pages/*.yml must carry a translation: block recording the
English source it tracks and a review status. This validator checks:

  · the block exists and has source_page / source_hash / status / updated
  · status is one of draft | machine-assisted | human-reviewed
  · source_hash still matches the current content/en source (stale FR copy)

In --release mode a draft or stale translation fails the build; otherwise
it is a warning (dev inner loop).

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the whole gate runs over a fixture repo with no monkeypatching.
`load(repo)` enumerates the fr/en page bytes; `evaluate(ctx, release)` is pure (it
hashes + compares, accumulating fails/warns into a Result); `main()` is the only
adapter that prints and exits. Behaviour is byte-identical to the former inline
main(): a stale source_hash is a warning in dev (RC 0) and a fail under --release.

Usage:
    python3 tools/quality/validate_translation_state.py            # warn
    python3 tools/quality/validate_translation_state.py --release  # fail on draft/stale

Exit 0 = every fr page carries a valid, fresh translation block (or warnings only).
Exit 1 = a missing/invalid block, or (under --release) a draft/stale translation.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML required", file=sys.stderr)
    sys.exit(2)

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
from hashing import sha256_hex  # noqa: E402
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

VALID_STATUS = {"draft", "machine-assisted", "human-reviewed"}
RELEASE_OK = {"human-reviewed"}

# repo-relative content locations (resolved through the Repo seam).
FR_PAGES_GLOB = "content/fr/pages/*.yml"
EN_PAGES_DIR_REL = "content/en/pages"


# ---------------------------------------------------------------------------
# Ctx / Result — the values that flow through the interface. load() produces
# Ctx; evaluate() produces Result; main() renders it. tests assert on Result,
# never on stdout.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Ctx:
    # fr-page rels (repo-relative posix) in sorted order, paired with their text.
    fr_pages: list[tuple[str, str]]
    # repo seam, so evaluate can read the matching en source per page.
    repo: Repo


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    oks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


def _en_source_hash(repo: Repo, page_name: str) -> str | None:
    en_rel = f"{EN_PAGES_DIR_REL}/{page_name}.yml"
    if repo.is_file(en_rel):
        return "sha256-" + sha256_hex(repo.read(en_rel).encode("utf-8"))
    return None


# ---------------------------------------------------------------------------
# load — read the inputs through the Repo seam. never prints/exits.
# ---------------------------------------------------------------------------
def load(repo: Repo) -> Ctx:
    fr_pages = [(rel, repo.read(rel)) for rel in repo.glob(FR_PAGES_GLOB)]
    return Ctx(fr_pages=fr_pages, repo=repo)


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo (carried on Ctx). this is the test surface.
# ---------------------------------------------------------------------------
def evaluate(ctx: Ctx, release: bool = False) -> Result:
    r = Result()
    if not ctx.fr_pages:
        r.fails.append("no content/fr/pages/*.yml found")
        return r

    for rel, text in ctx.fr_pages:
        data = yaml.safe_load(text) or {}
        tr = data.get("translation")
        if not isinstance(tr, dict):
            r.fails.append(f"{rel}: missing translation: block")
            continue
        for field_name in ("source_page", "source_hash", "status", "updated"):
            if field_name not in tr:
                r.fails.append(f"{rel}: translation.{field_name} missing")
        status = tr.get("status")
        if status not in VALID_STATUS:
            r.fails.append(f"{rel}: invalid status {status!r}")
        current = _en_source_hash(ctx.repo, tr.get("source_page", ""))
        stale = current is not None and current != tr.get("source_hash")
        if stale:
            msg = f"{rel}: source_hash stale — EN source changed since translation"
            (r.fails if release else r.warns).append(msg)
        if release and status not in RELEASE_OK:
            r.fails.append(
                f"{rel}: status {status!r} not release-ready (need human-reviewed)"
            )

    if not r.fails:
        r.oks.append(
            f"translation state OK ({len(ctx.fr_pages)} fr pages"
            + (f", {len(r.warns)} warning(s)" if r.warns else "")
            + ")"
        )
    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. loads, evaluates, renders, returns exit
# code. the only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    release = "--release" in sys.argv
    repo = Repo(repo_root)
    r = evaluate(load(repo), release=release)

    for w in r.warns:
        print(f"  ⚠ {w}")
    for e in r.fails:
        print(f"  ✗ {e}", file=sys.stderr)
    if r.fails:
        print(f"\n✗ translation state: {len(r.fails)} error(s)", file=sys.stderr)
        return 1
    for line in r.oks:
        print(f"✓ {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
