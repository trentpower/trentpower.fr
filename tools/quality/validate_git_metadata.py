#!/usr/bin/env python3
"""tools/quality/validate_git_metadata.py — git/repo metadata gate.

Scans the working tree for AI/model attribution metadata that does
not belong in committable bytes:

    Co-authored-by:    Generated-by:    AI-assisted-by:
    Assisted-by:       Prompt:          model-generated
    ai-generated       generated with Claude / ChatGPT
    Claude Code        ChatGPT          Anthropic         OpenAI

Per the canonical authorship position recorded in
docs/AUTHORSHIP-STATEMENT.md and humans.txt, AI/tool assistance
acknowledgement belongs in those documentation files only — never
in commit metadata, never in generated repo material, never in
release notes or changelogs, never in source mirrors.

The gate refuses the build if any forbidden pattern appears in
publishable working-tree files. Git history is not scanned here —
historical attribution is a separate report-only concern documented
in reports/historical-commit-attribution-report.txt.

Exit 0 = green; exit 1 = block.

Registered in tools/lib/checks.py (blocking tier).

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the scan runs over a fixture repo with no monkeypatching.
`evaluate(repo)` is the pure compute path returning a Result; `main()` is the
only adapter that prints/exits. The scan order, root set, file filters,
allowlist, and messages are lifted verbatim from the former inline gate.
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

# forbidden patterns. Trailer-shaped lines are anchored at line-start
# so prose mentioning the words "co-authored" elsewhere does not trip
# the gate. Word-boundary patterns catch product/vendor names as
# bare tokens.
FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("co-authored-by trailer", re.compile(r"^\s*co-authored-by\s*:", re.IGNORECASE | re.MULTILINE)),
    ("generated-by trailer", re.compile(r"^\s*generated-by\s*:", re.IGNORECASE | re.MULTILINE)),
    ("ai-assisted-by trailer", re.compile(r"^\s*ai-assisted-by\s*:", re.IGNORECASE | re.MULTILINE)),
    ("assisted-by trailer", re.compile(r"^\s*assisted-by\s*:", re.IGNORECASE | re.MULTILINE)),
    ("prompt trailer", re.compile(r"^\s*prompt\s*:", re.IGNORECASE | re.MULTILINE)),
    ("Claude Code reference", re.compile(r"\bClaude\s+Code\b", re.IGNORECASE)),
    ("ChatGPT reference", re.compile(r"\bChatGPT\b", re.IGNORECASE)),
    ("Anthropic reference", re.compile(r"\bAnthropic\b", re.IGNORECASE)),
    ("OpenAI reference", re.compile(r"\bOpenAI\b", re.IGNORECASE)),
    ("model-generated phrasing", re.compile(r"\bmodel-generated\b", re.IGNORECASE)),
    ("ai-generated phrasing", re.compile(r"\bai-generated\b", re.IGNORECASE)),
    ("generated-with-Claude phrasing", re.compile(r"\bgenerated\s+with\s+Claude\b", re.IGNORECASE)),
    (
        "generated-with-ChatGPT phrasing",
        re.compile(r"\bgenerated\s+with\s+ChatGPT\b", re.IGNORECASE),
    ),
]

SCAN_GLOBS = [
    "*.html",
    "*.css",
    "*.js",
    "*.json",
    "*.txt",
    "*.md",
    "*.py",
    "*.sh",
    "*.svg",
    "*.yml",
    "*.yaml",
    "*.xml",
]

# roots scanned, repo-relative. .github/ included so any future workflow
# that might reference forbidden vendor names trips the gate.
SCAN_ROOTS = [
    "public",
    "tools",
    "templates",
    "docs",
    ".github",
    "reports",
]

# files the gate explicitly tolerates. each entry is a path relative
# to the repo root. the allowlist is small and explicit — every entry is
# either the gate itself (contains the patterns as regex source) or a
# repo-record file that names the patterns by design.
ALLOWLIST_RELATIVE = {
    "tools/quality/validate_git_metadata.py",
    "tools/quality/validate_language_consistency.py",
    "reports/git-authorship-metadata-audit.txt",
    "reports/historical-commit-attribution-report.txt",
    # docs/AUTHORSHIP-STATEMENT.md is allowed to mention the bare names
    # Claude/ChatGPT/Anthropic in the context of explaining the policy.
    # it must not contain trailers (caught by the trailer regexes).
    "docs/AUTHORSHIP-STATEMENT.md",
}

# frozen archives are sealed historical bytes; never scanned.
FROZEN_PREFIX = re.compile(r"^public/integrity/releases/\d{4}-\d{2}/")


def _is_frozen(rel: str) -> bool:
    return bool(FROZEN_PREFIX.match(rel))


# ---------------------------------------------------------------------------
# Result — the value that flows through the interface. evaluate() produces it;
# main() renders it. tests assert on Result, never on stdout.
# ---------------------------------------------------------------------------
@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    scanned: int = 0

    @property
    def ok(self) -> bool:
        return not self.fails


# ---------------------------------------------------------------------------
# evaluate — the pure compute path. one call, one Result, over the injected
# Repo. walks the repo-relative scan roots in the original order (per root,
# per glob, rglob), preserving the exact file set and scan count.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo) -> Result:
    r = Result()

    for root_rel in SCAN_ROOTS:
        root = repo.root / root_rel
        if not root.is_dir():
            continue
        for glob in SCAN_GLOBS:
            for p in root.rglob(glob):
                if not p.is_file():
                    continue
                rel = p.relative_to(repo.root).as_posix()
                if rel in ALLOWLIST_RELATIVE:
                    continue
                if _is_frozen(rel):
                    continue
                try:
                    text = p.read_text(encoding="utf-8", errors="strict")
                except UnicodeDecodeError:
                    continue
                r.scanned += 1
                for label, pat in FORBIDDEN_PATTERNS:
                    for m in pat.finditer(text):
                        line_no = text.count("\n", 0, m.start()) + 1
                        # show the offending line, trimmed.
                        line_text = text.splitlines()[line_no - 1].strip()[:120]
                        r.fails.append(f"{rel}:{line_no} [{label}] — {line_text}")

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
            f"FAIL: {len(r.fails)} AI/model attribution issue(s) ({r.scanned} files scanned)",
            file=sys.stderr,
        )
        for f in r.fails[:30]:
            print(f"  ✗ {f}", file=sys.stderr)
        if len(r.fails) > 30:
            print(f"  … and {len(r.fails) - 30} more", file=sys.stderr)
        print(file=sys.stderr)
        print("AI/model attribution belongs in docs/AUTHORSHIP-STATEMENT.md", file=sys.stderr)
        print("and humans.txt only — never in commit metadata, generated", file=sys.stderr)
        print("repo material, source mirrors, or public file headers.", file=sys.stderr)
        return 1

    print(f"OK: no AI/model attribution metadata in working tree ({r.scanned} files scanned)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
