#!/usr/bin/env python3
"""validate_no_runtime_contamination.py — block third-party runtime
contamination from the deployed site.

Goal
----
Confirm that no deployed JavaScript or HTML script-bearing surface
contains markers of analytics, dev-server tooling, live-reload, or
WebSocket/EventSource endpoints. Editorial body copy is allowed to
reference "no analytics" as a privacy statement; this gate scans
script bodies and HTML <script>…</script> contents only.

Patterns checked
- socket.io
- (?:^|[^A-Za-z0-9_$])io\\s*\\(   — Socket.IO client init, safe-bordered
- EventSource
- WebSocket / new WebSocket
- ws:// / wss://
- livereload
- browser-sync
- googletagmanager / google-analytics / gtag(
- dataLayer
- \\bhmr\\b
- liveodds

Quiet on success, precise on failure.

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the scan runs over a fixture repo with no monkeypatching.
`evaluate(repo)` is the pure compute path returning a Result; `main()` is the
only adapter that prints/exits. Behaviour (patterns, messages, allowlist,
exclusions) is byte-identical to the former inline version.
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
from script_blocks import iter_script_blocks  # noqa: E402

# repo-relative root of the deployable bytes — the only tree the gate scans.
PUBLIC_PREFIX = "public/"

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("socket.io", re.compile(r"socket\.io")),
    ("io( call", re.compile(r"(?:^|[^A-Za-z0-9_$])io\s*\(")),
    ("EventSource", re.compile(r"\bEventSource\b")),
    ("new WebSocket", re.compile(r"\bnew\s+WebSocket\b")),
    ("WebSocket type", re.compile(r"\bWebSocket\s*\(")),
    ("ws:// scheme", re.compile(r"\bws://")),
    ("wss:// scheme", re.compile(r"\bwss://")),
    ("livereload", re.compile(r"livereload", re.IGNORECASE)),
    ("browser-sync", re.compile(r"browser-sync", re.IGNORECASE)),
    ("googletagmanager", re.compile(r"googletagmanager", re.IGNORECASE)),
    ("google-analytics", re.compile(r"google-analytics", re.IGNORECASE)),
    ("gtag(", re.compile(r"\bgtag\s*\(")),
    ("dataLayer", re.compile(r"\bdataLayer\b")),
    ("hmr", re.compile(r"\bhmr\b", re.IGNORECASE)),
    ("liveodds", re.compile(r"liveodds", re.IGNORECASE)),
]

# safe substrings — if a candidate match's surrounding line contains
# any of these, the match is treated as authored prose, not runtime.
LINE_ALLOWLIST = (
    "no analytics",
    "No analytics",
    "no third-party",
    "No third-party",
)


@dataclass
class Result:
    # one finding per (rel, line_no, label, snippet); empty == clean.
    fails: list[tuple[str, int, str, str]] = field(default_factory=list)
    public_missing: bool = False

    @property
    def ok(self) -> bool:
        return not self.fails and not self.public_missing


def scan_text(text: str) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    for label, pat in PATTERNS:
        for m in pat.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            if line_end < 0:
                line_end = len(text)
            line = text[line_start:line_end]
            if any(s in line for s in LINE_ALLOWLIST):
                continue
            findings.append((line_no, label, line.strip()))
    return findings


def scan_html(text: str) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    for blk in iter_script_blocks(text):
        body = blk.body
        if not body.strip():
            continue
        block_line = text.count("\n", 0, blk.body_start) + 1
        for sub_line, label, snippet in scan_text(body):
            findings.append((block_line + sub_line - 1, label, snippet))
    return findings


def scan_js(text: str) -> list[tuple[int, str, str]]:
    return scan_text(text)


def evaluate(repo: Repo) -> Result:
    r = Result()
    if not (repo.root / "public").is_dir():
        r.public_missing = True
        return r
    for full in repo.glob(f"{PUBLIC_PREFIX}**/*.js"):
        if not full.endswith(".js"):
            continue
        rel = full[len(PUBLIC_PREFIX) :]
        for line_no, label, snippet in scan_js(repo.read(full)):
            r.fails.append((rel, line_no, label, snippet))
    for full in repo.glob(f"{PUBLIC_PREFIX}**/*.html"):
        rel = full[len(PUBLIC_PREFIX) :]
        for line_no, label, snippet in scan_html(repo.read(full)):
            r.fails.append((rel, line_no, label, snippet))
    return r


def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(repo)
    if r.public_missing:
        print(f"FAIL: public root not found at {repo_root / 'public'}")
        return 1
    if r.fails:
        print(f"  FAIL: runtime-contamination — {len(r.fails)} match(es):")
        for rel, line_no, label, snippet in r.fails[:30]:
            print(f"    {rel}:{line_no} → {label}: {snippet[:140]}")
        if len(r.fails) > 30:
            print(f"    … {len(r.fails) - 30} more")
        return 1
    print("  OK: runtime-contamination — deployed JS/HTML free of analytics, sockets, dev tooling")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
