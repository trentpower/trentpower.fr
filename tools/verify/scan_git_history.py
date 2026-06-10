#!/usr/bin/env python3
"""scan_git_history.py — advisory pre-public git-history secret/path scan.

The deploy gate (`validate_repository_hygiene.py`) scans the *working tree*. It
does not look at history: a secret committed and later removed still lives in the
git objects and would be exposed the moment the repo goes public. This tool
sweeps the whole history for the same secret signatures plus local-path / private
artefact tells.

It is REPORT-ONLY by design (exit 0 even with findings, unless `--strict`):
removing a finding means rewriting history (git filter-repo / BFG), which is an
operator decision, not a build step. Run it before flipping the repo public; see
docs/PUBLIC-READINESS.md §3.

  python3 tools/verify/scan_git_history.py            # scan all history, report
  python3 tools/verify/scan_git_history.py --strict   # exit 1 if anything is found
  python3 tools/verify/scan_git_history.py --max 2000 # cap diff lines scanned per commit

Reuses SECRET_PATTERNS from validate_repository_hygiene.py so the working-tree
gate and the history scan never drift apart.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
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
# validate_repository_hygiene lives under the quality pillar.
sys.path.insert(
    0,
    str(
        next(
            _a
            for _a in __import__("pathlib").Path(__file__).resolve().parents
            if _a.name == "tools"
        )
        / "quality"
    ),
)
from validate_repository_hygiene import SECRET_PATTERNS  # noqa: E402

# local-path / private-artefact tells that should never enter public history.
# kept high-signal: filename mentions of ssh keys and bare ip addresses are
# covered by the filename scan / --ips opt-in to avoid drowning real leaks.
PATH_PATTERNS = [
    (re.compile(r"/home/[A-Za-z0-9._-]+/"), "absolute /home/ path"),
    (re.compile(r"/Users/[A-Za-z0-9._-]+/"), "absolute /Users/ path"),
    (re.compile(r"-----BEGIN PGP PRIVATE KEY"), "exported private pgp key"),
]
IP_PATTERN = (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "bare IPv4 (verify host/secret)")

# filenames whose mere presence anywhere in history is a finding.
FORBIDDEN_BASENAMES = re.compile(
    r"(?:^|/)(?:\.env(?:\.[A-Za-z0-9_-]+)?|\.htpasswd|\.gate_credentials|"
    r"id_(?:ed25519|rsa|ecdsa|dsa)|config\.local\.php)$"
)
FORBIDDEN_SUFFIXES = re.compile(r"\.(?:sqlite3?|db|pem|key|totp_key|asc)$")
# .asc is allowed ONLY for the published public key.
ASC_ALLOW = re.compile(r"(?:^|/)pgp-key\.asc$|(?:^|/)attribution\.sig$")


def _git(args: list[str]) -> str:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        errors="replace",  # history holds binaries / non-utf8 blobs
        cwd=Path(__file__).resolve().parents[2],
    ).stdout


# binary / heavy generated trees: excluded from the line-level patch scan
# (they hold no source secrets and would make `git log -p` huge + slow). the
# filename scan still covers every path in history.
_PATCH_EXCLUDES = [
    ":(exclude,glob)**/*.pdf",
    ":(exclude,glob)**/*.zip",
    ":(exclude,glob)**/*.gz",
    ":(exclude,glob)**/*.woff2",
    ":(exclude,glob)**/*.png",
    ":(exclude,glob)**/*.jpg",
    ":(exclude,glob)**/*.jpeg",
    ":(exclude,glob)**/*.webp",
    ":(exclude,glob)**/*.ico",
    ":(exclude,glob)**/*.docx",
    ":(exclude,glob)public/integrity/releases/**",
]


def scan_added_content(max_lines: int, include_ips: bool = False) -> list[str]:
    """Scan every added (+) line across all history for secret/path tells."""
    findings: list[str] = []
    path_patterns = PATH_PATTERNS + ([IP_PATTERN] if include_ips else [])
    # one big patch stream over all refs; rename detection off for speed.
    patch = _git(
        ["log", "--all", "--no-color", "-p", "--no-renames", "-U0", "--", ".", *_PATCH_EXCLUDES]
    )
    commit = "?"
    path = "?"
    count = 0
    for line in patch.splitlines():
        if line.startswith("commit "):
            commit = line[7:14]
            count = 0
            continue
        if line.startswith("+++ b/"):
            path = line[6:]
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        count += 1
        if count > max_lines:
            continue
        body = line[1:]
        for pat, label in SECRET_PATTERNS:
            if pat.search(body):
                findings.append(f"{commit} {path}: {label}")
        for pat, label in path_patterns:
            if pat.search(body):
                findings.append(f"{commit} {path}: {label}")
    return findings


def scan_filenames() -> list[str]:
    """Flag any path that ever existed in history matching forbidden names."""
    findings: list[str] = []
    names = set(
        _git(["log", "--all", "--pretty=format:", "--name-only", "--no-renames"]).split("\n")
    )
    for name in sorted(n for n in names if n):
        if FORBIDDEN_BASENAMES.search(name):
            findings.append(f"history path: {name} (forbidden basename)")
        elif FORBIDDEN_SUFFIXES.search(name) and not ASC_ALLOW.search(name):
            findings.append(f"history path: {name} (forbidden suffix)")
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Advisory git-history secret/path scan.")
    ap.add_argument("--strict", action="store_true", help="exit 1 if anything is found")
    ap.add_argument("--max", type=int, default=5000, help="max added lines scanned per commit")
    ap.add_argument("--ips", action="store_true", help="also flag bare IPv4s (noisy)")
    args = ap.parse_args(argv)

    if not (Path(__file__).resolve().parents[2] / ".git").exists():
        print("scan_git_history: not a git repo (nothing to scan).")
        return 0

    content = scan_added_content(args.max, include_ips=args.ips)
    files = scan_filenames()
    # de-duplicate while preserving order.
    seen: set[str] = set()
    findings = [f for f in content + files if not (f in seen or seen.add(f))]

    if not findings:
        print("scan_git_history: clean — no secret/local-path tells in history.")
        return 0

    print(f"scan_git_history: {len(findings)} finding(s) in git history:")
    for f in findings:
        print(f"  {f}")
    print(
        "\nReview each. A genuine leak means rewriting history "
        "(git filter-repo / BFG) before going public. Some IPv4 hits may be "
        "version numbers or sample data — verify before acting."
    )
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
