#!/usr/bin/env python3
"""tools/quality/validate_git_metadata.py — git/repo metadata gate.

Scans the working tree for AI/model attribution metadata that does
not belong in committable bytes:

    Co-authored-by:    Generated-by:    AI-assisted-by:
    Assisted-by:       Prompt:          model-generated
    ai-generated       generated with Claude / ChatGPT
    Claude Code        ChatGPT          Anthropic         OpenAI

Per the canonical authorship position recorded in
docs/authorship-statement.md and humans.txt, AI/tool assistance
acknowledgement belongs in those documentation files only — never
in commit metadata, never in generated repo material, never in
release notes or changelogs, never in source mirrors.

The gate refuses the build if any forbidden pattern appears in
publishable working-tree files. Git history is not scanned here —
historical attribution is a separate report-only concern documented
in reports/historical-commit-attribution-report.txt.

Exit 0 = green; exit 1 = block.

Registered in tools/lib/checks.py (blocking tier).
"""

import re
import sys

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

# roots scanned. .github/ included so any future workflow that might
# reference forbidden vendor names trips the gate.
SCAN_ROOTS = [
    REPO_ROOT / "public",
    REPO_ROOT / "tools",
    REPO_ROOT / "templates",
    REPO_ROOT / "docs",
    REPO_ROOT / "design",
    REPO_ROOT / ".github",
    REPO_ROOT / "reports",
]

# files the gate explicitly tolerates. each entry is a path relative
# to REPO_ROOT. the allowlist is small and explicit — every entry is
# either the gate itself (contains the patterns as regex source) or a
# repo-record file that names the patterns by design.
ALLOWLIST_RELATIVE = {
    "tools/quality/validate_git_metadata.py",
    "tools/quality/validate_language_consistency.py",
    "reports/git-authorship-metadata-audit.txt",
    "reports/historical-commit-attribution-report.txt",
    # docs/authorship-statement.md is allowed to mention the bare names
    # Claude/ChatGPT/Anthropic in the context of explaining the policy.
    # it must not contain trailers (caught by the trailer regexes).
    "docs/authorship-statement.md",
}

# frozen archives are sealed historical bytes; never scanned.
FROZEN_PREFIX = re.compile(r"^public/integrity/releases/\d{4}-\d{2}/")


def _is_frozen(rel: str) -> bool:
    return bool(FROZEN_PREFIX.match(rel))


def main() -> int:
    fails: list[str] = []
    scanned = 0

    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for glob in SCAN_GLOBS:
            for p in root.rglob(glob):
                if not p.is_file():
                    continue
                rel = p.relative_to(REPO_ROOT).as_posix()
                if rel in ALLOWLIST_RELATIVE:
                    continue
                if _is_frozen(rel):
                    continue
                try:
                    text = p.read_text(encoding="utf-8", errors="strict")
                except UnicodeDecodeError:
                    continue
                scanned += 1
                for label, pat in FORBIDDEN_PATTERNS:
                    for m in pat.finditer(text):
                        line_no = text.count("\n", 0, m.start()) + 1
                        # show the offending line, trimmed.
                        line_text = text.splitlines()[line_no - 1].strip()[:120]
                        fails.append(f"{rel}:{line_no} [{label}] — {line_text}")

    if fails:
        print(
            f"FAIL: {len(fails)} AI/model attribution issue(s) ({scanned} files scanned)",
            file=sys.stderr,
        )
        for f in fails[:30]:
            print(f"  ✗ {f}", file=sys.stderr)
        if len(fails) > 30:
            print(f"  … and {len(fails) - 30} more", file=sys.stderr)
        print(file=sys.stderr)
        print("AI/model attribution belongs in docs/authorship-statement.md", file=sys.stderr)
        print("and humans.txt only — never in commit metadata, generated", file=sys.stderr)
        print("repo material, source mirrors, or public file headers.", file=sys.stderr)
        return 1

    print(f"OK: no AI/model attribution metadata in working tree ({scanned} files scanned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
