#!/usr/bin/env python3
"""tools/c2pa/inspect_asset.py — read back the C2PA manifest of a signed asset.

Two modes: `--json` emits the reader's stable JSON (for validators / piping); the
default is a short human summary for debugging. Reports cleanly when a file has no
embedded manifest rather than raising.

    python3 tools/c2pa/inspect_asset.py <file> [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_MIME = {
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def read_manifest(path: Path) -> dict | None:
    """Return the reader JSON dict, or None if the file carries no C2PA manifest."""
    try:
        from c2pa import Reader  # noqa: PLC0415
    except ImportError:
        raise SystemExit(
            "error: c2pa-python not importable. Run with the signing venv, e.g.\n"
            "  ~/.local/share/trentpower/c2pa-venv/bin/python tools/c2pa/inspect_asset.py ..."
        ) from None
    mime = _MIME.get(path.suffix.lower())
    if mime is None:
        raise SystemExit(f"error: no known mime for {path.suffix}")
    try:
        with open(path, "rb") as fh:
            return json.loads(Reader(mime, fh).json())
    except Exception:  # noqa: BLE001
        return None


def summarise(data: dict) -> str:
    active = data.get("active_manifest")
    if not active or active not in data.get("manifests", {}):
        return "no active manifest"
    m = data["manifests"][active]
    sig = m.get("signature_info", {})
    lines = [
        f"  title:       {m.get('title')}",
        f"  issuer:      {sig.get('issuer')}",
        f"  alg:         {sig.get('alg')}",
        f"  time:        {sig.get('time')}",
        f"  validation:  {data.get('validation_state', '?')}",
        f"  assertions:  {', '.join(a.get('label', '?') for a in m.get('assertions', []))}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Inspect a C2PA-signed asset.")
    ap.add_argument("file")
    ap.add_argument("--json", action="store_true", help="emit stable reader JSON")
    args = ap.parse_args(argv)

    path = Path(args.file)
    if not path.is_file():
        raise SystemExit(f"error: file not found: {path}")
    data = read_manifest(path)
    if data is None:
        if args.json:
            print("null")
        else:
            print("  no embedded C2PA manifest")
        return 1
    print(json.dumps(data, indent=2) if args.json else summarise(data))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
