#!/usr/bin/env python3
"""tools/derive_build_manifest.py — enrich public/.well-known/build.json.

generate_site.py writes the editorial/identity fields of build.json
early in the build. This script runs late — after the content tree is
byte-stable (post-SRI) but before the source mirrors and the final
integrity pass — and appends a verifiable build-provenance block:

    git_commit          source revision the build was cut from
    python_version      interpreter that ran the build
    builder_platform    coarse OS/arch of the build host
    public_file_count   files covered by public_tree_sha256
    public_tree_sha256  deterministic hash of the frozen content tree
    gpg_fingerprint     signing identity (compact, from pgp-key.asc)
    build_phases        conceptual pipeline phases

public_tree_sha256 covers the deployable *content* (HTML/CSS/JS/fonts/
images/.well-known). It deliberately excludes derived/volatile trees —
source mirrors, integrity manifests + signatures, file-metadata, the
release archive tree — so the same content yields the same hash
regardless of metadata churn. build.json itself is excluded (it carries
this hash) but is still covered downstream by the signed integrity.json.

Run standalone (idempotent — safe to re-run):
    python3 tools/derive_build_manifest.py
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
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
from paths import PUBLIC_DIR, REPO_ROOT

BUILD_JSON = PUBLIC_DIR / ".well-known" / "build.json"

# top-level public/ subtrees excluded from public_tree_sha256:
# derived mirrors and the frozen release archive set.
EXCLUDE_TOP_DIRS = {"source", "integrity"}

# individual files excluded: build.json carries the hash; the integrity
# manifest + file-metadata are regenerated after this stage; .sig files
# carry random gpg salt; the sitemap checksum is a derived convenience.
EXCLUDE_RELPATHS = {
    ".well-known/build.json",
    "integrity.json",
    "integrity.json.txt",
    "file-metadata.json",
    "sitemap.xml.sha256",
}

BUILD_PHASES = ["generate", "integrity", "derive", "sign"]


def _git_commit() -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return r.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _signing_fingerprint() -> str:
    """Compact (space-free) fingerprint derived from the published key."""
    key = PUBLIC_DIR / ".well-known" / "pgp-key.asc"
    if not key.is_file():
        return "unknown"
    try:
        r = subprocess.run(
            [
                "gpg",
                "--batch",
                "--with-colons",
                "--import-options",
                "show-only",
                "--import",
                str(key),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
    for line in r.stdout.splitlines():
        if line.startswith("fpr:"):
            return line.split(":")[9]
    return "unknown"


def _content_files() -> list:
    """Sorted relative posix paths of the frozen content tree."""
    out = []
    for p in PUBLIC_DIR.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(PUBLIC_DIR)
        parts = rel.parts
        if parts[0] in EXCLUDE_TOP_DIRS:
            continue
        relposix = rel.as_posix()
        if relposix in EXCLUDE_RELPATHS:
            continue
        if p.suffix == ".sig":
            continue
        out.append((relposix, p))
    out.sort(key=lambda t: t[0])
    return out


def _tree_sha256(files: list) -> str:
    """Deterministic fold: sha256 over (relpath \\0 filehash \\n) lines."""
    folded = hashlib.sha256()
    for relposix, path in files:
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        folded.update(relposix.encode("utf-8"))
        folded.update(b"\0")
        folded.update(file_hash.encode("ascii"))
        folded.update(b"\n")
    return folded.hexdigest()


def main() -> int:
    if not BUILD_JSON.is_file():
        print(f"FAIL: {BUILD_JSON} missing — run generate_site.py first")
        return 1

    manifest = json.loads(BUILD_JSON.read_text(encoding="utf-8"))

    files = _content_files()
    tree_sha = _tree_sha256(files)

    # provenance block — appended after the existing keys so the diff
    # is minimal and key order stays deterministic.
    provenance = {
        "git_commit": _git_commit(),
        "python_version": platform.python_version(),
        "builder_platform": f"{platform.system()} {platform.machine()}",
        "public_file_count": len(files),
        "public_tree_sha256": tree_sha,
        "gpg_fingerprint": _signing_fingerprint(),
        "build_phases": BUILD_PHASES,
    }
    for key in provenance:
        manifest.pop(key, None)
    manifest.update(provenance)

    BUILD_JSON.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("  → .well-known/build.json (+provenance)")
    print(f"    git_commit         {provenance['git_commit']}")
    print(f"    public_file_count  {provenance['public_file_count']}")
    print(f"    public_tree_sha256 {tree_sha}")
    print(f"    gpg_fingerprint    {provenance['gpg_fingerprint']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
