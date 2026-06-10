#!/usr/bin/env python3
"""seal_edition.py — operator entry point for edition baseline state.

The release-archive immutability gate (predeploy step 11) reads its
seal from metadata/archive-baseline.json. New canonicals seal
automatically when predeploy first observes them; this tool covers
the two operator paths that the auto-seal does not:

  --list                          show every sealed file, grouped by edition
  --status <edition>              show what is sealed for one edition
  --reseal-canonical <edition>    intentionally replace a canonical's bytes
                                  (post-incident reissue, rare)

reseal-canonical is destructive: it deletes the canonical archive and
its byte-stable companion manifests on disk and clears the matching
baseline entries, then re-runs build_release_archives.py to mint
fresh canonical bytes. the previous bytes are not recoverable through
this tool — git history is the audit trail.

dated rebuild artefacts (trentpower-fr-<build_date>.zip with
build_date != edition) are not affected by reseal-canonical. they
ship under their own dated companion set and remain on disk
alongside the new canonical.

usage:
    python3 tools/seal_edition.py --list
    python3 tools/seal_edition.py --status 2026-05-17
    python3 tools/seal_edition.py --reseal-canonical 2026-05-17
"""

from __future__ import annotations

import argparse
import json
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
from paths import ARCHIVE_BASELINE, TOOLS_DIR
from paths import PUBLIC_DIR as ROOT

BUILD_SCRIPT = TOOLS_DIR / "release" / "build_release_archives.py"


def _load_baseline() -> dict:
    if not ARCHIVE_BASELINE.is_file():
        return {}
    try:
        return json.loads(ARCHIVE_BASELINE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FAIL: {ARCHIVE_BASELINE.name} invalid JSON ({e})")
        sys.exit(1)


def _write_baseline(data: dict) -> None:
    ARCHIVE_BASELINE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _edition_of(path: str) -> str | None:
    # paths look like integrity/releases/<edition>/...
    parts = path.split("/")
    if len(parts) >= 3 and parts[0] == "integrity" and parts[1] == "releases":
        return parts[2]
    return None


def _canonical_filenames(edition: str) -> list[str]:
    """Return the list of canonical filenames the build emits for one
    edition. dated rebuild artefacts (which carry the build date in
    the basename) are deliberately excluded from this list."""
    basename = f"trentpower-fr-{edition}"
    return [
        f"{basename}.zip",
        f"{basename}.zip.sha256",
        f"{basename}.zip.sig",
        f"{basename}.tar.gz",
        f"{basename}.tar.gz.sha256",
        f"{basename}.tar.gz.sig",
        "integrity-redistributable.json",
        "integrity-redistributable.json.sig",
        "EXCLUDED_FILES.json",
        "EXCLUDED_FILES.json.sig",
        "EXCLUDED_FILES.txt",
        "release.json",
        "release.json.sig",
    ]


def _baseline_tracked_filenames(edition: str) -> set[str]:
    """Subset of canonical filenames that the gate's frozen-archive
    immutability check actually seals into metadata/archive-baseline.json.
    mirrors the byte-stable list in
    tools/quality/inline_checks.py:_hash_archive_tree(). .sig files
    (random gpg salt), SHA256SUMS (aggregate), and builds.json
    (mutable index) are NOT baseline-tracked; their integrity is
    asserted by an independent signed manifest instead."""
    basename = f"trentpower-fr-{edition}"
    return {
        f"{basename}.zip",
        f"{basename}.zip.sha256",
        f"{basename}.tar.gz",
        f"{basename}.tar.gz.sha256",
        "integrity-redistributable.json",
        "EXCLUDED_FILES.json",
        "EXCLUDED_FILES.txt",
        "release.json",
    }


# ── --list ──────────────────────────────────────────────────────
def cmd_list() -> int:
    baseline = _load_baseline()
    if not baseline:
        print("baseline empty or missing")
        return 0
    by_edition: dict[str, list[str]] = {}
    for path in sorted(baseline):
        ed = _edition_of(path) or "(unknown)"
        by_edition.setdefault(ed, []).append(path)
    print(f"{ARCHIVE_BASELINE.relative_to(TOOLS_DIR.parent)} — {len(baseline)} sealed file(s)")
    for ed in sorted(by_edition):
        print(f"\n{ed}: {len(by_edition[ed])} file(s)")
        for p in by_edition[ed]:
            sha = baseline[p]
            print(f"  {sha[:32]}…  {p}")
    return 0


# ── --status <edition> ──────────────────────────────────────────
def cmd_status(edition: str) -> int:
    rel_dir = ROOT / "integrity" / "releases" / edition
    if not rel_dir.is_dir():
        print(f"FAIL: edition {edition!r} not present under public/integrity/releases/")
        return 1
    baseline = _load_baseline()
    prefix = f"integrity/releases/{edition}/"
    sealed = sorted(k for k in baseline if k.startswith(prefix))
    on_disk = sorted(
        f"integrity/releases/{edition}/{fp.name}" for fp in rel_dir.iterdir() if fp.is_file()
    )
    print(f"edition {edition}: {len(sealed)} sealed in baseline, {len(on_disk)} on disk")
    if sealed:
        print("\nsealed:")
        for p in sealed:
            print(f"  {baseline[p][:32]}…  {p}")

    # split the un-baseline-tracked files into two buckets:
    # (a) byte-stable canonical files that are MISSING from disk
    #     (would normally auto-seal but the file is gone — note it)
    # (b) files on disk that are intentionally not baseline-tracked
    #     (sigs, sha256sums, dated rebuilds, builds.json index)
    tracked = _baseline_tracked_filenames(edition)
    prefix = f"integrity/releases/{edition}/"
    canonical_to_seal = {prefix + n for n in tracked}
    will_auto_seal = [p for p in on_disk if p in canonical_to_seal and p not in baseline]
    intentionally_unsealed = [
        p for p in on_disk if p not in baseline and p not in canonical_to_seal
    ]
    if will_auto_seal:
        print(f"\nwill auto-seal at next predeploy ({len(will_auto_seal)}):")
        for p in will_auto_seal:
            print(f"  {p}")
    if intentionally_unsealed:
        print(
            f"\nintentionally not baseline-tracked ({len(intentionally_unsealed)} — "
            "gpg sigs / SHA256SUMS / builds.json / dated rebuild artefacts):"
        )
        for p in intentionally_unsealed:
            print(f"  {p}")
    return 0


# ── --reseal-canonical <edition> ────────────────────────────────
def cmd_reseal_canonical(edition: str) -> int:
    rel_dir = ROOT / "integrity" / "releases" / edition
    if not rel_dir.is_dir():
        print(f"FAIL: edition {edition!r} not present under public/integrity/releases/")
        return 1
    canonical_zip = rel_dir / f"trentpower-fr-{edition}.zip"
    if not canonical_zip.is_file():
        print(
            f"FAIL: canonical archive {canonical_zip.relative_to(ROOT)} not present — nothing to reseal"
        )
        return 1

    print(f"reseal-canonical: edition {edition}")
    print("  this is destructive: the canonical bytes will be replaced.")
    print("  dated rebuild artefacts under this edition are not affected.")
    print()

    # delete canonical files on disk
    deleted: list[str] = []
    for fn in _canonical_filenames(edition):
        fp = rel_dir / fn
        if fp.is_file():
            fp.unlink()
            deleted.append(fn)
            print(f"  removed   {fp.relative_to(ROOT)}")
    if not deleted:
        print(f"FAIL: no canonical files to remove in {rel_dir.relative_to(ROOT)}")
        return 1

    # clear matching baseline entries (only canonical, not dated rebuilds)
    baseline = _load_baseline()
    prefix = f"integrity/releases/{edition}/"
    canonical_set = set(_canonical_filenames(edition))
    cleared = 0
    new_baseline: dict[str, str] = {}
    for path, sha in baseline.items():
        if path.startswith(prefix):
            basename = path[len(prefix) :]
            if basename in canonical_set:
                cleared += 1
                continue
        new_baseline[path] = sha
    if cleared:
        _write_baseline(new_baseline)
        print(f"  cleared   {cleared} baseline entry(ies)")
    print()

    # regenerate canonical via the standard build path. first-emit
    # path fires because the canonical files were just removed.
    print(f"  rebuilding canonical archive for {edition}…")
    r = subprocess.run([sys.executable, str(BUILD_SCRIPT)])
    if r.returncode != 0:
        print(f"FAIL: build_release_archives.py exited {r.returncode}")
        print("      baseline has been partially cleared; investigate before commit.")
        return 1

    print()
    print(f"OK: canonical archive for {edition} resealed.")
    print("    next predeploy run will auto-seal the new hashes into")
    print(f"    {ARCHIVE_BASELINE.relative_to(TOOLS_DIR.parent)}.")
    print("    review and commit:")
    print(f"      public/integrity/releases/{edition}/")
    print(f"      {ARCHIVE_BASELINE.relative_to(TOOLS_DIR.parent)}")
    return 0


# ── entry point ─────────────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(
        prog="seal_edition.py",
        description=(
            "inspect or intentionally reseal the per-edition canonical "
            "archive baseline used by predeploy step 11."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--list",
        action="store_true",
        help="print every sealed file in the baseline, grouped by edition",
    )
    g.add_argument(
        "--status",
        metavar="EDITION",
        help="print sealed-vs-on-disk status for one edition",
    )
    g.add_argument(
        "--reseal-canonical",
        metavar="EDITION",
        help="replace the canonical archive bytes for one edition (destructive)",
    )
    args = p.parse_args()
    if args.list:
        return cmd_list()
    if args.status:
        return cmd_status(args.status)
    if args.reseal_canonical:
        return cmd_reseal_canonical(args.reseal_canonical)
    return 1


if __name__ == "__main__":
    sys.exit(main())
