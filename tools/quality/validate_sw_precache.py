#!/usr/bin/env python3
"""validate_sw_precache.py — every URL in sw.js's precache lists maps to a real
file on disk with an allowed content-type.

Catches the silent-install class — a precache URL that 404s on the server (or is
missing locally) fails install in the browser without naming itself; this gate
names it before anything ships.

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the gate runs over a fixture repo (sw.js + the referenced
files) with no monkeypatching. `evaluate(repo)` is the compute path returning a
Result; `main()` is the only adapter that prints/exits. Byte-identical to the
former inline_checks.check_sw_precache.

Exit 0 = every precache URL resolves to a real file of a valid type.
Exit 1 = sw.js missing/malformed, or a precache URL does not resolve.
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

SW_REL = "public/sw.js"

# allowed file extensions in the precache list. anything else fails.
_PRECACHE_EXT_OK = {
    ".html",
    ".css",
    ".js",
    ".woff2",
    ".svg",
    ".png",
    ".ico",
    ".json",
    ".webmanifest",
}


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    count: int = 0
    sw_missing: bool = False
    literals_missing: bool = False
    empty: bool = False

    @property
    def ok(self) -> bool:
        return not (self.fails or self.sw_missing or self.literals_missing or self.empty)


def evaluate(repo: Repo) -> Result:
    if not repo.is_file(SW_REL):
        return Result(sw_missing=True)
    text = repo.read(SW_REL)
    # the two-tier split gives sw.js separate CRITICAL_PRECACHE + OPTIONAL_PRECACHE
    # literals plus a derived precache = CRITICAL_PRECACHE.concat(OPTIONAL_PRECACHE).
    # read both arrays and treat their union as the surface to validate.
    crit_m = re.search(r"var CRITICAL_PRECACHE = \[(.*?)\];", text, re.S)
    opt_m = re.search(r"var OPTIONAL_PRECACHE = \[(.*?)\];", text, re.S)
    if not (crit_m and opt_m):
        return Result(literals_missing=True)
    entries = re.findall(r"'([^']+)'", crit_m.group(1)) + re.findall(r"'([^']+)'", opt_m.group(1))
    if not entries:
        return Result(empty=True)

    r = Result(count=len(entries))
    for url in entries:
        if not url.startswith("/"):
            r.fails.append(f"{url}: not server-rooted (must start with '/')")
            continue
        # map url → on-disk path (public-relative).
        if url == "/":
            disk_rel = "index.html"
        elif url.endswith("/"):
            disk_rel = url.lstrip("/") + "index.html"
        else:
            disk_rel = url.lstrip("/")
        if not repo.is_file(f"public/{disk_rel}"):
            r.fails.append(f"{url}: missing on disk ({disk_rel})")
            continue
        # extension allowlist — sanity for content-type.
        ext = "." + disk_rel.rsplit(".", 1)[-1].lower() if "." in disk_rel else ""
        if ext not in _PRECACHE_EXT_OK:
            r.fails.append(f"{url}: extension {ext or '(none)'} not in allowed precache type set")
    return r


def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(repo)
    if r.sw_missing:
        print("  FAIL: sw.js missing — run generate_sw.py")
        return 1
    if r.literals_missing:
        print("  FAIL: sw.js missing CRITICAL_PRECACHE / OPTIONAL_PRECACHE literals")
        return 1
    if r.empty:
        print("  FAIL: sw.js precache list is empty")
        return 1
    if r.fails:
        print(f"  FAIL: {len(r.fails)} precache issue(s):")
        for f in r.fails[:30]:
            print(f"    {f}")
        if len(r.fails) > 30:
            print(f"    … and {len(r.fails) - 30} more")
        return 1
    print(f"  OK: sw.js PRECACHE — {r.count} URL(s) resolve to disk")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
