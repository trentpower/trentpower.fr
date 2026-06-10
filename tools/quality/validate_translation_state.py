#!/usr/bin/env python3
"""validate_translation_state.py — content/fr/ translation freshness gate.

Every content/fr/pages/*.yml must carry a translation: block recording the
English source it tracks and a review status. This validator checks:

  · the block exists and has source_page / source_hash / status / updated
  · status is one of draft | machine-assisted | human-reviewed
  · source_hash still matches the current content/en source (stale FR copy)

In --release mode a draft or stale translation fails the build; otherwise
it is a warning (dev inner loop).

Usage:
    python3 tools/validate_translation_state.py            # warn
    python3 tools/validate_translation_state.py --release  # fail on draft/stale
"""

from __future__ import annotations

import sys

try:
    import yaml
except ImportError:
    print("error: PyYAML required", file=sys.stderr)
    sys.exit(2)

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
from hashing import sha256_hex  # noqa: E402
from paths import CONTENT_DIR  # noqa: E402

VALID_STATUS = {"draft", "machine-assisted", "human-reviewed"}
RELEASE_OK = {"human-reviewed"}


def _en_source_hash(page_name: str) -> str | None:
    en_yaml = CONTENT_DIR / "en" / "pages" / f"{page_name}.yml"
    if en_yaml.exists():
        return "sha256-" + sha256_hex(en_yaml.read_bytes())
    return None


def main() -> int:
    release = "--release" in sys.argv
    fr_pages = sorted((CONTENT_DIR / "fr" / "pages").glob("*.yml"))
    if not fr_pages:
        print("✗ no content/fr/pages/*.yml found", file=sys.stderr)
        return 1

    errors, warnings = [], []
    for path in fr_pages:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rel = path.relative_to(CONTENT_DIR.parent)
        tr = data.get("translation")
        if not isinstance(tr, dict):
            errors.append(f"{rel}: missing translation: block")
            continue
        for field in ("source_page", "source_hash", "status", "updated"):
            if field not in tr:
                errors.append(f"{rel}: translation.{field} missing")
        status = tr.get("status")
        if status not in VALID_STATUS:
            errors.append(f"{rel}: invalid status {status!r}")
        current = _en_source_hash(tr.get("source_page", ""))
        stale = current is not None and current != tr.get("source_hash")
        if stale:
            msg = f"{rel}: source_hash stale — EN source changed since translation"
            (errors if release else warnings).append(msg)
        if release and status not in RELEASE_OK:
            errors.append(f"{rel}: status {status!r} not release-ready (need human-reviewed)")

    for w in warnings:
        print(f"  ⚠ {w}")
    for e in errors:
        print(f"  ✗ {e}", file=sys.stderr)
    if errors:
        print(f"\n✗ translation state: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print(
        f"✓ translation state OK ({len(fr_pages)} fr pages"
        + (f", {len(warnings)} warning(s)" if warnings else "")
        + ")"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
