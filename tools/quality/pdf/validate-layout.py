#!/usr/bin/env python3
"""validate-layout.py — publication-layout gate for README.pdf.

Parses a rendered PDF with PyMuPDF and fails on layout defects that paged.js
can still emit even with break-inside rules in place:

  ERROR (fail the build)
    - text/text collisions   two text blocks overlapping enough to obscure each
                             other (a card landing on the block beneath it)
    - edge clipping          a text block bleeding off the physical page edge
                             (content pushed outside the printable area)

  WARN (reported; fail only with --strict)
    - orphan heading         a sub-heading left as the last block on a page,
                             divorced from the body it introduces
    - isolated caption       a small italic fragment opening a page alone,
                             likely a caption split from its figure

Page furniture (running head / folio in the @page margin boxes) is ignored.

Usage:
    python3 tools/pdf/validate-layout.py [README.pdf] [--strict] [--json]

Exit 0 = clean (no errors; no warns under --strict). Exit 1 = defects. Exit 2 =
could not run (missing file or PyMuPDF).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover - environment guard
    sys.stderr.write(
        "validate-layout: PyMuPDF (fitz) is required.\n"
        "  install: python3 -m pip install --break-system-packages pymupdf\n"
    )
    sys.exit(2)

# ── A4 geometry, in points (1mm = 72/25.4 pt). Mirrors print-paged.css @page. ──
MM = 72.0 / 25.4
PAGE_W = 210 * MM
PAGE_H = 297 * MM
MARGIN_TOP = 18 * MM
MARGIN_BOTTOM = 15 * MM
MARGIN_LEFT = 24 * MM  # --m-inner (label-rail side)
MARGIN_RIGHT = 20 * MM  # --m-outer

# physical-bleed tolerance: text closer than this to a sheet edge is clipped.
EDGE_TOL = 6.0
# vertical band that holds @page furniture; text here is the running head/folio.
FURNITURE_TOP = MARGIN_TOP - 2.0
FURNITURE_BOTTOM = PAGE_H - MARGIN_BOTTOM + 2.0

# overlap thresholds. Tight label/sub-label stacking inside a card overlaps a
# few points vertically by design; a genuine card-on-content collision overlaps
# heavily on BOTH axes. Require a substantial overlap on each axis so the former
# never trips and the latter always does.
OVERLAP_MIN_PT = 8.0  # min intersection on BOTH axes
OVERLAP_MIN_FRAC = 0.25  # min intersection area / smaller-block area

# heading detection (PDF points; CSS px ≈ 0.75pt at 96dpi).
HEADING_MIN_PT = 12.0  # t-h3 (18px) and up
HEADING_MAX_PT = 30.0  # exclude full-page opener h1 (54px ≈ 40pt)
CAPTION_MAX_PT = 8.2  # .cap (9.5px ≈ 7.1pt) and similar small italics


def _rects_overlap(a, b):
    """Intersection (w, h) of two fitz.Rect-like (x0,y0,x1,y1) tuples."""
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    return ix, iy


def _area(r):
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def _block_text(block):
    out = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            out.append(span.get("text", ""))
    return "".join(out).strip()


def _block_max_size(block):
    sizes = [
        span.get("size", 0.0) for line in block.get("lines", []) for span in line.get("spans", [])
    ]
    return max(sizes) if sizes else 0.0


def _block_is_italic(block):
    flags = [
        span.get("flags", 0) for line in block.get("lines", []) for span in line.get("spans", [])
    ]
    # PyMuPDF flag bit 1 (value 2) marks italic.
    return bool(flags) and all(f & 2 for f in flags)


def _is_furniture(bbox):
    """True for running head / folio living in the @page margin boxes."""
    return bbox[3] <= FURNITURE_TOP or bbox[1] >= FURNITURE_BOTTOM


def analyse(path: pathlib.Path):
    doc = fitz.open(path)
    findings = []  # (severity, page_no, kind, message)

    for pno, page in enumerate(doc, start=1):
        raw = page.get_text("dict").get("blocks", [])
        text_blocks = []
        for b in raw:
            if b.get("type", 0) != 0:  # 0 = text
                continue
            txt = _block_text(b)
            if not txt:
                continue
            bbox = tuple(b["bbox"])
            if _is_furniture(bbox):
                continue
            text_blocks.append(
                {
                    "bbox": bbox,
                    "text": txt,
                    "size": _block_max_size(b),
                    "italic": _block_is_italic(b),
                }
            )

        # ── edge clipping ──────────────────────────────────────────────
        for blk in text_blocks:
            x0, y0, x1, y1 = blk["bbox"]
            if x0 < EDGE_TOL or x1 > PAGE_W - EDGE_TOL or y0 < EDGE_TOL or y1 > PAGE_H - EDGE_TOL:
                findings.append(
                    (
                        "ERROR",
                        pno,
                        "edge-clip",
                        f"text bleeds off the page edge: "
                        f"{blk['text'][:50]!r} at "
                        f"({x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f})",
                    )
                )

        # ── text/text collisions ───────────────────────────────────────
        for i in range(len(text_blocks)):
            for j in range(i + 1, len(text_blocks)):
                a, b = text_blocks[i]["bbox"], text_blocks[j]["bbox"]
                ix, iy = _rects_overlap(a, b)
                if ix <= OVERLAP_MIN_PT or iy <= OVERLAP_MIN_PT:
                    continue
                inter = ix * iy
                smaller = min(_area(a), _area(b)) or 1.0
                if inter / smaller < OVERLAP_MIN_FRAC:
                    continue
                findings.append(
                    (
                        "ERROR",
                        pno,
                        "collision",
                        f"text blocks overlap "
                        f"({ix:.0f}×{iy:.0f}pt): "
                        f"{text_blocks[i]['text'][:32]!r} ✕ "
                        f"{text_blocks[j]['text'][:32]!r}",
                    )
                )

        if not text_blocks:
            continue
        ordered = sorted(text_blocks, key=lambda b: b["bbox"][1])

        # ── orphan heading: a sub-heading is the last block on the page ──
        last = ordered[-1]
        if HEADING_MIN_PT <= last["size"] <= HEADING_MAX_PT and len(ordered) > 1:
            findings.append(
                (
                    "WARN",
                    pno,
                    "orphan-heading",
                    f"heading ends the page with no following body: {last['text'][:50]!r}",
                )
            )

        # ── isolated caption: a small italic fragment opens the page ─────
        first = ordered[0]
        if first["italic"] and first["size"] <= CAPTION_MAX_PT and len(first["text"]) < 200:
            findings.append(
                (
                    "WARN",
                    pno,
                    "isolated-caption",
                    f"small italic fragment opens the page (caption split from "
                    f"its figure?): {first['text'][:50]!r}",
                )
            )

    doc.close()
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate README.pdf page layout.")
    ap.add_argument("pdf", nargs="?", default="README.pdf")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    path = pathlib.Path(args.pdf)
    if not path.is_file():
        sys.stderr.write(f"validate-layout: no such file: {path}\n")
        return 2

    findings = analyse(path)
    errors = [f for f in findings if f[0] == "ERROR"]
    warns = [f for f in findings if f[0] == "WARN"]

    if args.json:
        print(
            json.dumps(
                {
                    "pdf": str(path),
                    "errors": len(errors),
                    "warnings": len(warns),
                    "findings": [
                        {"severity": s, "page": p, "kind": k, "message": m}
                        for (s, p, k, m) in findings
                    ],
                },
                indent=2,
            )
        )
    else:
        for sev, pno, kind, msg in findings:
            print(f"  p{pno:<3} {sev:<5} {kind}: {msg}")
        if not findings:
            print(f"validate-layout: {path.name} clean — no layout defects.")
        else:
            print(
                f"validate-layout: {len(errors)} error(s), {len(warns)} warning(s) in {path.name}."
            )

    if errors or (args.strict and warns):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
