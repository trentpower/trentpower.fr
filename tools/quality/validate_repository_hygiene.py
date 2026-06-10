#!/usr/bin/env python3
"""tools/validate_repository_hygiene.py — strict pre-build / pre-deploy gate.

Recursively scans the release input tree (public/) for artefacts that
must never ship: private operational data, secrets, keys, databases,
editor cruft, build scratch. Fails non-zero with human-readable
diagnostics so the build aborts before a leak can be packaged, hashed,
signed, or pushed.

Run standalone:
    python3 tools/validate_repository_hygiene.py            # scan public/
    python3 tools/validate_repository_hygiene.py --path X   # scan X

This is defence-in-depth: .gitignore stops files entering git, the
public-exposure allow-list governs what is reachable over HTTP, and
this gate is the last structural check on the bytes themselves.
"""

from __future__ import annotations

import argparse
import re
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
from paths import PUBLIC_DIR

# ── directories never walked ────────────────────────────────────────
#   integrity/releases/ holds frozen historical release bodies; their
#   own hygiene was enforced when they were sealed. .git/ is not a
#   release input.
EXCLUDE_DIRS = {".git", "integrity/releases"}

# ── forbidden basenames (exact match, case-insensitive) ─────────────
FORBIDDEN_NAMES = {
    ".ds_store",
    "thumbs.db",
    ".env",
    ".gate_credentials",
    "id_ed25519",
    "id_rsa",
    "id_ecdsa",
    "id_dsa",
    ".htpasswd",
    "config.local.php",
}

# ── forbidden suffixes ──────────────────────────────────────────────
FORBIDDEN_SUFFIXES = {
    ".sqlite",
    ".sqlite3",
    ".db",
    ".log",
    ".bak",
    ".swp",
    ".tmp",
    ".pyc",
    ".totp_key",
    ".pem",
    ".key",
}

# ── forbidden path fragments (substring of posix relpath) ───────────
FORBIDDEN_FRAGMENTS = [
    "private/",
    "console_data/",
    "__pycache__/",
    ".env.",
]

# ── content signatures: secrets that may hide inside otherwise
#    innocuous text files. each scanned text file is checked line by
#    line. tuned to avoid false positives on prose. ──────────────────
SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |PGP )?PRIVATE KEY"), "private key block"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "aws access key id"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b"), "github token"),
    (
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|token|passwd|password)\s*[:=]\s*['\"][^'\"]{12,}['\"]"
        ),
        "inline credential assignment",
    ),
]
# files whose content the secret scan reads (everything else is
# treated as binary and only name/suffix-checked).
TEXT_SUFFIXES = {
    ".html",
    ".htm",
    ".js",
    ".css",
    ".json",
    ".txt",
    ".xml",
    ".yml",
    ".yaml",
    ".ini",
    ".conf",
    ".md",
    ".csv",
    ".svg",
}
# frozen release bodies legitimately mirror key material / sample
# config in documentation; skip content scanning there. (the dir is
# already excluded above, but source mirrors of those pages are not.)
SECRET_SCAN_SKIP = {
    ".well-known/pgp-key.asc",  # the *public* key — published on purpose
    "source/well-known/pgp-key.asc.txt",
}


def _excluded_dir(rel: str) -> bool:
    return any(rel == d or rel.startswith(d + "/") for d in EXCLUDE_DIRS)


def scan(root: Path) -> list[str]:
    """Return a sorted list of human-readable hygiene violations."""
    fails: list[str] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if _excluded_dir(rel):
            continue
        if path.is_dir():
            continue
        name = path.name.lower()
        suffix = path.suffix.lower()

        if name in FORBIDDEN_NAMES:
            fails.append(f"{rel}: forbidden filename '{path.name}'")
            continue
        if suffix in FORBIDDEN_SUFFIXES:
            fails.append(f"{rel}: forbidden extension '{suffix}'")
            continue
        frag = next((f for f in FORBIDDEN_FRAGMENTS if f in rel), None)
        if frag:
            fails.append(f"{rel}: forbidden path fragment '{frag}'")
            continue

        # content scan — text files only, frozen mirrors skipped.
        if suffix in TEXT_SUFFIXES and rel not in SECRET_SCAN_SKIP:
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                for pat, label in SECRET_PATTERNS:
                    if pat.search(line):
                        fails.append(f"{rel}:{lineno}: possible {label} → {line.strip()[:80]}")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description="strict repository hygiene gate")
    ap.add_argument(
        "--path",
        type=Path,
        default=PUBLIC_DIR,
        help="release input tree to scan (default: public/)",
    )
    args = ap.parse_args()
    root = args.path.resolve()

    if not root.is_dir():
        print(f"FAIL: scan target does not exist: {root}")
        return 1

    print(f"repository-hygiene: scanning {root}")
    fails = scan(root)
    if fails:
        print(f"FAIL: {len(fails)} hygiene violation(s):")
        for f in fails:
            print(f"  ✗ {f}")
        print()
        print(
            "These artefacts must never enter a release. Remove them, "
            "verify .gitignore covers them, and rebuild."
        )
        return 1
    print("OK: no forbidden artefacts in release inputs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
