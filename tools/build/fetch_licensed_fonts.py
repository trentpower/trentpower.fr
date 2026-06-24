#!/usr/bin/env python3
"""tools/build/fetch_licensed_fonts.py — restore licensed font binaries.

The Klim Type Foundry fonts are deliberately absent from the public git
repository (the licence prohibits redistribution; see
metadata/repo-exclusions.json). The live site serves them under a
commercial agreement, so a fresh checkout restores them from the live
host and verifies every byte against the SRI digest recorded in the
signed integrity manifest. A digest mismatch fails closed: no file is
written unless it is exactly the attested binary.

Idempotent: files already on disk with the right digest are left alone.

Run standalone:
    python3 tools/build/fetch_licensed_fonts.py            # restore missing
    python3 tools/build/fetch_licensed_fonts.py --check    # verify only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

_TOOLS = next(_a for _a in Path(__file__).resolve().parents if _a.name == "tools")
sys.path.insert(0, str(_TOOLS / "lib"))

from hashing import sri_sha256  # noqa: E402
from paths import REPO_ROOT  # noqa: E402

MANIFEST = REPO_ROOT / "metadata" / "repo-exclusions.json"


def main() -> int:
    ap = argparse.ArgumentParser(description="restore licensed font binaries")
    ap.add_argument("--check", action="store_true", help="verify only, restore nothing")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = manifest["files"]
    fetched: dict[str, bytes] = {}
    restored = present = 0
    fails: list[str] = []

    for e in entries:
        target = REPO_ROOT / e["path"]
        want = e["live_sha256"]
        if target.is_file() and sri_sha256(target.read_bytes()) == want:
            present += 1
            continue
        if args.check:
            fails.append(f"{e['path']}: missing or digest mismatch")
            continue
        data = fetched.get(e["live_url"])
        if data is None:
            try:
                with urllib.request.urlopen(e["live_url"], timeout=120) as r:
                    data = r.read()
            except Exception as exc:
                fails.append(f"{e['path']}: download failed ({exc})")
                continue
            fetched[e["live_url"]] = data
        got = sri_sha256(data)
        if got != want:
            fails.append(f"{e['path']}: live bytes do not match signed manifest ({got})")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=target.name + ".")
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, target)
        restored += 1

    print(f"licensed-fonts: {present} present, {restored} restored, {len(fails)} failed")
    if fails:
        for f in fails:
            print(f"  ✗ {f}")
        return 1
    print("OK: every licensed binary matches the signed integrity manifest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
