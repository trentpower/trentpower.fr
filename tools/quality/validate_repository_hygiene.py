#!/usr/bin/env python3
"""tools/validate_repository_hygiene.py — strict pre-build / pre-deploy gate.

Recursively scans the release input tree (public/) for artefacts that
must never ship: private operational data, secrets, keys, databases,
editor cruft, build scratch. Fails non-zero with human-readable
diagnostics so the build aborts before a leak can be packaged, hashed,
signed, or pushed.

Run standalone:
    python3 tools/quality/validate_repository_hygiene.py    # scan public/

This is defence-in-depth: .gitignore stops files entering git, the
public-exposure allow-list governs what is reachable over HTTP, and
this gate is the last structural check on the bytes themselves.

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)`. The release-input tree (`public/`) is walked through `repo.root`,
which is exactly what a fixture repo provides — no monkeypatching. `evaluate(repo)`
is the compute path returning a Result; `main()` is the only adapter that
prints/exits. Byte-identical to the former inline scan().
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
from redact import mask_secret  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

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


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


def evaluate(repo: Repo) -> Result:
    """Walk the release input tree (public/) and collect hygiene violations.

    The scanned root is `repo.root / "public"`; for the production REPO_ROOT
    this equals PUBLIC_DIR, so behaviour is byte-identical to the former scan()."""
    r = Result()
    fails = r.fails
    root = repo.root / "public"
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
                    m = pat.search(line)
                    if m:
                        # never echo the matched value — that would re-leak
                        # it into terminals and ci logs. the mask keeps a
                        # short prefix + fingerprint for identification.
                        fails.append(
                            f"{rel}:{lineno}: possible {label} → {mask_secret(m.group(0))}"
                        )
    return r


def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    root = repo.root / "public"

    # the scanning line prints the absolute scanned path; for the production
    # repo_root this is identical to the former args.path.resolve() output.
    if not root.is_dir():
        print(f"FAIL: scan target does not exist: {root}")
        return 1

    print(f"repository-hygiene: scanning {root}")
    r = evaluate(repo)
    if r.fails:
        print(f"FAIL: {len(r.fails)} hygiene violation(s):")
        for f in r.fails:
            print(f"  ✗ {f}")
        print()
        print(
            "These artefacts must never enter a release. Remove them, "
            "verify .gitignore covers them, and rebuild."
        )
        return 1
    print("OK: no forbidden artefacts in release inputs")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
