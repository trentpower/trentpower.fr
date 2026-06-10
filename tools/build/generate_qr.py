#!/usr/bin/env python3
"""generate_qr.py — canonical QR SVG generator for trentpower.fr.

Every QR that prints on a sheet is derived from a single URL table here.
The build gates against this script so a URL change can never silently
diverge from the SVG bytes that end up in the signed integrity manifest.

Modes
─────
  --check  (default in build.sh)
    regenerate each QR in memory, compare to the committed SVG bytes,
    exit 1 on any drift. lists the affected files.
  --write
    write the canonical SVGs to public/images/qr/. used when the URL
    table changes or when adding new pages.

Why our QRs encode the bare host (no `https://`):
  trentpower.fr/privacy/ scans the same as https://trentpower.fr/privacy/
  on every modern phone qr reader, and the shorter payload keeps the
  module count down so the print-sheet 11.5 mm QR stays crisp on paper.

Segno parameters chosen to match the existing site register:
  error correction 'M'  — comfortable margin without overdriving size
  scale 10              — svg path uses integer module coords
  dark '#1f1e1c'        — site ink; quiet against the cream paper
  no xml decl           — matches the rest of the static svg corpus
"""

from __future__ import annotations

import argparse
import io
import pathlib
import sys

import segno

ROOT = pathlib.Path(__file__).resolve().parents[2]
QR_DIR = ROOT / "public" / "images" / "qr"

# filename (without .svg) → bare URL encoded into the QR + svg <title>
URLS = {
    "qr-home": "trentpower.fr/",
    "qr-privacy": "trentpower.fr/privacy/",
    "qr-integrity": "trentpower.fr/integrity/",
    "qr-security": "trentpower.fr/security/",
    "qr-verify": "trentpower.fr/verify/",
    "qr-source": "trentpower.fr/source/",
    "qr-releases": "trentpower.fr/integrity/releases/",
    "qr-acknowledgments": "trentpower.fr/security/acknowledgments/",
    "qr-release-2026-05-09": "trentpower.fr/integrity/releases/2026-05-09/",
    "qr-release-2026-05-17": "trentpower.fr/integrity/releases/2026-05-17/",
    "qr-verify-locally": "trentpower.fr/integrity/verify-locally/",
    "qr-sw-reset": "trentpower.fr/sw-reset/",
    "qr-maintenance": "trentpower.fr/maintenance.html",
    "print-qr-trentpower": "trentpower.fr/",
}


def render(url: str) -> bytes:
    """canonical svg bytes for one url."""
    qr = segno.make(url, error="M")
    buf = io.BytesIO()
    qr.save(
        buf,
        kind="svg",
        scale=10,
        dark="#1f1e1c",
        xmldecl=False,
        svgns=True,
        title=url,
    )
    return buf.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group()
    g.add_argument(
        "--check",
        action="store_true",
        help="verify committed svgs match canonical output (default)",
    )
    g.add_argument(
        "--write", action="store_true", help="regenerate and write svgs to public/images/qr/"
    )
    args = parser.parse_args()
    write_mode = args.write
    # default to --check when neither flag given
    if not args.write and not args.check:
        args.check = True

    if write_mode:
        QR_DIR.mkdir(parents=True, exist_ok=True)
        for stem, url in URLS.items():
            path = QR_DIR / f"{stem}.svg"
            data = render(url)
            path.write_bytes(data)
            print(f"  wrote {path.relative_to(ROOT)}  ({len(data)} bytes, {url})")
        print(f"OK: generate_qr — wrote {len(URLS)} qr svg(s) to {QR_DIR.relative_to(ROOT)}")
        return 0

    # --check
    drift = []
    missing = []
    for stem, url in URLS.items():
        path = QR_DIR / f"{stem}.svg"
        canonical = render(url)
        if not path.exists():
            missing.append((stem, url))
            continue
        if path.read_bytes() != canonical:
            drift.append((stem, url))
    if missing:
        print(f"FAIL: generate_qr — {len(missing)} missing svg(s):")
        for stem, url in missing:
            print(f"  ✗ {stem}.svg  (url: {url})")
    if drift:
        print(f"FAIL: generate_qr — {len(drift)} committed svg(s) drift from canonical output:")
        for stem, url in drift:
            print(f"  ✗ {stem}.svg  (url: {url})")
    if missing or drift:
        print("fix: run `python3 tools/generate_qr.py --write` then commit the regenerated svgs.")
        return 1
    print(f"OK: generate_qr — {len(URLS)} qr svg(s) match canonical output")
    return 0


if __name__ == "__main__":
    sys.exit(main())
