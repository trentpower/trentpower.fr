#!/usr/bin/env python3
"""validate_lowercase_comments.py — enforce the lowercase-comments
authorial rule.

scans every authored source file in scope (same target list as
fix_lowercase_comments.py) and flags comment regions that still
contain uppercase prose. each violation reports file:line + the
offending comment snippet.

exits 0 on a clean tree; non-zero on any violation. registered in
tools/lib/checks.py (advisory tier).

scope, preserve heuristic, and exclusions match
fix_lowercase_comments.py byte-for-byte (same TARGETS list, same
_is_preserve_token + _lower_prose imports). public/changelog.txt
is grandfathered (phase 1-18 history sealed); the validator
does not scan it.

Shape (deep module, small interface). The external interface is `main() -> int`
plus the FAIL/OK text contract. Internally the filesystem is the injected
`Repo(root)` seam — the same authored-source scan set, but enumerated and read
through Repo — so the whole gate runs through `evaluate(repo) -> Result` over a
fixture repo with no monkeypatching. Compute (`evaluate`) is separate from render
(`main`): the former returns a Result and never prints or exits; the latter is
the only side-effecting adapter. Behaviour is byte-identical to the former
ROOT/TARGETS inline scan.
"""

from __future__ import annotations

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

# delegate to the fix script's logic. import the module from the same
# tools/quality/ directory so we get one source of truth for the comment
# handlers and the curated target list. the py target glob is re-derived
# below against the Repo seam so the scan honours a fixture root, but the
# selection rule (pillars + skip set) matches fix_lowercase_comments.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fix_lowercase_comments import (  # noqa: E402
    HANDLERS,
    TARGETS,
)

# the responsibility pillars + self-reference skip set the py target glob uses,
# lifted verbatim from fix_lowercase_comments.py so the scan set is identical.
_PY_PILLARS = {"build", "quality", "verify", "release", "lib"}
_PY_SKIP = {"fix_lowercase_comments.py", "validate_lowercase_comments.py"}


# named accessor over the shared Repo seam. the authored-source scan set (the
# curated TARGETS lists + the tools/*/*.py glob rule) lives here in the
# validator, not on Repo — Repo stays a pure adapter.
def _scan_targets(repo: Repo) -> list[tuple[str, str]]:
    """(kind, repo-relative-path) pairs in the exact order the original
    ROOT/TARGETS loop visited them. non-py kinds reuse the curated TARGETS
    lists; the py kind is re-globbed through Repo with the same pillar/skip
    filter fix_lowercase_comments.py applies."""
    out: list[tuple[str, str]] = []
    for kind, paths in TARGETS:
        if kind == "py":
            for rel in sorted(
                p
                for p in repo.glob("tools/*/*.py")
                if p.split("/")[-2] in _PY_PILLARS
                and p.split("/")[-1] not in _PY_SKIP
            ):
                out.append((kind, rel))
        else:
            for rel in paths:
                out.append((kind, rel))
    return out


# ---------------------------------------------------------------------------
# Result — the value that flows through the interface. evaluate() produces it;
# main() renders it. tests assert on Result, never on stdout.
# ---------------------------------------------------------------------------
@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    files_scanned: int = 0
    files_with_diff: int = 0

    @property
    def ok(self) -> bool:
        return not self.fails


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo. this is the test surface.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo) -> Result:
    r = Result()
    for kind, rel in _scan_targets(repo):
        handler = HANDLERS[kind]
        if not repo.is_file(rel):
            continue
        r.files_scanned += 1
        try:
            text = repo.read(rel)
        except UnicodeDecodeError:
            continue
        new, changed = handler(text)
        if changed > 0 and new != text:
            r.files_with_diff += 1
            # locate the lines where the source and fixed text differ
            # for a more helpful error message
            src_lines = text.splitlines()
            new_lines = new.splitlines()
            for ln, (src_line, new_line) in enumerate(
                zip(src_lines, new_lines, strict=False), start=1
            ):
                if src_line != new_line:
                    # report only the first 3 violations per file to
                    # keep the validator output scannable
                    if sum(1 for f in r.fails if f.startswith(f"{rel}:")) >= 3:
                        break
                    r.fails.append(
                        f"{rel}:{ln}: uppercase comment prose — {src_line.strip()[:120]}"
                    )
    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. evaluates, renders, returns exit code.
# the only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(repo)

    if r.fails:
        print(
            f"FAIL: {len(r.fails)} lowercase-comments violation(s) in "
            f"{r.files_with_diff}/{r.files_scanned} file(s):",
            file=sys.stderr,
        )
        for f in r.fails[:30]:
            print(f"  ✗ {f}", file=sys.stderr)
        if len(r.fails) > 30:
            print(f"  … and {len(r.fails) - 30} more", file=sys.stderr)
        print(
            "",
            "run: python3 tools/fix_lowercase_comments.py",
            "to auto-fix in place. preserves paths, urls, identifiers,",
            "hex hashes, css variables, and python warning words "
            "(IMPORTANT NOTE TODO WARNING FIXME XXX HACK).",
            sep="\n",
            file=sys.stderr,
        )
        return 1
    print(
        f"OK: lowercase-comments — {r.files_scanned} file(s) scanned; "
        "all comment prose lowercase"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
