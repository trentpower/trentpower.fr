#!/usr/bin/env python3
"""validate_verification_data.py — shape gate for the Verify route map.

public/verify/verification-data.js is generated and read client-side by the
Verify page + modal. It is signed (listed in integrity.json), but nothing else
asserts that each record is *shaped, bounded and impossible to reinterpret* —
this validator does, as the new "publication-firewall" coverage that the
existing Python gate did not already provide.

For every record it enforces an allowlist:
  - path: absolute, on-site, no traversal / scheme / backslash
  - sha256 / source_sha256: look like sha256-<base64> (when present)
  - size_bytes: a positive int, <= 2 MB
  - edition / validated: YYYY-MM-DD
  - no duplicate record paths; key == record.path

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the whole gate runs over a fixture repo with no
monkeypatching. `load(repo)` reads + parses the one input (returning a Ctx or
errors); `evaluate(ctx)` is the pure compute path returning a Result and never
prints or exits; `main()` is the only adapter that prints and exits. Behaviour
is byte-identical to the former direct-PUBLIC_DIR implementation.

Exit 0 = clean. Exit 1 = a malformed record (build is blocked upstream of signing).
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

# repo-relative location of the one input (resolved through the Repo seam).
DATA_REL = "public/verify/verification-data.js"

_PATH = re.compile(r"^/[A-Za-z0-9._~/-]*$")  # absolute, on-site, no traversal chars
_SHA = re.compile(r"^sha256-[A-Za-z0-9+/]+=*$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_BYTES = 2_000_000


# ---------------------------------------------------------------------------
# Ctx / Result — the values that flow through the interface. load() produces
# Ctx (or errors); evaluate() produces Result; main() renders it. tests assert
# on Result, never on stdout.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Ctx:
    records: dict


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    oks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


def _check_record(key: str, rec: dict) -> list[str]:
    errs: list[str] = []

    def bad(msg: str) -> None:
        errs.append(f"{key}: {msg}")

    path = rec.get("path")
    if not isinstance(path, str) or not _PATH.match(path) or ".." in path:
        bad(f"unsafe or malformed path {path!r}")
    elif path != key:
        bad(f"record path {path!r} does not match its key {key!r}")

    for field_name in ("sha256", "source_sha256"):
        val = rec.get(field_name)
        if val not in (None, "") and (not isinstance(val, str) or not _SHA.match(val)):
            bad(f"{field_name} is not a valid sha256-<base64> value: {val!r}")

    size = rec.get("size_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0 or size > _MAX_BYTES:
        bad(f"size_bytes must be a positive int <= {_MAX_BYTES}: {size!r}")

    for field_name in ("edition", "validated"):
        val = rec.get(field_name)
        if not isinstance(val, str) or not _DATE.match(val):
            bad(f"{field_name} must be YYYY-MM-DD: {val!r}")

    return errs


# ---------------------------------------------------------------------------
# load — read + parse the input. returns (ctx, errors); never prints/exits.
# ---------------------------------------------------------------------------
def load(repo: Repo) -> tuple[Ctx | None, list[str]]:
    if not repo.is_file(DATA_REL):
        return None, [f"{repo.root / DATA_REL} not found"]
    text = repo.read(DATA_REL)
    try:
        m = re.search(r"window\.TP_VERIFICATION_MAP\s*=\s*(\{.*\})\s*;", text, re.S)
        if not m:
            raise ValueError("could not locate window.TP_VERIFICATION_MAP object")
        records = json.loads(m.group(1))
    except Exception as exc:  # noqa: BLE001
        return None, [f"could not parse verification-data.js ({exc})"]
    return Ctx(records=records), []


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the loaded Ctx.
# this is the test surface.
# ---------------------------------------------------------------------------
def evaluate(ctx: Ctx) -> Result:
    r = Result()
    seen: set[str] = set()
    for key, rec in ctx.records.items():
        if not isinstance(rec, dict):
            r.fails.append(f"{key}: record is not an object")
            continue
        if key in seen:
            r.fails.append(f"{key}: duplicate record path")
        seen.add(key)
        r.fails.extend(_check_record(key, rec))
    if r.ok:
        r.oks.append(f"verification-data.js — {len(ctx.records)} record(s) shaped + bounded")
    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. loads, evaluates, renders, returns exit
# code. the only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)

    ctx, errors = load(repo)
    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        return 1

    r = evaluate(ctx)

    if r.fails:
        print(f"  FAIL: {len(r.fails)} verification-data shape issue(s):")
        for e in r.fails[:40]:
            print(f"    ✗ {e}")
        return 1

    for line in r.oks:
        print(f"  OK: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
