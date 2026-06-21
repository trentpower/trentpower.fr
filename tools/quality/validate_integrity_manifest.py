#!/usr/bin/env python3
"""validate_integrity_manifest.py — every active public file must appear in
integrity.json with a sha256-b64 that matches its bytes on disk.

Catches the case where a file was modified after integrity.json was generated
(a signed manifest that no longer reflects the tree), and the case where a
required active path is missing from the manifest entirely.

Shape (deep module, small interface). Two injected seams: `Repo(root)` for the
filesystem, and the `required_paths` list (sourced from the public-inventory
surface) for the must-be-present set — injecting it keeps `evaluate` testable
without standing up the full active tree. `main()` is the only adapter that
prints/exits. Byte-identical to the former
inline_checks.check_integrity_manifest_freshness.

Exit 0 = manifest reflects the tree. Exit 1 = missing entry, drift, or a
malformed manifest.
"""

from __future__ import annotations

import json
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
import public_inventory as _pi  # noqa: E402
from hashing import sha256_b64  # noqa: E402
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

MANIFEST_REL = "public/integrity.json"

# required entries — every active public file that integrity.json claims to
# cover. site-metadata.json is intentionally excluded by
# generate_integrity.EXCLUDE_FILES (it carries asset_version, which depends on
# bundle bytes the manifest hashes — a circular reference) and is omitted here.
_REQUIRED_LITERAL = [
    "index.html",
    "403.html",
    "404.html",
    "500.html",
    "maintenance.html",
    "local/index.html",
    "js/theme.js",
    "sw-register.js",
    "js/reveal.js",
    "js/verify-modal.js",
    "js/language-gate.js",
    "verify/verify.js",
    "verify/verification-data.js",
    "styles.css",
    "print.css",
    "sw.js",
    "source/source-manifest.json",
]


def required_paths() -> list[str]:
    """The literal core set plus every bilingual page output and per-tree error
    document (the public-inventory surface)."""
    return _REQUIRED_LITERAL + _pi.page_outputs() + _pi.error_page_outputs()


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    manifest_missing: bool = False
    bad_json: str = ""
    no_files_dict: bool = False
    file_count: int = 0

    @property
    def ok(self) -> bool:
        return not (self.fails or self.manifest_missing or self.bad_json or self.no_files_dict)


def evaluate(repo: Repo, required: list[str]) -> Result:
    if not repo.is_file(MANIFEST_REL):
        return Result(manifest_missing=True)
    try:
        man = json.loads(repo.read(MANIFEST_REL))
    except json.JSONDecodeError as e:
        return Result(bad_json=str(e))
    files = man.get("files") or {}
    if not isinstance(files, dict):
        return Result(no_files_dict=True)

    r = Result(file_count=len(files))
    # 1. every required active path is recorded.
    for rel in required:
        if rel not in files:
            r.fails.append(f"integrity.json: missing required entry for {rel}")
    # 2. every recorded entry hashes to its claimed value.
    for rel, claimed in files.items():
        pub = f"public/{rel}"
        if not repo.is_file(pub):
            r.fails.append(f"integrity.json: {rel} listed but missing on disk")
            continue
        actual = "sha256-" + sha256_b64((repo.root / pub).read_bytes())
        if actual != claimed:
            r.fails.append(
                f"integrity.json: {rel} hash drift "
                f"(manifest {claimed[:24]} vs disk {actual[:24]}) — "
                f"regenerate integrity.json"
            )
    return r


def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(repo, required_paths())
    if r.manifest_missing:
        print("  FAIL: integrity.json missing")
        return 1
    if r.bad_json:
        print(f"  FAIL: integrity.json not valid JSON ({r.bad_json})")
        return 1
    if r.no_files_dict:
        print("  FAIL: integrity.json missing 'files' dict")
        return 1
    if r.fails:
        print(f"  FAIL: {len(r.fails)} integrity-manifest freshness issue(s):")
        for f in r.fails[:50]:
            print(f"    {f}")
        if len(r.fails) > 50:
            print(f"    … and {len(r.fails) - 50} more")
        return 1
    print(f"  OK: integrity.json reflects {r.file_count} files on disk")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
