#!/usr/bin/env python3
"""validate_docs_links.py — the internal links in docs/*.md must not rot.

A companion to validate_docs_freshness.py focused on one thing: every relative
link and embedded image/badge in the tracked markdown must resolve to a file that
actually ships. A doc that links to a renamed or deleted page is a broken promise
the reader only discovers by clicking; this gate catches it at build time.

  - relative markdown links + image/SVG/PNG sources → must resolve to a tracked
    file                                                              FAIL
  - same-doc and cross-doc `#anchor` targets → checked against computed GitHub
    heading slugs                                                     WARN
  - external http(s) links → skipped (flaky; no network in the gate)

Links inside fenced or indented code blocks and inline code spans are ignored —
those are examples (e.g. the root-relative badge snippet in
metadata/badges/README.md), not live links.

The slug algorithm is approximate (GitHub's is unspecified in edge cases), so
anchor mismatches are advisory. File-resolution is exact and blocking.

Shape (deep module, ADR-0002): `evaluate(repo, tracked) -> Result` is the pure
compute surface; `main()` is the only adapter (git, stdout, exit code).
"""

from __future__ import annotations

import posixpath
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(
    0,
    str(next(_a for _a in Path(__file__).resolve().parents if _a.name == "tools") / "lib"),
)
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402

FENCE_RE = re.compile(r"^(```|~~~)")
INDENT_RE = re.compile(r"^(    |\t)")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
LINK_RE = re.compile(r"\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "tel:", "data:")


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    oks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


def strip_code(text: str) -> str:
    """drop fenced + indented code blocks and inline code spans, so link
    extraction never trips on an example. mirrors GitHub's fence handling."""
    out: list[str] = []
    in_fence = False
    fence = ""
    for line in text.split("\n"):
        s = line.lstrip()
        if not in_fence and FENCE_RE.match(s):
            in_fence = True
            fence = s[:3]
            continue
        if in_fence:
            if s.startswith(fence):
                in_fence = False
            continue
        if INDENT_RE.match(line):
            continue
        out.append(line)
    return INLINE_CODE_RE.sub("", "\n".join(out))


def _slugs(text: str) -> set[str]:
    """approximate GitHub heading slugs for a markdown document."""
    seen: dict[str, int] = {}
    slugs: set[str] = set()
    in_fence = False
    fence = ""
    for line in text.split("\n"):
        s = line.lstrip()
        if not in_fence and FENCE_RE.match(s):
            in_fence = True
            fence = s[:3]
            continue
        if in_fence:
            if s.startswith(fence):
                in_fence = False
            continue
        m = HEADING_RE.match(line)
        if not m:
            continue
        title = INLINE_CODE_RE.sub("", m.group(2))
        slug = re.sub(r"[^\w\s-]", "", title).strip().lower()
        # GitHub maps each whitespace char to a hyphen WITHOUT collapsing runs,
        # so "a & b" -> "a--b". match that rather than coalescing to one hyphen.
        slug = re.sub(r"\s", "-", slug)
        if slug in seen:
            seen[slug] += 1
            slug = f"{slug}-{seen[slug]}"
        else:
            seen[slug] = 0
        slugs.add(slug)
    return slugs


def _resolve(doc_rel: str, target: str) -> str:
    """repo-relative normalised path of a link target written relative to its
    document. returns "" if it escapes the repo root."""
    joined = posixpath.normpath(posixpath.join(posixpath.dirname(doc_rel), target))
    return "" if joined.startswith("..") else joined


def _target_ships(resolved: str, tracked: set[str]) -> bool:
    """a link target ships if it is a tracked file or a tracked directory (git
    tracks files, so a directory is present iff some file lives under it)."""
    if resolved in tracked:
        return True
    pref = resolved.rstrip("/") + "/"
    return any(t.startswith(pref) for t in tracked)


def evaluate(repo: Repo, tracked: set[str]) -> Result:
    md_files = sorted(t for t in tracked if t.endswith(".md"))
    r = Result()
    links = 0
    anchors = 0
    for rel in md_files:
        raw = repo.read(rel)
        body = strip_code(raw)
        for m in LINK_RE.finditer(body):
            target = m.group(1).strip().split(" ")[0]  # drop any "title"
            if not target or target.startswith(EXTERNAL_PREFIXES):
                continue
            path_part, _, anchor = target.partition("#")
            if not path_part:
                # same-document anchor.
                anchors += 1
                if anchor and anchor not in _slugs(raw):
                    r.warns.append(f"{rel}: anchor '#{anchor}' not found in this document")
                continue
            links += 1
            resolved = _resolve(rel, path_part)
            if not resolved or not _target_ships(resolved, tracked):
                line = body.count("\n", 0, m.start()) + 1
                r.fails.append(f"{rel}:{line} link target does not ship: {path_part}")
                continue
            if anchor and resolved.endswith(".md"):
                anchors += 1
                if anchor not in _slugs(repo.read(resolved)):
                    r.warns.append(f"{rel}: anchor '{path_part}#{anchor}' not found in target")
    r.oks.append(f"links: {links} relative target(s) resolve, {anchors} anchor(s) checked")
    return r


def git_tracked(repo_root: Path) -> set[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=repo_root, capture_output=True, text=True, check=True
    ).stdout
    return {line for line in out.splitlines() if line}


def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(repo, git_tracked(repo_root))

    print("DOC LINKS")
    for line in r.oks:
        print(f"OK {line}")
    for line in r.warns:
        print(f"WARN {line}")
    for line in r.fails:
        print(f"ERROR {line}")

    if r.fails:
        print(f"RESULT: {len(r.fails)} error(s), {len(r.warns)} warning(s)")
        return 1
    print("RESULT: green" if not r.warns else f"RESULT: green, {len(r.warns)} warning(s)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
