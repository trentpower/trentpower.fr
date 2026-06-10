"""
generate_file_metadata.py · build /file-metadata.json — public manifest
of byte size + modified-time + sha256 per deployable file.

Sits alongside /integrity.json. integrity.json hashes every public
file, including this one, so the existing GPG signature on
integrity.json.sig transitively signs every date and size recorded
here.

Modes:
  python3 generate_file_metadata.py            # build the manifest
  python3 generate_file_metadata.py --sweep    # rewrite placeholder
                                                 tokens in HTML + sitemap

Phase A wires the build mode only. The --sweep mode is shipped as a
no-op stub for now and gains real behaviour in Phase C, once
generate_site.py starts emitting {{lastmod:*}} and {{datemod:*}}
placeholders.

The walker, exclusion sets, and HARD_FAIL guard mirror
generate_integrity.py so the two manifests cannot disagree on which
files are public. We re-implement rather than import to avoid the
os.chdir side-effect that script has at import time.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
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
import public_tree  # noqa: E402 — shared public-surface walker + exclusion policy
from paths import (  # noqa: E402
    CONTENT_HISTORY,
    IDENTITY_CANONICAL,
    PUBLIC_DIR,
    TOOLS_DIR,
)
from sizes import humanise_bytes  # noqa: E402

# content-history map (metadata/content-history.json): persistent
# across builds, committed to git. tracks the first build day on which
# each (path, sha256) pair was seen. when a file's bytes are unchanged
# from the recorded hash, its modified_iso stays anchored to that
# first-seen day; when the bytes change, the date bumps to today. this
# is what gives every page an honest "modified" date even though every
# build touches every file's filesystem mtime.

# the public-surface exclusion policy now lives in public_tree.py, the single
# source of truth shared with generate_integrity.py. this tool sizes the same
# files integrity.py hashes, so the two manifests cannot drift apart. this tool
# additionally excludes its own output (`file-metadata.json`) — passed as
# extra_exclude_files — so it never hashes its own pre-write bytes; integrity.py
# hashes file-metadata.json after it is written (the transitive-signing path).
_EXTRA_EXCLUDE_FILES = {"file-metadata.json"}


def _load_edition() -> str:
    return json.loads(IDENTITY_CANONICAL.read_text(encoding="utf-8"))["edition"]


def _iter_public_files(root: Path):
    """yield (relpath, fullpath) for every public file, via the shared
    public_tree walker. This tool excludes its own output on top of the
    shared policy."""
    for rel, full in public_tree.iter_public_files(root, extra_exclude_files=_EXTRA_EXCLUDE_FILES):
        yield rel, Path(full)


def _load_history() -> dict:
    if CONTENT_HISTORY.exists():
        try:
            return json.loads(CONTENT_HISTORY.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {
        "_doc": (
            "content-history.json — first-seen date per (path, sha256). "
            "do not edit by hand; generate_file_metadata.py is the only writer. "
            "commit this file to git so the history survives across machines."
        ),
        "files": {},
    }


def _save_history(history: dict) -> None:
    CONTENT_HISTORY.write_text(
        json.dumps(history, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build_manifest() -> dict:
    edition = _load_edition()
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    history = _load_history()
    history_files = history.setdefault("files", {})

    files: dict[str, dict] = {}
    for rel, full in _iter_public_files(PUBLIC_DIR):
        data = full.read_bytes()
        sha = base64.b64encode(hashlib.sha256(data).digest()).decode("utf-8")
        sha256_full = f"sha256-{sha}"
        mtime = int(full.stat().st_mtime)

        record = history_files.get(rel)
        if record and record.get("sha256") == sha256_full:
            modified_iso = record["first_seen"]
        else:
            modified_iso = today
            history_files[rel] = {"sha256": sha256_full, "first_seen": today}

        files[rel] = {
            "bytes": len(data),
            "size_human_en": humanise_bytes(len(data), lang="en"),
            "size_human_fr": humanise_bytes(len(data), lang="fr"),
            "sha256": sha256_full,
            "modified_iso": modified_iso,
            "modified_mtime": mtime,
        }

    # prune history entries for files that no longer exist in public/
    history["files"] = {k: v for k, v in history_files.items() if k in files}
    _save_history(history)

    return {
        "schema_version": 1,
        "site": "https://trentpower.fr",
        "edition": edition,
        "generated_at": today,
        "algorithm": "SHA-256",
        "files": dict(sorted(files.items())),
    }


def write_manifest() -> Path:
    manifest = build_manifest()
    out = PUBLIC_DIR / "file-metadata.json"
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


_PLACEHOLDER_RE = re.compile(r"\{\{(lastmod|datemod):([^}]+)\}\}")


def _load_overrides() -> dict:
    p = TOOLS_DIR / "config" / "date_overrides.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _resolve_date(kind: str, target: str, manifest: dict, overrides: dict, edition: str) -> str:
    """resolve a placeholder to a date string.

    kind: 'lastmod' (sitemap date-only) or 'datemod' (JSON-LD ISO 8601)
    target: the path/route inside the placeholder

    resolution order:
      1. explicit override in date_overrides.json (literal 'edition' resolves
         to identity_canonical.json edition)
      2. file-metadata.json modified_iso for that path
      3. fallback to edition
    """
    override_block = overrides.get("lastmod" if kind == "lastmod" else "modified", {})
    if isinstance(override_block, dict):
        entry = override_block.get(target)
        if isinstance(entry, dict) and entry.get("date"):
            val = entry["date"]
            if val == "edition":
                val = edition
            return val + "T00:00:00+00:00" if kind == "datemod" else val

    files = manifest.get("files", {})
    rec = files.get(target.lstrip("/")) or files.get(target)
    if rec and rec.get("modified_iso"):
        val = rec["modified_iso"]
        return val + "T00:00:00+00:00" if kind == "datemod" else val

    return edition + "T00:00:00+00:00" if kind == "datemod" else edition


def sweep_placeholders() -> int:
    """rewrite {{lastmod:<path>}} and {{datemod:<route>}} placeholders in
    every HTML file under public/ and in public/sitemap.xml. resolves
    values from public/file-metadata.json and tools/date_overrides.json."""
    manifest_path = PUBLIC_DIR / "file-metadata.json"
    if not manifest_path.exists():
        print(
            "generate_file_metadata.py --sweep: file-metadata.json missing; run build first",
            file=sys.stderr,
        )
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    overrides = _load_overrides()
    edition = manifest.get("edition", _load_edition())

    swept_files = 0
    swept_tokens = 0

    def _sub(match):
        nonlocal swept_tokens
        swept_tokens += 1
        return _resolve_date(match.group(1), match.group(2), manifest, overrides, edition)

    for dirpath, dirnames, filenames in os.walk(PUBLIC_DIR):
        dirnames[:] = [d for d in dirnames if d not in public_tree.EXCLUDE_DIRS]
        for fn in filenames:
            if not (fn.endswith(".html") or fn == "sitemap.xml"):
                continue
            full = Path(dirpath) / fn
            text = full.read_text(encoding="utf-8")
            if "{{lastmod:" not in text and "{{datemod:" not in text:
                continue
            new_text = _PLACEHOLDER_RE.sub(_sub, text)
            if new_text != text:
                full.write_text(new_text, encoding="utf-8")
                swept_files += 1

    print(f"sweep: {swept_files} file(s), {swept_tokens} placeholder(s) resolved")
    return 0


def finalise_manifest() -> int:
    """re-walk public/ to refresh bytes/sha256/mtime, but preserve
    modified_iso from the existing manifest. used at stage [6h] after
    the sweep has mutated HTML and source-view has regenerated mirrors."""
    manifest_path = PUBLIC_DIR / "file-metadata.json"
    if not manifest_path.exists():
        print(
            "generate_file_metadata.py --final: preliminary manifest missing; run plain mode first",
            file=sys.stderr,
        )
        return 1
    prev = json.loads(manifest_path.read_text(encoding="utf-8"))
    prev_files = prev.get("files", {})

    edition = prev.get("edition", _load_edition())
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    files: dict[str, dict] = {}
    for rel, full in _iter_public_files(PUBLIC_DIR):
        data = full.read_bytes()
        sha = base64.b64encode(hashlib.sha256(data).digest()).decode("utf-8")
        mtime = int(full.stat().st_mtime)
        prior = prev_files.get(rel)
        # preserve modified_iso if we had one (the preliminary pass set
        # it from content-history). otherwise this is a file that
        # appeared between passes (e.g. a new source mirror) — date as
        # today.
        modified_iso = (prior or {}).get("modified_iso", today)
        files[rel] = {
            "bytes": len(data),
            "size_human_en": humanise_bytes(len(data), lang="en"),
            "size_human_fr": humanise_bytes(len(data), lang="fr"),
            "sha256": f"sha256-{sha}",
            "modified_iso": modified_iso,
            "modified_mtime": mtime,
        }

    manifest = {
        "schema_version": 1,
        "site": "https://trentpower.fr",
        "edition": edition,
        "generated_at": today,
        "algorithm": "SHA-256",
        "files": dict(sorted(files.items())),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"file-metadata.json (final): {len(files)} entries; modified_iso preserved from preliminary pass"
    )
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--sweep", action="store_true", help="rewrite placeholder tokens in HTML/sitemap"
    )
    group.add_argument(
        "--final",
        action="store_true",
        help="re-walk to refresh bytes/sha256; preserve modified_iso",
    )
    args = parser.parse_args(argv)
    if args.sweep:
        return sweep_placeholders()
    if args.final:
        return finalise_manifest()
    out = write_manifest()
    data = json.loads(out.read_text(encoding="utf-8"))
    print(f"file-metadata.json: {len(data['files'])} entries (generated_at {data['generated_at']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
