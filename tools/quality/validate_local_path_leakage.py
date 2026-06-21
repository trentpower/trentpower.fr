#!/usr/bin/env python3
"""validate_local_path_leakage.py — no host-internal paths in public bytes.

Scans the public tree for /home/, Desktop/, htdocs/htdocs or the gandi
instance's /srv/data/web/vhosts/ server paths — anything that would leak the
build host's filesystem into shipped bytes.

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the scan runs over a fixture repo with no monkeypatching.
`evaluate(repo)` is the pure compute path returning a Result; `main()` is the
only adapter that prints/exits. Byte-identical to the former
inline_checks.check_local_path_leakage.

Exit 0 = no leaks. Exit 1 = at least one host-internal path in a public file.
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

LEAK_PATTERNS = [
    re.compile(r"/home/trentpower/"),
    re.compile(r"\bDesktop/"),
    re.compile(r"htdocs/htdocs"),
    # Server-internal absolute paths from the gandi instance. anything matching
    # this in a public file is a leak — public-side .htaccess uses /htdocs/htdocs
    # to block requests to it (excluded below) but no public artefact has any
    # legitimate reason to mention /srv/data/web/vhosts/...
    re.compile(r"/srv/data/web/vhosts/"),
]
# glob list for the leak scan. the brief explicitly forbids
# /srv/data/web/vhosts/ leaks via .ini files (.user.ini was the original
# instance) so the scan includes config-shape extensions.
LEAK_GLOBS = [
    "*.html",
    "*.js",
    "*.css",
    "*.json",
    "*.txt",
    "*.ini",
    "*.conf",
    "*.yaml",
    "*.yml",
    "*.xml",
]
# keep "integrity/releases" excluded — frozen historical bytes that may
# legitimately contain the kind of strings the leak scan looks for.
LEAK_EXCLUDE_DIRS = {"integrity/releases", ".git"}
# the apache config (and its public mirror) intentionally references the stale
# /htdocs/htdocs/ path to block requests to it via redirectmatch. defensive,
# not a leak. skip the file.
LEAK_EXCLUDE_FILES = {"source/htaccess.txt"}


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


def _is_excluded(rel: str) -> bool:
    if rel in LEAK_EXCLUDE_FILES:
        return True
    return any(rel.startswith(d + "/") or rel == d for d in LEAK_EXCLUDE_DIRS)


def evaluate(repo: Repo) -> Result:
    r = Result()
    prefix = "public/"
    for glob in LEAK_GLOBS:
        for full in repo.glob(f"{prefix}**/{glob}"):
            rel = full[len(prefix) :]
            if _is_excluded(rel):
                continue
            try:
                text = repo.read(full)
            except UnicodeDecodeError:
                continue
            for line_num, line in enumerate(text.splitlines(), 1):
                for pat in LEAK_PATTERNS:
                    if pat.search(line):
                        r.fails.append(f"{rel}:{line_num} {pat.pattern} → {line.strip()[:100]}")
    return r


def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(repo)
    if r.fails:
        print(f"  FAIL: {len(r.fails)} local-path leak(s):")
        for f in r.fails:
            print(f"    {f}")
        return 1
    print("  OK: no local-path leaks in public tree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
