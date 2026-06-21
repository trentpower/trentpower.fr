"""Shared public-tree walker + exclusion policy.

Single source of truth for "which files under public/ belong to the
signed + published surface". Consumed by:

  - generate_integrity.py     (hashes every surviving file → integrity.json)
  - generate_file_metadata.py (sizes every surviving file → file-metadata.json)

Before this module the two tools each carried their own hand-synced copy of
the exclusion sets and an identical os.walk loop. The comments warned they
were "kept in lockstep" — by hand, which is exactly how a signed manifest and
its size sidecar silently drift apart. Deriving both from one walker makes
agreement a fact instead of a hope.

Import-safe by design: NO chdir, NO file writes, NO sys.exit at import time.
The caller passes the root to walk and any per-consumer extra exclusions.

Per-consumer differences are expressed as explicit arguments, not forks:
  - generate_file_metadata.py excludes its own output (`file-metadata.json`)
    so it never hashes its own pre-write bytes.
  - generate_integrity.py keeps `file-metadata.json` in the manifest, and
    layers its own fail-loud HARD_FAIL guard on top (a security gate, not a
    filter — it stays in that script).
"""

import os
import re

# Exact-name exclusions (basename match, anywhere in the tree).
EXCLUDE_FILES = {
    ".DS_Store",
    ".gitignore",
    ".htaccess",
    ".user.ini",
    ".env",
    ".htpasswd",
    "Thumbs.db",
    "id_ed25519",
    "id_ed25519.pub",
    "composer.json",
    "composer.lock",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "integrity.json",
    "integrity.json.sig",
    "identity_canonical.json",
    "site-metadata.json",
    "Klim Invoice 26041260.pdf",
    "Klim Invoice 26041315.pdf",
    # Per-release aggregated checksums + sig. they live inside
    # integrity/releases/<edition>/ alongside the .zip / .tar.gz / .sig
    # binaries, all of which are already excluded by extension or
    # filename guard. including sha256sums{,.sig} would make the
    # signed manifest re-perturb every time the release archive
    # pipeline runs, which is a recursion the manifest carefully avoids.
    "SHA256SUMS",
    "SHA256SUMS.sig",
    # Per-release file-level archive manifest + its detached signature.
    # same recursion concern: the .sig has random gpg salt, so hashing it
    # here would change integrity.json on every build. the redistributable
    # manifest stands on its own signature, independent of the live one.
    "integrity-redistributable.json",
    "integrity-redistributable.json.sig",
    # Per-edition exclusion manifest + sig. signed independently; the .sig
    # has random gpg salt, so all three are excluded to keep the live
    # integrity.json byte-stable.
    "EXCLUDED_FILES.json",
    "EXCLUDED_FILES.json.sig",
    "EXCLUDED_FILES.txt",
    # Per-edition release.json trust anchor + sig. deterministic content,
    # random-salt .sig → excluded for byte-stability.
    "release.json",
    "release.json.sig",
    # Per-edition builds index + sig. content grows each rebuild; .sig has
    # random gpg salt → excluded for byte-stability.
    "builds.json",
    "builds.json.sig",
}

# Path-specific exclusions (root-relative posix path). only the root readme
# is excluded — that one is the gandi instance documentation placed at the
# sftp root by the host, not a public artefact. /source/README.txt is the
# same content shipped inside the release archives and must be hashed.
EXCLUDE_PATHS = {
    "README.txt",
}

# directory names pruned anywhere in the tree. the walk runs over public/
# specifically, so tools/, templates/, docs/, .git, i18n/, scripts/ are never
# reached; this set covers belt-and-braces cases that could appear inside
# public/. (__pycache__ is non-deterministic.)
EXCLUDE_DIRS = {
    ".git",
    ".github",
    "private",
    "console_data",
    "node_modules",
    "ZIP",
    "__MACOSX",
    "__pycache__",
}

# extension exclusions (lowercased). ".md" is intentionally NOT here: the
# editorial review documents at /editorial/*.md are public artefacts and
# belong in the signed manifest.
EXCLUDE_EXTENSIONS = {
    ".zip",  # release archive bundles
    ".gz",  # release archive .tar.gz
    ".sha256",  # release archive checksum files
    ".py",
    ".pyc",  # python bytecode (also caught by __pycache__ dir; defence in depth)
    ".sh",
    ".bak",
    ".old",
    ".orig",
    ".tmp",
    ".log",
    ".env",
    ".swp",  # editor swap files
    ".sqlite",
    ".db",
    ".totp_key",
}

# basename regex exclusions.
EXCLUDE_PATTERNS = [
    # old numbered rollback assets (styles.v22.css, app.v22.js, fonts/*.v17.woff2)
    re.compile(r"\.v\d+\.(css|js|woff2)$"),
    # dated rebuild companions at /integrity/releases/<edition>/ — same
    # byte-stability reason as the canonical companions (deterministic
    # content but .sig has random gpg salt). matched on basename only.
    re.compile(
        r"^(integrity-redistributable|release|EXCLUDED_FILES)-\d{4}-\d{2}-\d{2}\.(json|txt)(\.sig)?$"
    ),
]

# audit artefact files (local-only, prefixed with _) and dirs.
EXCLUDE_PREFIXES = ("_audit", "_rollback", "_archives", "_licences")


def iter_public_files(root, *, extra_exclude_files=frozenset()):
    """Yield (relpath, fullpath) for every file under `root` that belongs to
    the public surface. `relpath` is root-relative posix; `fullpath` is the
    path to open (preserves whatever form `root` was passed in).

    extra_exclude_files: per-consumer basenames to skip beyond EXCLUDE_FILES
    (e.g. a tool excluding its own output file).
    """
    exclude_files = EXCLUDE_FILES | set(extra_exclude_files)
    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded directories
        dirnames[:] = [
            d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(EXCLUDE_PREFIXES)
        ]
        for fn in filenames:
            if fn in exclude_files:
                continue
            if fn.endswith(".template.js"):
                continue
            if any(fn.startswith(p) for p in EXCLUDE_PREFIXES):
                continue
            _, ext = os.path.splitext(fn)
            if ext.lower() in EXCLUDE_EXTENSIONS:
                continue
            # release-archive detached signatures (trentpower-fr-<date>.{zip,
            # tar.gz}.sig) pair with archive binaries excluded by extension,
            # so the sigs would otherwise dangle.
            if fn.endswith(".sig") and fn.startswith("trentpower-fr-"):
                continue
            if any(p.search(fn) for p in EXCLUDE_PATTERNS):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if rel in EXCLUDE_PATHS:
                continue
            yield rel, full


def snapshot_tree(root) -> dict:
    """Content-hash EVERY file under `root`, no exclusions — the convergence
    signal. Returns {root-relative posix path: sha256 hex}.

    Distinct from iter_public_files on purpose: the byte-convergence driver and
    the seal-immutability guard must notice ANY file moving, including the ones
    the signed-surface walker excludes (integrity.json, site-metadata.json,
    verification-data.js). On a converged tree a full generator pass rewrites
    those with identical content, so their hash is stable here; if anything is
    genuinely churning, this surfaces it. No writes, no chdir, import-safe.
    """
    from pathlib import Path

    from hashing import sha256_file_hex

    out: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            out[rel] = sha256_file_hex(Path(full))
    return out
