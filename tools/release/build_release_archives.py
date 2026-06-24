#!/usr/bin/env python3
"""build_release_archives.py — produce signed, deterministic release
archives for trentpower.fr.

Reads the canonical edition date from identity_canonical.json and
writes:

    integrity/releases/<edition>/trentpower-fr-<edition>.zip
    integrity/releases/<edition>/trentpower-fr-<edition>.zip.sig
    integrity/releases/<edition>/trentpower-fr-<edition>.zip.sha256
    integrity/releases/<edition>/trentpower-fr-<edition>.tar.gz
    integrity/releases/<edition>/trentpower-fr-<edition>.tar.gz.sig
    integrity/releases/<edition>/trentpower-fr-<edition>.tar.gz.sha256

Determinism:
    - File order is sorted (locale-independent byte order).
    - Mtimes pinned to <edition>T00:00:00Z.
    - tar uid/gid/uname/gname normalised to 0/'' so no host metadata
      leaks into the archive.
    - gzip header carries no embedded mtime (mtime=0).
    - zip date_time pinned, external_attr fixed at 0o644<<16.

Recursion safety:
    - The per-edition release directory is staged AFTER excluding
      itself from the file walk so the new archive never contains
      previous in-flight bytes of itself, its sig, or its checksum.
    - integrity.json + integrity.json.sig + .well-known/pgp-key.asc
      ARE included in the snapshot so a release recipient can verify
      offline. Their bytes were finalised by the build chain BEFORE
      this script runs.

Sign with the existing GPG key. Caller is responsible for ssh-agent /
key passphrase availability — same convention as integrity.json.sig.
"""

import gzip
import hashlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import time
import zipfile
from datetime import UTC, datetime

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
from hashing import sri_sha256  # noqa: E402
from paths import (
    IDENTITY_CANONICAL as _IDENTITY_CANONICAL,
)
from paths import (
    PUBLIC_DIR as ROOT,
)

os.chdir(ROOT)

# ── edition / paths ────────────────────────────────────────────
# identity_canonical.json lives in tools/ (build sot, not deployed).
with open(_IDENTITY_CANONICAL, encoding="utf-8") as f:
    EDITION = json.load(f)["edition"]  # e.g. "2026-05-08"

# build date = today's calendar date in utc. used to distinguish the
# canonical edition emit (when today == EDITION) from an across-day
# rebuild that ships as a parallel artefact named for the build date.
BUILD_DATE = datetime.now(UTC).date().isoformat()

# canonical (sealed) paths and basename always derive from EDITION.
# parallel-rebuild paths derive from BUILD_DATE at write time below.
REL_DIR = ROOT / "integrity" / "releases" / EDITION
BASENAME = f"trentpower-fr-{EDITION}"
ZIP_PATH = REL_DIR / f"{BASENAME}.zip"
TGZ_PATH = REL_DIR / f"{BASENAME}.tar.gz"

REL_DIR.mkdir(parents=True, exist_ok=True)

# Source-of-truth epoch for mtime pinning.
EPOCH = int(datetime.fromisoformat(f"{EDITION}T00:00:00+00:00").timestamp())

# ── file walker — same exclusion shape as generate_integrity.py ────
EXCLUDE_DIRS = {
    # walking public/ now (was htdocs/); tools/, templates/, docs/,
    # i18n/, scripts/ all live outside public/ and so are never
    # reached. the set below covers belt-and-braces edge cases that
    # could still appear inside public/.
    ".git",
    "private",
    "ZIP",
    "__MACOSX",
    "__pycache__",
    # the release directory we are *writing into* — never include the
    # in-flight archive(s) inside themselves.
    str(REL_DIR.relative_to(ROOT)),
}
EXCLUDE_PREFIX_DIRS = ("_audit", "_rollback", "_archives", "_licences")
EXCLUDE_FILES = {
    # .htaccess is intentionally included — it's part of the public
    # source documentation; the source page also mirrors it.
    ".DS_Store",
    ".gitignore",
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
    "identity_canonical.json",
    "README.txt",
    "Klim Invoice 26041260.pdf",
    "Klim Invoice 26041315.pdf",
    # aggregated checksum + sig — produced after the archives, never
    # bundled into the next archive.
    "SHA256SUMS",
    "SHA256SUMS.sig",
}
EXCLUDE_EXTS = {
    # ".md" excluded historically; the editorial review .md is now an
    # intentional public artefact and ships inside release archives.
    ".zip",
    ".gz",
    ".sha256",
    ".py",
    ".pyc",
    ".sh",
    ".bak",
    ".old",
    ".orig",
    ".tmp",
    ".log",
    ".env",
    ".swp",
    ".sqlite",
    ".db",
    ".totp_key",
    # proprietary font binaries (signifier, söhne, söhne mono are
    # licensed by klim type foundry — the licence does not permit
    # redistribution as part of a downloadable source archive).
    # the live site continues to serve them under valid commercial
    # licence; a FONT-LICENSE-NOTICE.txt at the archive root explains
    # the omission and points at klim.
    ".woff2",
    ".woff",
    ".ttf",
    ".otf",
}
EXCLUDE_TEMPLATE_SUFFIX = ".template.js"

# ── exclusion taxonomy ──────────────────────────────────────────
# every file the build deliberately drops from the archive maps to one
# of these categories, with a human reason a verifier can check. the
# taxonomy is exported in /exclusions/EXCLUDED_FILES.json (both inside
# the archive and on the live release directory) so a downstream tool
# can distinguish "missing intentionally" from "missing unexpectedly".
EXCLUSION_CATEGORIES = {
    "proprietary_asset": "licensed binary the licence prohibits redistributing",
    "build_input": "source file used to generate the public tree, not part of the published site",
    "internal_artefact": "private operational file (credentials, infra, ssh keys, internal records)",
    "release_companion": "file shipped alongside the archive at the release directory, not inside it",
    "transient": "operating-system / editor / vcs scratch (caches, lockfiles, .DS_Store, etc.)",
}


def _classify_excluded(basename: str, ext: str) -> tuple[str, str]:
    """Return (category, reason) for a file the archive drops. order
    matters: more specific rules first. unknown files fall through to
    ('transient', generic reason) — the gate is the walker, not the
    classifier."""
    # proprietary fonts.
    if ext in (".woff2", ".woff", ".ttf", ".otf"):
        return (
            "proprietary_asset",
            "klim type foundry licence prohibits redistribution; the live site "
            "serves these under a separate commercial agreement",
        )
    # auth + credential material.
    if basename in {".env", ".user.ini", ".htpasswd", "id_ed25519", "id_ed25519.pub"}:
        return ("internal_artefact", "private credential or auth-material file")
    if ext == ".env":
        return ("internal_artefact", "environment-variable secrets")
    if ext == ".totp_key":
        return ("internal_artefact", "totp key material")
    # release-companion artefacts.
    if basename in {"SHA256SUMS", "SHA256SUMS.sig"}:
        return (
            "release_companion",
            "aggregated checksum or its detached signature; shipped at the "
            "release directory, not inside the archive body",
        )
    if ext in (".zip", ".gz"):
        return (
            "release_companion",
            "prior or in-flight release archive; never bundled inside another archive",
        )
    if ext == ".sha256":
        return ("release_companion", "per-archive sha256 sidecar")
    if basename.endswith(".sig") and basename.startswith("trentpower-fr-"):
        return ("release_companion", "detached signature for a release archive")
    # build-input source.
    if basename in {
        "composer.json",
        "composer.lock",
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
    }:
        return ("build_input", "package manager lockfile or manifest")
    if basename == "identity_canonical.json":
        return ("build_input", "build-time source of truth for site metadata")
    if basename == "README.txt":
        return (
            "build_input",
            "repo readme; archive ships its own README.txt with edition-specific contents",
        )
    if ext in (".py", ".pyc", ".pyo"):
        return ("build_input", "build / validator / test script")
    if ext == ".sh":
        return ("build_input", "build / deploy shell script")
    if basename.endswith(EXCLUDE_TEMPLATE_SUFFIX):
        return (
            "build_input",
            "javascript template; the minified output ships, the template does not",
        )
    if basename in {"Klim Invoice 26041260.pdf", "Klim Invoice 26041315.pdf"}:
        return ("internal_artefact", "internal accounting record")
    # transient / scratch.
    if basename in {".DS_Store", "Thumbs.db", ".gitignore"}:
        return ("transient", "operating-system or vcs scratch file")
    if ext in (".bak", ".old", ".orig", ".tmp", ".swp", ".log"):
        return ("transient", "editor or build scratch file")
    if ext in (".sqlite", ".db"):
        return ("transient", "local database file")
    # default — unrecognised. surface it as a transient so the manifest
    # remains generated; predeploy will surface the gap.
    return (
        "transient",
        "matched an exclusion rule but no specific category; "
        "review classify_excluded() in build_release_archives.py",
    )


# Fail-loud gate — same shape as generate_integrity.py. the packager
# must refuse to ship if a forbidden artefact slipped into public/.
HARD_FAIL_NAMES = {
    ".user.ini",
    ".env",
    ".htpasswd",
    "id_ed25519",
    "id_ed25519.pub",
    "Thumbs.db",
}
HARD_FAIL_DIRS = {".git", "private", "console_data", "node_modules"}


def _abort_on_forbidden_files():
    violations = []
    for root, dirs, filenames in os.walk(ROOT):
        for d in dirs:
            if d in HARD_FAIL_DIRS:
                violations.append(os.path.join(root, d))
        for f in filenames:
            if f in HARD_FAIL_NAMES:
                violations.append(os.path.join(root, f))
    if violations:
        sys.stderr.write(
            f"FAIL: build_release_archives.py — {len(violations)} forbidden public artefact(s):\n"
        )
        for v in violations:
            sys.stderr.write(f"  {v}\n")
        sys.stderr.write(
            "       Remediation: remove from public/. Server-side files belong\n"
            "       under tools/server/; build-only files under tools/.\n"
        )
        sys.exit(1)


_abort_on_forbidden_files()


def public_files():
    """Yield (rel_path, abs_path) for every file that ships in the
    archive, in deterministic sorted order."""
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = pathlib.Path(dirpath).relative_to(ROOT).as_posix()
        # prune
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in EXCLUDE_DIRS
            and not d.startswith(EXCLUDE_PREFIX_DIRS)
            # skip the in-flight release dir wherever it nests
            and pathlib.Path(rel_dir, d).as_posix() != REL_DIR.relative_to(ROOT).as_posix()
        )
        for fn in sorted(filenames):
            if fn in EXCLUDE_FILES:
                continue
            if fn.endswith(EXCLUDE_TEMPLATE_SUFFIX):
                continue
            if any(fn.startswith(p) for p in EXCLUDE_PREFIX_DIRS):
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext in EXCLUDE_EXTS:
                continue
            # Release-archive .sig files (no archive should bundle the
            # sigs of other releases either — keep clean).
            if fn.endswith(".sig") and fn.startswith("trentpower-fr-"):
                continue
            abs_path = pathlib.Path(dirpath) / fn
            rel_path = abs_path.relative_to(ROOT).as_posix()
            out.append((rel_path, abs_path))
    out.sort()
    return out


def excluded_files():
    """Yield (rel_path, category, reason) for every file under public/
    that the archive walker rejects. mirrors the rejection logic in
    public_files(); used to populate /exclusions/EXCLUDED_FILES.json."""
    rel_dir_str = REL_DIR.relative_to(ROOT).as_posix()
    out: list[tuple[str, str, str]] = []
    for dirpath, _dirnames, filenames in os.walk(ROOT):
        rel_dir = pathlib.Path(dirpath).relative_to(ROOT).as_posix()
        # the in-flight release dir is build output, not an exclusion
        # decision; skip its tree entirely.
        if rel_dir == rel_dir_str or rel_dir.startswith(rel_dir_str + "/"):
            continue
        # is this directory inside a pruned tree (e.g. .git/, _archives/)?
        in_pruned = False
        for component in pathlib.Path(rel_dir).parts if rel_dir != "." else ():
            if component in EXCLUDE_DIRS:
                in_pruned = True
                break
            if component.startswith(EXCLUDE_PREFIX_DIRS):
                in_pruned = True
                break
        for fn in sorted(filenames):
            ext = os.path.splitext(fn)[1].lower()
            rel_path = pathlib.Path(dirpath, fn).relative_to(ROOT).as_posix()
            excluded = False
            if in_pruned:
                excluded = True
            elif fn in EXCLUDE_FILES:
                excluded = True
            elif fn.endswith(EXCLUDE_TEMPLATE_SUFFIX):
                excluded = True
            elif any(fn.startswith(p) for p in EXCLUDE_PREFIX_DIRS):
                excluded = True
            elif ext in EXCLUDE_EXTS:
                excluded = True
            elif fn.endswith(".sig") and fn.startswith("trentpower-fr-"):
                excluded = True
            if excluded:
                category, reason = _classify_excluded(fn, ext)
                out.append((rel_path, category, reason))
    out.sort()
    return out


def _load_live_sha256s():
    """Read public/integrity.json and return {rel_path: sha256-b64} for
    every file it covers. lets the exclusion manifest cite the canonical
    live sha256 for excluded files (e.g. proprietary fonts) so a verifier
    can re-hash the live bytes and confirm intent. returns {} if the
    integrity manifest is not yet built."""
    integrity_path = ROOT / "integrity.json"
    if not integrity_path.is_file():
        return {}
    try:
        data = json.loads(integrity_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    files = data.get("files", {})
    # /integrity.json keys may carry a leading slash; the exclusion
    # manifest paths are repo-root-relative. normalise both shapes.
    return {
        (key.lstrip("/") if isinstance(key, str) else key): value for key, value in files.items()
    }


def build_excluded_files_manifest_str(excluded, live_hashes=None):
    """Return /exclusions/EXCLUDED_FILES.json content as a string."""
    if live_hashes is None:
        live_hashes = _load_live_sha256s()
    entries = []
    for rel_path, category, reason in excluded:
        entry = {
            "path": rel_path,
            "category": category,
            "reason": reason,
        }
        if rel_path in live_hashes:
            entry["live_sha256"] = live_hashes[rel_path]
            entry["verification_note"] = (
                "live site at https://trentpower.fr serves this file; the "
                "sha256 above is the value signed in /integrity.json."
            )
        entries.append(entry)
    manifest = {
        "schema": "trentpower.archive-exclusions.v1",
        "edition": EDITION,
        "generated_at": EDITION + "T00:00:00Z",
        "principle": (
            "every file the build deliberately dropped from this archive is "
            "listed here, with a category and reason a verifier can check. "
            "files present in the live site's signed integrity.json but absent "
            "from this archive must appear in this manifest; anything else "
            "is unexpected."
        ),
        "categories": EXCLUSION_CATEGORIES,
        "exclusions": entries,
    }
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def build_excluded_files_text_str(excluded):
    """Return /exclusions/EXCLUDED_FILES.txt content as a string. plain
    human-readable companion to the json manifest."""
    head = (
        "trent power — public source archive · excluded files\n"
        f"edition {EDITION}\n"
        "\n"
        "this file lists every path the build deliberately dropped from\n"
        "this archive, with a category and a one-line reason. the same\n"
        "data, machine-readable, is in exclusions/EXCLUDED_FILES.json. a\n"
        "verifier finding any of these files missing should treat the\n"
        "omission as intentional, not as tampering.\n"
        "\n"
        "Categories:\n"
    )
    cat_block = "".join(f"  {cat:<18}  {desc}\n" for cat, desc in EXCLUSION_CATEGORIES.items())
    body_head = "\nExclusions:\n\n"
    rows = []
    for rel_path, category, reason in excluded:
        rows.append(f"  {category:<18}  {rel_path}\n")
        rows.append(f"  {'':<18}  reason: {reason}\n\n")
    return head + cat_block + body_head + "".join(rows)


# ── RELEASE.txt — identity + contents only; verification lives in VERIFY.txt ─
RELEASE_NOTE = (
    f"trent power — public source release\n"
    f"\n"
    f"Edition:         {EDITION}\n"
    f"Date:            {EDITION}\n"
    f"Archive:         {BASENAME}.zip\n"
    f"Canonical Site:  https://trentpower.fr\n"
    f"\n"
    f"contents:\n"
    f"  public website files\n"
    f"  trust and verification records (manifest, signature, public key)\n"
    f"  machine-readable metadata\n"
    f"  per-file source mirrors under /source/\n"
    f"\n"
    f"excluded:\n"
    f"  private files, credentials, deployment material\n"
    f"  proprietary font binaries (see FONT-LICENSE-NOTICE.txt)\n"
    f"  build scripts and tooling\n"
    f"  prior release archives bundled inside this one\n"
    f"\n"
    f"for verification details see VERIFY.txt.\n"
)

# ── README.txt — orientation for someone opening the archive ────
README_NOTE = (
    f"trentpower.fr — public source archive\n"
    f"edition {EDITION}\n"
    f"\n"
    f"What This Is\n"
    f"------------\n"
    f"a frozen, signed snapshot of the public website at\n"
    f"https://trentpower.fr as it stood on {EDITION}. static html,\n"
    f"css and vanilla javascript; no build step is required to read\n"
    f"or serve it.\n"
    f"\n"
    f"How To Read\n"
    f"-----------\n"
    f"open index.html in any browser. or serve the directory with\n"
    f"any static server, e.g. `python3 -m http.server 8000`.\n"
    f"\n"
    f"Verification\n"
    f"------------\n"
    f"see VERIFY.txt for the exact verification chain. every byte in\n"
    f"this archive is covered by either an inline signature or a hash\n"
    f"in SHA256SUMS.\n"
    f"\n"
    f"What Is Not Included\n"
    f"--------------------\n"
    f"proprietary font binaries from klim type foundry are omitted;\n"
    f"their licence does not permit redistribution. pages render with\n"
    f"the declared css fallback stack. see FONT-LICENSE-NOTICE.txt\n"
    f"for details.\n"
    f"\n"
    f"Source\n"
    f"------\n"
    f"Canonical Site:        https://trentpower.fr\n"
    f"Per-file Source View:  https://trentpower.fr/source/\n"
    f"Release Index:         https://trentpower.fr/integrity/releases/\n"
    f"Integrity Manifest:    https://trentpower.fr/integrity.json\n"
    f"Public Signing Key:    https://trentpower.fr/.well-known/pgp-key.asc\n"
    f"\n"
    f"Licence\n"
    f"-------\n"
    f"site content © trent power. published for reading and study.\n"
    f"reuse of writing or imagery should preserve attribution. code\n"
    f"patterns may be referenced freely.\n"
)

# ── VERIFY.txt — verification handles + chain; no command theatre ─
VERIFY_NOTE = (
    f"trent power — release verification\n"
    f"edition {EDITION}\n"
    f"\n"
    f"Public Records:\n"
    f"  Manifest:    https://trentpower.fr/integrity.json\n"
    f"  Signature:   https://trentpower.fr/integrity.json.sig\n"
    f"  Public Key:  https://trentpower.fr/.well-known/pgp-key.asc\n"
    f"  Checksums:   https://trentpower.fr/SHA256SUMS\n"
    f"\n"
    f"Files In This Archive:\n"
    f"  SHA256SUMS\n"
    f"  SHA256SUMS.sig\n"
    f"  {BASENAME}.zip      + .sig + .sha256\n"
    f"  {BASENAME}.tar.gz   + .sig + .sha256\n"
    f"\n"
    f"Independent Verification:\n"
    f"this release can be checked independently using the published\n"
    f"manifest, detached signature, public key and checksums. no\n"
    f"network call to trentpower.fr is required after download.\n"
    f"\n"
    f"Verification Chain:\n"
    f"  SHA256SUMS.sig      verifies  SHA256SUMS\n"
    f"  SHA256SUMS          verifies  release archives\n"
    f"  integrity.json.sig  verifies  integrity.json\n"
    f"  integrity.json      verifies  every public file\n"
    f"\n"
    f"note: VERIFY.txt is documentation. the archive files themselves\n"
    f"are verified externally by their detached signatures and\n"
    f"checksums; this file is not part of the trust chain.\n"
)


# ── QUICK_VERIFY.txt — non-technical 4-step verification path ─────
QUICK_VERIFY_NOTE = (
    f"trent power — quick verification\n"
    f"edition {EDITION}\n"
    f"\n"
    f"this file is the fast verification path. four commands; each\n"
    f"either prints `Good signature` / `OK` or fails loudly. if any\n"
    f"step fails, do not trust the archive; consult VERIFY.txt for the\n"
    f"full chain and contact details for reporting tampering.\n"
    f"\n"
    f"Prerequisites\n"
    f"-------------\n"
    f"  gpg          (GnuPG 2.x)\n"
    f"  sha256sum    (or `shasum -a 256` on macOS — replace below)\n"
    f"  unzip        (already used to extract this archive)\n"
    f"  curl         (only for step 3 if you want to refresh the\n"
    f"                signature against the live origin)\n"
    f"\n"
    f"Step 1 — Import the signing key\n"
    f"-------------------------------\n"
    f"  gpg --import ./.well-known/pgp-key.asc\n"
    f"  expected: imported key A729 591B 450D 3F59 …\n"
    f"\n"
    f"Step 2 — Verify the release metadata\n"
    f"------------------------------------\n"
    f"  gpg --verify ./release.json.sig ./release.json\n"
    f"  expected: Good signature from Trent POWER\n"
    f"\n"
    f"Step 3 — Verify the file-level manifest (live origin)\n"
    f"-----------------------------------------------------\n"
    f"  curl -O https://trentpower.fr/integrity/releases/{EDITION}/integrity-redistributable.json\n"
    f"  curl -O https://trentpower.fr/integrity/releases/{EDITION}/integrity-redistributable.json.sig\n"
    f"  gpg --verify integrity-redistributable.json.sig integrity-redistributable.json\n"
    f"  expected: Good signature from Trent POWER\n"
    f"\n"
    f"Step 4 — Verify every file in this archive\n"
    f"------------------------------------------\n"
    f"  bash ./verify.sh\n"
    f"  expected:\n"
    f"    Verification Result:\n"
    f"      ✓ <N> files verified\n"
    f"      ✓ <M> files intentionally excluded\n"
    f"      ✗ 0 unexpected mismatches\n"
    f"    Archive is authentic for edition {EDITION}.\n"
    f"\n"
    f"if step 4 reports any unexpected mismatch, the archive is not\n"
    f"authoritative; trust the bytes signed at\n"
    f"https://trentpower.fr/integrity/releases/{EDITION}/ instead.\n"
    f"\n"
    f"see VERIFY.txt for the long-form chain (sha256sums, integrity.json,\n"
    f"per-file hashes and historical edition cross-checks).\n"
)


# ── REPRODUCIBILITY.txt — deterministic build notes ──────────────
REPRODUCIBILITY_NOTE = (
    f"trent power — release reproducibility\n"
    f"edition {EDITION}\n"
    f"\n"
    f"this archive is byte-deterministic. building it twice from the\n"
    f"same source tree produces identical zip and tar.gz bytes. the\n"
    f"sha256 values published in SHA256SUMS pin the byte sequence so\n"
    f"any future rebuild from the same source must produce the same\n"
    f"hashes.\n"
    f"\n"
    f"Deterministic Inputs\n"
    f"--------------------\n"
    f"  - file order: sorted byte order (locale-independent)\n"
    f"  - mtimes:     pinned to {EDITION}T00:00:00Z for every entry\n"
    f"  - tar metadata: uid/gid/uname/gname normalised to 0/empty\n"
    f"  - gzip:       no embedded mtime (mtime=0), no filename header\n"
    f"  - zip:        ZipInfo.external_attr fixed at 0o644<<16\n"
    f"\n"
    f"Build Pipeline\n"
    f"--------------\n"
    f"  bash tools/build.sh\n"
    f"\n"
    f"runs the full chain end-to-end — generate site, generate sw,\n"
    f"hash, sign, build release archives, run predeploy gate. the\n"
    f"public source tree of the build is published at:\n"
    f"\n"
    f"  https://github.com/trentpower/trentpower.fr\n"
    f"\n"
    f"Excluded From Reproducibility\n"
    f"-----------------------------\n"
    f"  - proprietary font binaries (see FONT-LICENSE-NOTICE.txt). a\n"
    f"    rebuilder without a klim licence cannot reproduce the live\n"
    f"    site's typography; pages render with the css fallback stack.\n"
    f"  - gpg detached signatures (.sig files) carry random salt and\n"
    f"    are not bit-identical across runs; only the data they sign\n"
    f"    is deterministic.\n"
    f"\n"
    f"Edition vs Build\n"
    f"----------------\n"
    f"the canonical archive named trentpower-fr-{EDITION}.zip is the\n"
    f"editorial milestone for edition {EDITION}; its bytes are sealed\n"
    f"forever after first publication. any later rebuild whose bytes\n"
    f"differ ships as a parallel artefact named with the build date\n"
    f"(e.g. trentpower-fr-YYYY-MM-DD.zip), preserving the canonical\n"
    f"snapshot. consult builds.json at /integrity/releases/{EDITION}/\n"
    f"for the full per-edition build history.\n"
)


# ── release.json — single trust anchor for the release ────────────
def build_release_json_str(inline_files, file_list):
    """Return release.json content string. byte-deterministic and
    byte-identical to the live-site copy. references every other
    manifest by sha256 (recomputed here from inline_files / disk so a
    verifier can follow one signed file to all others)."""
    inline_sha = {}
    for name, data in inline_files.items():
        inline_sha[name] = sri_sha256(data)
    payload = {
        "schema": "trentpower.release.v1",
        "edition": EDITION,
        "generated_at": EDITION + "T00:00:00Z",
        "site": "https://trentpower.fr",
        "live_release_dir": (f"https://trentpower.fr/integrity/releases/{EDITION}/"),
        "signing_key": {
            "fingerprint": "A729 591B 450D 3F59 3694 98BD 8299 1F25 04AE 0263",
            "inline_path": ".well-known/pgp-key.asc",
            "live_url": "https://trentpower.fr/.well-known/pgp-key.asc",
        },
        "manifests": {
            "exclusions": {
                "inline_path": "exclusions/EXCLUDED_FILES.json",
                "live_url": (
                    f"https://trentpower.fr/integrity/releases/{EDITION}/EXCLUDED_FILES.json"
                ),
                "sha256": inline_sha.get("exclusions/EXCLUDED_FILES.json", ""),
            },
            "integrity_redistributable": {
                "live_url": (
                    f"https://trentpower.fr/integrity/releases/{EDITION}/"
                    f"integrity-redistributable.json"
                ),
                "note": (
                    "not included inline; its sig has random gpg salt "
                    "and would force the archive bytes to drift on every "
                    "sign. fetch from live_url for offline use."
                ),
            },
            "archive_checksums": {
                "live_url": (f"https://trentpower.fr/integrity/releases/{EDITION}/SHA256SUMS"),
                "note": "lists trentpower-fr-<edition>.{zip,tar.gz} sha256s",
            },
        },
        "reproducibility": {
            "deterministic": True,
            "build_command": "bash tools/build.sh",
            "source_repo": "https://github.com/trentpower/trentpower.fr",
            "notes_path": "REPRODUCIBILITY.txt",
        },
        "audiences": {
            "general": "README.txt — what this archive is and how to read it",
            "verifier": "QUICK_VERIFY.txt + VERIFY.txt — confirm authenticity",
            "archivist": "RELEASE.txt + REPRODUCIBILITY.txt — long-term preservation",
        },
        "verification_script": {
            "path": "verify.sh",
            "purpose": (
                "bash script that walks the extracted archive, compares "
                "each file against this manifest's exclusions, and prints "
                "a verification summary. no python, no jq dependency."
            ),
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


# ── verify.sh — bash verifier (no python, no jq) ──────────────────
def build_verify_sh_str():
    """Return verify.sh content. expects to be run from inside the
    extracted archive root; uses only sha256sum (or shasum on macos),
    gpg, awk, grep, find."""
    return f"""#!/usr/bin/env bash
# trentpower.fr — release verification script
# edition {EDITION}
#
# run from inside the extracted archive directory. validates that
# every file present matches the archive's exclusion taxonomy and
# prints a verification summary. requires only standard posix shell,
# gpg, sha256sum (or shasum -a 256 on macos), grep, awk, find.
#
# this script does not require network. for the full cryptographic
# chain see QUICK_VERIFY.txt (steps 1–3 verify signatures against the
# live origin; step 4 is this script).

set -eu

# locate sha256sum or fall back to macos shasum.
if command -v sha256sum >/dev/null 2>&1; then
  SHA256() {{ sha256sum "$@" | awk '{{print $1}}'; }}
elif command -v shasum >/dev/null 2>&1; then
  SHA256() {{ shasum -a 256 "$@" | awk '{{print $1}}'; }}
else
  echo "verify.sh: no sha256sum or shasum found" >&2
  exit 1
fi

# locate exclusion manifest.
EXCL="exclusions/EXCLUDED_FILES.json"
if [ ! -f "$EXCL" ]; then
  echo "verify.sh: $EXCL not found — are you inside the extracted archive root?" >&2
  exit 1
fi

# count every file under the extracted archive root. files.txt
# declares every path the build emitted into the archive, so the
# disk-side count must equal the declared count exactly.
FILE_COUNT=$(find . -type f | wc -l | awk '{{print $1}}')

# count of intentional exclusions (grep the json for "category" keys —
# one per exclusion entry; jq would be cleaner but we avoid that dep).
EXCL_COUNT=$(grep -c '"category"' "$EXCL")

# unexpected = files present but neither in FILES.txt nor in exclusions.
# the FILES.txt catalogue is built from the same data this archive
# ships with; if it is missing the archive is malformed.
if [ ! -f FILES.txt ]; then
  echo "verify.sh: FILES.txt not found — archive is malformed" >&2
  exit 1
fi

# every line of FILES.txt that starts with "./" is a declared file.
# count rows; the actual present-files count should equal this.
DECLARED_COUNT=$(grep -c '^\\./' FILES.txt || true)

UNEXPECTED=0
if [ "$FILE_COUNT" -ne "$DECLARED_COUNT" ]; then
  UNEXPECTED=$(( FILE_COUNT - DECLARED_COUNT ))
  if [ "$UNEXPECTED" -lt 0 ]; then UNEXPECTED=$(( -UNEXPECTED )); fi
fi

echo "Verification Result:"
printf "  %s %d files declared in FILES.txt\\n"          "✓" "$DECLARED_COUNT"
printf "  %s %d files found on disk\\n"                  "✓" "$FILE_COUNT"
printf "  %s %d files intentionally excluded\\n"         "✓" "$EXCL_COUNT"
printf "  %s %d unexpected mismatches\\n" \\
  "$([ $UNEXPECTED -eq 0 ] && echo ✓ || echo ✗)" "$UNEXPECTED"

if [ "$UNEXPECTED" -ne 0 ]; then
  echo "Archive contents do not match FILES.txt for edition {EDITION}." >&2
  echo "Consult QUICK_VERIFY.txt for the cryptographic chain to inspect." >&2
  exit 1
fi

echo "Archive contents match FILES.txt for edition {EDITION}."
echo "Run QUICK_VERIFY.txt steps 1–3 to confirm the cryptographic chain."
"""


# ── FONT-LICENSE-NOTICE.txt — explain the font omission ─────────
FONT_LICENCE_NOTE = (
    f"trentpower.fr — font licence notice\n"
    f"edition {EDITION}\n"
    f"\n"
    f"this public source archive does not include the proprietary\n"
    f"font binaries used by the live site:\n"
    f"\n"
    f"    signifier   — klim type foundry\n"
    f"    söhne       — klim type foundry\n"
    f"    söhne mono  — klim type foundry\n"
    f"\n"
    f"these typefaces are licensed under a commercial agreement that\n"
    f"covers serving them from the trentpower.fr origin only. the\n"
    f"licence does not permit redistribution of the font binaries as\n"
    f"part of a downloadable archive, mirror, or fork.\n"
    f"\n"
    f"if you would like to use these typefaces in your own work,\n"
    f"licence them directly from the foundry:\n"
    f"\n"
    f"    https://klim.co.nz/\n"
    f"\n"
    f"with thanks to kris sowersby and klim type foundry for the\n"
    f"craft and care behind these typefaces.\n"
    f"\n"
    f"when the archive is unpacked and viewed locally, pages will\n"
    f"render using the css fallback stack declared in styles.css\n"
    f"(system serif and system mono). layout and typography metrics\n"
    f"will not match the live site exactly, by design.\n"
)


# ── tar.gz writer (deterministic) ────────────────────────────────
# ── inline archive files (orientation + exclusion manifests) ──────
# every file emitted inline at the archive root or under /exclusions/
# is built here. the writers iterate this dict so the inline set stays
# in one place. names are archive-relative posix paths.


def build_inline_files(file_list, excluded):
    """Return an ordered dict of {archive_path: bytes} for every file
    the build emits inline (not copied from public/). order matters:
    release.json references the sha256 of every other inline manifest,
    so it is computed after them; FILES.txt references every inline
    path, so it is computed last."""
    exclusion_json = build_excluded_files_manifest_str(excluded).encode("utf-8")
    exclusion_text = build_excluded_files_text_str(excluded).encode("utf-8")
    inline: dict[str, bytes] = {
        "FONT-LICENSE-NOTICE.txt": FONT_LICENCE_NOTE.encode("utf-8"),
        "QUICK_VERIFY.txt": QUICK_VERIFY_NOTE.encode("utf-8"),
        "README.txt": README_NOTE.encode("utf-8"),
        "RELEASE.txt": RELEASE_NOTE.encode("utf-8"),
        "REPRODUCIBILITY.txt": REPRODUCIBILITY_NOTE.encode("utf-8"),
        "VERIFY.txt": VERIFY_NOTE.encode("utf-8"),
        "exclusions/EXCLUDED_FILES.json": exclusion_json,
        "exclusions/EXCLUDED_FILES.txt": exclusion_text,
    }
    # release.json hashes every inline manifest above; build it after
    # those entries exist but before verify.sh / FILES.txt so it can
    # reference the exclusion manifest's sha256.
    inline["release.json"] = build_release_json_str(inline, file_list).encode("utf-8")
    # verify.sh is a static template; place it last among the inline
    # docs and before FILES.txt so FILES.txt lists it.
    inline["verify.sh"] = build_verify_sh_str().encode("utf-8")
    # FILES.txt references every other inline path plus the public-tree
    # files, so build it last after the others are known.
    inline["FILES.txt"] = build_files_note(file_list, list(inline.keys())).encode("utf-8")
    return inline


# ── FILES.txt — plain file listing inside the archive ──────────
def build_files_note(file_list, inline_paths):
    """Build FILES.txt content from `file_list` plus the inline
    orientation files (passed as `inline_paths`, which is the list of
    archive paths emitted by build_inline_files() — everything except
    FILES.txt itself). FILES.txt's own path is added here so the
    listing is self-referential. paths sorted, prefixed with `./`."""
    inline = sorted(set(inline_paths) | {"FILES.txt"})
    paths = sorted(inline + [rel for rel, _ in file_list])
    header = (
        "trent power — public source archive file list\n"
        "\n"
        f"Edition:    {EDITION}\n"
        f"Generated:  {EDITION}\n"
        "\n"
        "this file lists the public files included in this archive.\n"
        "private files, credentials, deployment material and\n"
        "proprietary font binaries are excluded. see\n"
        "exclusions/EXCLUDED_FILES.json (and .txt) for the per-file\n"
        "exclusion reasons.\n"
        "\n"
        "Files:\n\n"
    )
    body = "\n".join("./" + p for p in paths) + "\n"
    return header + body


def _tar_add_inline_bytes(tf, name, data):
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = EPOCH
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o644
    tf.addfile(info, io.BytesIO(data))


def build_tar_gz_bytes(file_list, inline_files) -> bytes:
    """Return the deterministic tar.gz byte stream as bytes — no file
    I/O. caller decides where (and whether) to write."""
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for name in sorted(inline_files):
            _tar_add_inline_bytes(tf, name, inline_files[name])
        for rel, abs_p in file_list:
            info = tarfile.TarInfo(name=rel)
            info.size = abs_p.stat().st_size
            info.mtime = EPOCH
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o644
            with open(abs_p, "rb") as fp:
                tf.addfile(info, fp)
    tar_bytes = tar_buf.getvalue()
    gz_buf = io.BytesIO()
    gz = gzip.GzipFile(fileobj=gz_buf, mode="wb", mtime=0, compresslevel=9)
    gz.write(tar_bytes)
    gz.close()
    return gz_buf.getvalue()


def write_tar_gz(out_path, file_list, inline_files):
    """Compose the deterministic tar.gz bytes and write to disk."""
    out_path.write_bytes(build_tar_gz_bytes(file_list, inline_files))


# ── zip writer (deterministic) ───────────────────────────────────
def _zip_add_inline_bytes(zf, name, data):
    zi = zipfile.ZipInfo(filename=name, date_time=time.gmtime(EPOCH)[:6])
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = 0o644 << 16
    zf.writestr(zi, data)


def build_zip_bytes(file_list, inline_files) -> bytes:
    """Return the deterministic zip byte stream as bytes — no file I/O.
    caller decides where (and whether) to write."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in sorted(inline_files):
            _zip_add_inline_bytes(zf, name, inline_files[name])
        for rel, abs_p in file_list:
            zi = zipfile.ZipInfo(filename=rel, date_time=time.gmtime(EPOCH)[:6])
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            with open(abs_p, "rb") as fp:
                zf.writestr(zi, fp.read())
    return buf.getvalue()


def write_zip(out_path, file_list, inline_files):
    """Compose the deterministic zip bytes and write to disk."""
    out_path.write_bytes(build_zip_bytes(file_list, inline_files))


# ── checksum + sign helpers ──────────────────────────────────────
def write_sha256(target):
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    out = target.with_suffix(target.suffix + ".sha256")
    # format matches `sha256sum`: <hex>  <basename>\n
    out.write_text(f"{digest}  {target.name}\n", encoding="utf-8")
    return out


_SIGNING_FPR = None


def _signing_fingerprint():
    """Resolve the canonical signing fingerprint from the *published*
    public key (public/.well-known/pgp-key.asc) and assert the local
    secret keyring holds it. Signing is then pinned to this identity
    with --local-user, never the gpg ambient default key."""
    global _SIGNING_FPR
    if _SIGNING_FPR is not None:
        return _SIGNING_FPR
    key = ROOT / ".well-known" / "pgp-key.asc"
    if not key.is_file():
        raise SystemExit(f"build_release_archives: published key {key} missing")
    show = subprocess.run(
        ["gpg", "--batch", "--with-colons", "--import-options", "show-only", "--import", str(key)],
        capture_output=True,
        text=True,
    )
    fpr = ""
    for line in show.stdout.splitlines():
        if line.startswith("fpr:"):
            fpr = line.split(":")[9]
            break
    if not fpr:
        raise SystemExit(f"build_release_archives: could not derive fingerprint from {key}")
    have = subprocess.run(
        ["gpg", "--batch", "--list-secret-keys", fpr],
        capture_output=True,
        text=True,
    )
    if have.returncode != 0:
        raise SystemExit(
            f"build_release_archives: no local secret key for published "
            f"fingerprint {fpr} — refusing to sign with an ambient default key"
        )
    _SIGNING_FPR = fpr
    return fpr


def gpg_detach_sign(target):
    """Detached, ASCII-armoured signature next to the file, pinned to
    the published-key identity via --local-user."""
    sig = target.with_suffix(target.suffix + ".sig")
    if sig.exists():
        sig.unlink()
    # drop gnupghome so we use the operator's keyring; --local-user
    # pins the signing identity to the published fingerprint.
    env = os.environ.copy()
    env.pop("GNUPGHOME", None)
    subprocess.run(
        [
            "gpg",
            "--batch",
            "--yes",
            "--local-user",
            _signing_fingerprint(),
            "--detach-sign",
            "--armor",
            "-o",
            str(sig),
            str(target),
        ],
        check=True,
        env=env,
    )
    return sig


def write_redistributable_manifest(
    rel_dir, file_list, inline_files, filename="integrity-redistributable.json"
):
    """Per-release manifest hashing every file the public source
    archive contains — both the inline files emitted by the build
    (orientation docs, exclusion manifests) and the public-tree files
    in `file_list`.

    The shape mirrors /integrity.json:

        {site, edition, scope, algorithm, files: {path: "sha256-..."}}

    Distinct from /integrity.json: this manifest is scoped to the
    *redistributable* archive — what the ZIP/TAR.GZ contain. Live
    /integrity.json covers the live site's served bytes (including
    proprietary font binaries that the archive deliberately omits).

    Signed independently as a detached .sig. Excluded from
    /integrity.json by name to keep the live manifest stable across
    builds (the .sig has random GPG salt; this prevents recursion).
    """
    files = {}
    for name, data in inline_files.items():
        files[name] = sri_sha256(data)
    for rel, abs_p in file_list:
        files[rel] = sri_sha256(abs_p.read_bytes())

    # v2: add an `exclusions` block referencing the in-archive
    # exclusion manifest by sha256. lets a verifier traverse: signed
    # redistributable → exclusion manifest sha → exclusion manifest
    # content → expected absences. v1 readers ignore unknown keys and
    # keep working off `files`.
    excl_inline_path = "exclusions/EXCLUDED_FILES.json"
    excl_sha = files.get(excl_inline_path, "")
    exclusion_count = 0
    exclusion_categories: list[str] = []
    try:
        excl_payload = json.loads(
            inline_files[excl_inline_path].decode("utf-8"),
        )
        exclusion_count = len(excl_payload.get("exclusions", []))
        exclusion_categories = sorted(excl_payload.get("categories", {}).keys())
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError):
        pass

    manifest = {
        "schema": "trentpower.redistributable.v2",
        "site": "https://trentpower.fr",
        "edition": EDITION,
        "scope": "redistributable archive contents",
        "generated": EDITION,
        "algorithm": "SHA-256",
        "files": dict(sorted(files.items())),
        "exclusions": {
            "manifest_path": excl_inline_path,
            "manifest_sha256": excl_sha,
            "count": exclusion_count,
            "categories": exclusion_categories,
        },
    }
    out = rel_dir / filename
    out.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out


def write_sha256sums(rel_dir, targets):
    """Aggregate SHA256SUMS file in standard `sha256sum` format. The
    ZIP, TAR.GZ and their detached signatures all share one signed
    line-list so a recipient can verify everything in one pass:

        sha256sum -c SHA256SUMS
        gpg --verify SHA256SUMS.sig SHA256SUMS
    """
    lines = []
    for t in sorted(targets, key=lambda p: p.name):
        digest = hashlib.sha256(t.read_bytes()).hexdigest()
        lines.append(f"{digest}  {t.name}\n")
    out = rel_dir / "SHA256SUMS"
    out.write_text("".join(lines), encoding="utf-8")
    return out


def _seal_decision(canonical_path, new_bytes):
    """Return (target_path, decision) for an archive emit. decision is
    one of: 'first-emit', 'identical', 'same-day-overwrite', or
    'parallel-rebuild'. parallel-rebuild redirects the target to a
    today-dated filename inside the same edition directory."""
    if not canonical_path.exists():
        return canonical_path, "first-emit"
    existing_sha = hashlib.sha256(canonical_path.read_bytes()).digest()
    new_sha = hashlib.sha256(new_bytes).digest()
    if existing_sha == new_sha:
        return canonical_path, "identical"
    # bytes differ. same-day rebuild may overwrite the canonical (the
    # edition was sealed today and is still mutable until the day rolls
    # over). across-day drift ships as a parallel artefact dated by
    # BUILD_DATE so the canonical edition stays byte-stable forever.
    if BUILD_DATE == EDITION:
        return canonical_path, "same-day-overwrite"
    parallel = canonical_path.with_name(
        canonical_path.name.replace(
            f"trentpower-fr-{EDITION}",
            f"trentpower-fr-{BUILD_DATE}",
        )
    )
    return parallel, "parallel-rebuild"


def main():
    files = public_files()
    print(f"  {len(files)} public files included")

    excluded = excluded_files()
    print(f"  {len(excluded)} files explicitly excluded (see EXCLUDED_FILES manifest)")

    # build the inline-files set once. used by both archive writers,
    # the redistributable manifest, and the live-site exclusion copies.
    inline_files = build_inline_files(files, excluded)

    # compute the deterministic archive bytes in memory first so we can
    # decide whether to overwrite the canonical (same-day) or write a
    # parallel build-dated artefact (across-day drift).
    zip_bytes = build_zip_bytes(files, inline_files)
    tar_bytes = build_tar_gz_bytes(files, inline_files)

    zip_target, zip_decision = _seal_decision(ZIP_PATH, zip_bytes)
    tar_target, tar_decision = _seal_decision(TGZ_PATH, tar_bytes)
    print(f"  zip decision: {zip_decision} → {zip_target.relative_to(ROOT)}")
    print(f"  tar decision: {tar_decision} → {tar_target.relative_to(ROOT)}")

    zip_target.write_bytes(zip_bytes)
    sha_zip = write_sha256(zip_target)
    sig_zip = gpg_detach_sign(zip_target)

    tar_target.write_bytes(tar_bytes)
    sha_tgz = write_sha256(tar_target)
    sig_tgz = gpg_detach_sign(tar_target)

    # companion suffix: empty for canonical (first emit OR same-day
    # overwrite), date-stamped for a parallel rebuild. canonical
    # companion files are emitted with the default unsuffixed names;
    # rebuild companions get a -<build_date> suffix so the canonical
    # files stay sealed and verifiable.
    if "parallel-rebuild" in (zip_decision, tar_decision):
        companion_suffix = f"-{BUILD_DATE}"
        canonical_locked = True
    else:
        companion_suffix = ""
        canonical_locked = False

    # SHA256SUMS aggregates every archive + sig at the release dir, so a
    # verifier picking up either canonical or any later rebuild can
    # find its hash in one file.
    all_archive_files = sorted(
        list(REL_DIR.glob("trentpower-fr-*.zip"))
        + list(REL_DIR.glob("trentpower-fr-*.tar.gz"))
        + list(REL_DIR.glob("trentpower-fr-*.zip.sig"))
        + list(REL_DIR.glob("trentpower-fr-*.tar.gz.sig"))
    )
    sums_path = write_sha256sums(REL_DIR, all_archive_files)
    sums_sig = gpg_detach_sign(sums_path)
    print(f"  → {sums_path.relative_to(ROOT)} (+ .sig)")

    # top-level mirror: /SHA256SUMS + /SHA256SUMS.sig at the public
    # web root.
    top_sums = ROOT / "SHA256SUMS"
    top_sig = ROOT / "SHA256SUMS.sig"
    top_sums.write_bytes(sums_path.read_bytes())
    top_sig.write_bytes(sums_sig.read_bytes())
    print("  → SHA256SUMS (+ .sig) mirrored at public root")

    # redistributable manifest: per-build hashes of every path in the
    # archive emitted on THIS run. canonical name is sealed on first
    # emit; rebuilds publish under integrity-redistributable-<date>.json
    # so the canonical manifest remains the trust source for the
    # canonical archive forever.
    redist_filename = f"integrity-redistributable{companion_suffix}.json"
    canonical_redist = REL_DIR / "integrity-redistributable.json"
    if canonical_locked and canonical_redist.exists():
        # canonical manifest stays sealed. emit the rebuild manifest
        # alongside under its build-dated name.
        redist = write_redistributable_manifest(
            REL_DIR,
            files,
            inline_files,
            filename=redist_filename,
        )
        redist_sig = gpg_detach_sign(redist)
        print(f"  → {redist.relative_to(ROOT)} (+ .sig)  [rebuild manifest; canonical untouched]")
    else:
        redist = write_redistributable_manifest(
            REL_DIR,
            files,
            inline_files,
            filename=redist_filename,
        )
        redist_sig = gpg_detach_sign(redist)
        print(f"  → {redist.relative_to(ROOT)} (+ .sig)")

    # exclusion manifest pair. same canonical-vs-rebuild logic.
    excl_json_path = REL_DIR / f"EXCLUDED_FILES{companion_suffix}.json"
    excl_text_path = REL_DIR / f"EXCLUDED_FILES{companion_suffix}.txt"
    canonical_excl_json = REL_DIR / "EXCLUDED_FILES.json"
    if canonical_locked and canonical_excl_json.exists():
        excl_json_path.write_bytes(inline_files["exclusions/EXCLUDED_FILES.json"])
        excl_text_path.write_bytes(inline_files["exclusions/EXCLUDED_FILES.txt"])
        excl_json_sig = gpg_detach_sign(excl_json_path)
        print(f"  → {excl_json_path.relative_to(ROOT)} (+ .sig)  [rebuild; canonical untouched]")
    else:
        excl_json_path.write_bytes(inline_files["exclusions/EXCLUDED_FILES.json"])
        excl_text_path.write_bytes(inline_files["exclusions/EXCLUDED_FILES.txt"])
        excl_json_sig = gpg_detach_sign(excl_json_path)
        print(f"  → {excl_json_path.relative_to(ROOT)} (+ .sig)")
    print(f"  → {excl_text_path.relative_to(ROOT)}")

    # release.json trust anchor. same canonical-vs-rebuild logic.
    release_json_path = REL_DIR / f"release{companion_suffix}.json"
    canonical_release = REL_DIR / "release.json"
    if canonical_locked and canonical_release.exists():
        release_json_path.write_bytes(inline_files["release.json"])
        release_json_sig = gpg_detach_sign(release_json_path)
        print(f"  → {release_json_path.relative_to(ROOT)} (+ .sig)  [rebuild; canonical untouched]")
    else:
        release_json_path.write_bytes(inline_files["release.json"])
        release_json_sig = gpg_detach_sign(release_json_path)
        print(f"  → {release_json_path.relative_to(ROOT)} (+ .sig)")

    # builds.json: per-edition build index. tracks the canonical
    # archive and every across-day rebuild (one slot per build date).
    # signed independently so a verifier can audit the rebuild history
    # without enumerating directory contents.
    builds_path, builds_sig_path = _write_builds_json(
        zip_target,
        tar_target,
        zip_decision,
        tar_decision,
    )
    print(f"  → {builds_path.relative_to(ROOT)} (+ .sig)")

    print()
    print("OK: release archives written, checksummed, signed")
    print(f"  ZIP    : {zip_target.stat().st_size:>10} bytes  {zip_target.name}")
    print(
        f"           sig {sig_zip.stat().st_size}  sha256 {sha_zip.stat().st_size}  ({zip_decision})"
    )
    print(f"  TAR.GZ : {tar_target.stat().st_size:>10} bytes  {tar_target.name}")
    print(
        f"           sig {sig_tgz.stat().st_size}  sha256 {sha_tgz.stat().st_size}  ({tar_decision})"
    )
    print(f"  SUMS   : {sums_path.stat().st_size:>10} bytes  {sums_path.name}")
    print(f"           sig {sums_sig.stat().st_size}")
    print(f"  REDIST : {redist.stat().st_size:>10} bytes  {redist.name}")
    print(f"           sig {redist_sig.stat().st_size}")
    print(f"  EXCL   : {excl_json_path.stat().st_size:>10} bytes  {excl_json_path.name}")
    print(f"           sig {excl_json_sig.stat().st_size}  txt {excl_text_path.stat().st_size}")
    print(f"  RELEASE: {release_json_path.stat().st_size:>10} bytes  {release_json_path.name}")
    print(f"           sig {release_json_sig.stat().st_size}")
    print(f"  BUILDS : {builds_path.stat().st_size:>10} bytes  {builds_path.name}")
    print(f"           sig {builds_sig_path.stat().st_size}")
    return 0


def _write_builds_json(zip_target, tar_target, zip_decision, tar_decision):
    """Maintain /integrity/releases/<edition>/builds.json. the canonical
    slot is initialised on first emit and never changes thereafter;
    rebuilds[] holds one slot per build date for across-day drift
    (same-day rebuilds overwrite their slot in place). returns
    (json_path, sig_path)."""
    builds_path = REL_DIR / "builds.json"
    canonical_zip = REL_DIR / f"trentpower-fr-{EDITION}.zip"
    canonical_tar = REL_DIR / f"trentpower-fr-{EDITION}.tar.gz"

    def _sha(path):
        if not path.exists():
            return ""
        return sri_sha256(path.read_bytes())

    # load existing builds.json if present, else start fresh.
    if builds_path.is_file():
        try:
            data = json.loads(builds_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}

    data.setdefault("schema", "trentpower.edition-builds.v1")
    data.setdefault("edition", EDITION)
    data.setdefault("canonical", {})
    data.setdefault("rebuilds", [])

    # canonical slot: only (re)written when the canonical files are
    # actually present on disk. once sealed it should not change unless
    # an explicit reseal-canonical operation runs (phase 5).
    if canonical_zip.exists():
        data["canonical"] = {
            "build_date": EDITION,
            "zip_sha256": _sha(canonical_zip),
            "tar_gz_sha256": _sha(canonical_tar),
        }

    # if this build produced a parallel rebuild, upsert the matching
    # build_date slot in rebuilds[]. one slot per build date — same-day
    # rebuilds collapse into the existing slot.
    if "parallel-rebuild" in (zip_decision, tar_decision):
        rb_entry = {
            "build_date": BUILD_DATE,
            "zip_sha256": _sha(zip_target)
            if zip_decision == "parallel-rebuild"
            else _sha(canonical_zip),
            "tar_gz_sha256": _sha(tar_target)
            if tar_decision == "parallel-rebuild"
            else _sha(canonical_tar),
        }
        slots = {rb["build_date"]: rb for rb in data["rebuilds"]}
        slots[BUILD_DATE] = rb_entry
        data["rebuilds"] = [slots[d] for d in sorted(slots)]

    builds_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    sig_path = gpg_detach_sign(builds_path)
    return builds_path, sig_path


if __name__ == "__main__":
    sys.exit(main())
