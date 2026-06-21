#!/usr/bin/env python3
"""validate_integrity_sig.py — integrity.json.sig must not be older than
integrity.json.

If it is, the signature is for a previous state of the manifest — the operator
re-ran integrity but forgot to re-sign.

Shape (deep module, small interface). The filesystem is the injected seam —
`Repo(root)`. mtimes are a temporal property the `read`/`is_file`/`glob`
primitives do not expose, so `load(repo)` performs the two `stat` reads (the
impure step) and `evaluate(ctx)` is a pure comparison over the two floats — the
test surface needs only `os.utime` on a fixture, no clock or process mocking.
`main()` is the only adapter that prints/exits. Byte-identical to the former
inline_checks.check_integrity_sig_freshness.

Exit 0 = signature is current. Exit 1 = signature stale or an input missing.
"""

from __future__ import annotations

import datetime
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

MANIFEST_REL = "public/integrity.json"
SIG_REL = "public/integrity.json.sig"


@dataclass(frozen=True)
class Ctx:
    present: bool
    sig_mtime: float | None
    man_mtime: float | None


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    oks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


def load(repo: Repo) -> Ctx:
    present = repo.is_file(MANIFEST_REL) and repo.is_file(SIG_REL)
    if not present:
        return Ctx(present=False, sig_mtime=None, man_mtime=None)
    return Ctx(
        present=True,
        sig_mtime=(repo.root / SIG_REL).stat().st_mtime,
        man_mtime=(repo.root / MANIFEST_REL).stat().st_mtime,
    )


def evaluate(ctx: Ctx) -> Result:
    r = Result()
    if not ctx.present:
        r.fails.append("integrity.json or integrity.json.sig missing")
        return r
    # +1 second slack so a same-second regenerate-then-sign pair does not falsely
    # fail on filesystems with second-resolution mtimes.
    if ctx.sig_mtime + 1 < ctx.man_mtime:
        r.fails.append(
            f"integrity.json.sig is older than integrity.json "
            f"(sig {datetime.datetime.fromtimestamp(ctx.sig_mtime).isoformat()} "
            f"vs man {datetime.datetime.fromtimestamp(ctx.man_mtime).isoformat()}) — "
            f"re-sign with: gpg --batch --yes --detach-sign --armor "
            f"-o integrity.json.sig integrity.json"
        )
        return r
    r.oks.append("integrity.json.sig is current")
    return r


def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(load(repo))
    for line in r.oks:
        print(f"  OK: {line}")
    for line in r.fails:
        print(f"  FAIL: {line}")
    return 1 if r.fails else 0


if __name__ == "__main__":
    sys.exit(main())
