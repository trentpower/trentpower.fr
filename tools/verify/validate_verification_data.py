#!/usr/bin/env python3
"""validate_verification_data.py — shape gate for the Verify route map.

public/verify/verification-data.js is generated and read client-side by the
Verify page + modal. It is signed (listed in integrity.json), but nothing else
asserts that each record is *shaped, bounded and impossible to reinterpret* —
this validator does, as the new "publication-firewall" coverage that the
existing Python gate did not already provide.

For every record it enforces an allowlist:
  - path: absolute, on-site, no traversal / scheme / backslash
  - sha256 / source_sha256: look like sha256-<base64> (when present)
  - size_bytes: a positive int, <= 2 MB
  - edition / validated: YYYY-MM-DD
  - no duplicate record paths; key == record.path

Exit 0 = clean. Exit 1 = a malformed record (build is blocked upstream of signing).
"""

from __future__ import annotations

import json
import re
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
from paths import PUBLIC_DIR as ROOT  # noqa: E402

DATA = ROOT / "verify" / "verification-data.js"

_PATH = re.compile(r"^/[A-Za-z0-9._~/-]*$")  # absolute, on-site, no traversal chars
_SHA = re.compile(r"^sha256-[A-Za-z0-9+/]+=*$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_BYTES = 2_000_000


def _load() -> dict:
    text = DATA.read_text(encoding="utf-8")
    m = re.search(r"window\.TP_VERIFICATION_MAP\s*=\s*(\{.*\})\s*;", text, re.S)
    if not m:
        raise ValueError("could not locate window.TP_VERIFICATION_MAP object")
    return json.loads(m.group(1))


def _check_record(key: str, rec: dict) -> list[str]:
    errs: list[str] = []

    def bad(msg: str) -> None:
        errs.append(f"{key}: {msg}")

    path = rec.get("path")
    if not isinstance(path, str) or not _PATH.match(path) or ".." in path:
        bad(f"unsafe or malformed path {path!r}")
    elif path != key:
        bad(f"record path {path!r} does not match its key {key!r}")

    for field in ("sha256", "source_sha256"):
        val = rec.get(field)
        if val not in (None, "") and (not isinstance(val, str) or not _SHA.match(val)):
            bad(f"{field} is not a valid sha256-<base64> value: {val!r}")

    size = rec.get("size_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0 or size > _MAX_BYTES:
        bad(f"size_bytes must be a positive int <= {_MAX_BYTES}: {size!r}")

    for field in ("edition", "validated"):
        val = rec.get(field)
        if not isinstance(val, str) or not _DATE.match(val):
            bad(f"{field} must be YYYY-MM-DD: {val!r}")

    return errs


def main() -> int:
    if not DATA.exists():
        print(f"  FAIL: {DATA} not found")
        return 1
    try:
        records = _load()
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL: could not parse verification-data.js ({exc})")
        return 1

    errors: list[str] = []
    seen: set[str] = set()
    for key, rec in records.items():
        if not isinstance(rec, dict):
            errors.append(f"{key}: record is not an object")
            continue
        if key in seen:
            errors.append(f"{key}: duplicate record path")
        seen.add(key)
        errors.extend(_check_record(key, rec))

    if errors:
        print(f"  FAIL: {len(errors)} verification-data shape issue(s):")
        for e in errors[:40]:
            print(f"    ✗ {e}")
        return 1

    print(f"  OK: verification-data.js — {len(records)} record(s) shaped + bounded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
