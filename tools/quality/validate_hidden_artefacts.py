#!/usr/bin/env python3
"""validate_hidden_artefacts.py — fail on hidden host artefacts in the public
tree and on font binaries / stale stylesheets inside the newest release ZIP.

Covers the classes of file the hardening spec calls out as build-fail triggers:
hidden host artefacts (.DS_Store, .env, Thumbs.db, swap files, sqlite DBs, key
material, lockfiles), forbidden directories under public/, and font binaries
that must never ship inside a date-precision release ZIP. Existing checks
(local-path leakage, frozen-archive immutability) cover different surfaces.

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)`. The directory and ZIP walks the scan needs are not file-globs (the
Repo primitives filter directories out), so they run through `repo.root`, which
is exactly what a fixture repo provides — no monkeypatching. `evaluate(repo)` is
the compute path; `main()` is the only adapter that prints/exits. Byte-identical
to the former inline_checks.check_hidden_and_archive_safety.

Exit 0 = clean. Exit 1 = a hidden artefact, forbidden directory, or a banned
file inside the newest release ZIP.
"""

from __future__ import annotations

import re
import sys
import zipfile
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

# hidden host artefacts + secret-material globs. mirrors the brief's "forbidden
# public files"; any addition there should be reflected here.
HIDDEN_GLOBS = [
    ".DS_Store",
    ".env",
    ".env.*",
    "Thumbs.db",
    "*.swp",
    "*.sqlite",
    "*.db",
    "*.log",
    "*.bak",
    "*.tmp",
    "id_ed25519",
    "id_ed25519.pub",
    "*.totp_key",
    "*-key.txt",
    ".htpasswd",
    "composer.json",
    "composer.lock",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
]
# the local-path leakage scan already excludes these; mirror that here.
HIDDEN_SKIP_PREFIXES = ("_audit", "_rollback", "_archives", "_licences")
# forbidden directories that should never appear inside public/.
FORBIDDEN_DIRS = ["console_data", "node_modules", ".git", "private"]


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


def evaluate(repo: Repo) -> Result:
    r = Result()
    public = repo.root / "public"

    # 1. hidden host artefacts + secret-material globs anywhere in the tree.
    for glob in HIDDEN_GLOBS:
        for p in public.rglob(glob):
            if not p.is_file():
                continue
            rel = p.relative_to(public).as_posix()
            if rel.startswith(HIDDEN_SKIP_PREFIXES):
                continue
            r.fails.append(f"hidden artefact: {rel}")

    # the brief's .user.ini policy: must not appear in public/.
    if (public / ".user.ini").exists():
        r.fails.append(
            ".user.ini present in public/ — move directives to "
            "tools/server/user.ini.example; the server-side file is "
            "preserved by --no-delete mirror semantics."
        )

    # forbidden directories under public/.
    for d in FORBIDDEN_DIRS:
        for p in public.rglob(d):
            if p.is_dir():
                r.fails.append(
                    f"forbidden directory under public/: {p.relative_to(public).as_posix()}"
                )

    for p in public.rglob("__MACOSX"):
        if p.is_dir():
            r.fails.append(f"hidden artefact dir: {p.relative_to(public).as_posix()}")

    # 2. font binaries / stale stylesheets inside the newest date-precision
    # release zip. the packager already excludes them by extension, but the gate
    # verifies the artefact on disk so a packager regression cannot ship.
    rel_root = public / "integrity" / "releases"
    if rel_root.is_dir():
        for child in sorted(rel_root.iterdir(), reverse=True):
            if not child.is_dir():
                continue
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", child.name):
                continue
            for zp in sorted(child.glob("trentpower-fr-*.zip")):
                try:
                    with zipfile.ZipFile(zp) as zf:
                        for entry in zf.namelist():
                            low = entry.lower()
                            if low.endswith((".woff", ".woff2", ".otf", ".ttf")):
                                r.fails.append(f"font binary inside {zp.name}: {entry}")
                            if low.endswith("styles.v") or "/styles.v" in low:
                                r.fails.append(f"stale stylesheet inside {zp.name}: {entry}")
                except Exception as e:  # noqa: BLE001 — an unreadable zip is itself a finding
                    r.fails.append(f"could not read {zp.name}: {e}")
            break  # only the newest date-precision folder
    return r


def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(repo)
    if r.fails:
        print(f"  FAIL: {len(r.fails)} hidden/archive issue(s):")
        for f in r.fails:
            print(f"    {f}")
        print("       Remediation: delete the offending file(s) or fix the packager.")
        return 1
    print("  OK: no hidden artefacts; release ZIP free of fonts and stale stylesheets")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
