#!/usr/bin/env python3
"""validate-content.py — semantic gate for the README PDF.

The layout gate (validate-layout.py) proves nothing overlaps or clips.
This gate proves the document tells the truth and survives export:

  charts
    - every .bar__fill carries --v / --m custom properties (no
      hand-tuned width: anywhere on a fill)
    - the --v datum equals the printed value beside the bar
    - the --m datum equals the group maximum
    - the "checks by category" chart and stat band match the live
      registry in tools/lib/checks.py
    - the "public folder" chart and prose totals match
      `git ls-files public/` at validation time

  assets
    - every <img src> in readme.html resolves on disk
    - the exported PDF embeds at least as many raster images as the
      HTML references (a missing asset exports as an empty box)

  typography
    - canonical display headings extract from the PDF with their
      spaces intact (the joined-words regression: "Whatisinside")
    - no em dash anywhere in readme.html copy

  edition
    - every "edition YYYY-MM-DD" mention in readme.html and
      print-paged.css equals the canonical edition in
      tools/config/identity_canonical.json

Usage:
    python3 tools/quality/pdf/validate-content.py [README.pdf] [readme.html]

Exit 0 = clean. Exit 1 = defects. Exit 2 = could not run.
"""

from __future__ import annotations

import collections
import json
import pathlib
import re
import subprocess
import sys

_TOOLS = pathlib.Path(__file__).resolve().parents[2]
REPO = _TOOLS.parent
sys.path.insert(0, str(_TOOLS / "lib"))

# canonical headings that must survive export with spaces intact.
EXPECTED_HEADINGS = [
    "What is inside",
    "What trentpower.fr is",
    "From words to pages",
    "One command, ten stages",
    "What may ship",
    "Proof anyone can re-run",
    "What the browser is told to enforce",
    "The deploy routine, and recovery",
    "Going public, stated plainly",
]

# label → file-extension group for the public-folder chart.
EXT_GROUPS = {
    "source mirrors .txt": (".txt",),
    "signatures .sig": (".sig",),
    "data .json": (".json",),
    "checksums .sha256": (".sha256",),
    "archives .zip / .gz": (".zip", ".gz"),
    "pages .html": (".html",),
}

BAR_RE = re.compile(
    r'<div class="bar"><span class="bar__l">(?P<label>[^<]+)</span>'
    r'<span class="bar__track"><span class="bar__fill[^"]*"'
    r' style="(?P<style>[^"]*)"></span></span>'
    r'<span class="bar__v">(?P<value>[^<]+)</span></div>'
)


def _normalise(text: str) -> str:
    for k, v in {"‑": "-", " ": " ", " ": " ", "·": "·"}.items():
        text = text.replace(k, v)
    return " ".join(text.split())


def _public_histogram() -> tuple[collections.Counter, int, int]:
    files = subprocess.run(
        ["git", "ls-files", "public/"], capture_output=True, text=True, cwd=REPO, check=True
    ).stdout.split()
    ext = collections.Counter(pathlib.Path(f).suffix.lower() for f in files)
    frozen = sum(1 for f in files if re.match(r"public/integrity/releases/[^/]+/", f))
    return ext, len(files), frozen


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    pdf_path = pathlib.Path(argv[0]) if argv else REPO / "README.pdf"
    html_path = pathlib.Path(argv[1]) if len(argv) > 1 else REPO / "docs" / "pdf" / "readme.html"
    if not pdf_path.is_file() or not html_path.is_file():
        sys.stderr.write(f"validate-content: missing {pdf_path} or {html_path}\n")
        return 2

    try:
        import fitz  # PyMuPDF
    except ImportError:
        sys.stderr.write(
            "validate-content: PyMuPDF (fitz) is required.\n"
            "  install: python3 -m pip install --break-system-packages pymupdf\n"
        )
        return 2

    html = html_path.read_text(encoding="utf-8")
    fails: list[str] = []

    # ── em dashes ────────────────────────────────────────────────────
    if "—" in html:
        n = html.count("—")
        fails.append(f"readme.html contains {n} em dash(es); the document voice forbids them")

    # ── edition coherence ────────────────────────────────────────────
    with open(_TOOLS / "config" / "identity_canonical.json", encoding="utf-8") as f:
        edition = json.load(f)["edition"]
    css = (html_path.parent / "print-paged.css").read_text(encoding="utf-8")
    for src_name, text in (("readme.html", html), ("print-paged.css", css)):
        for m in re.finditer(r"[Ee]dition[^0-9<]{0,3}(\d{4}.\d{2}.\d{2})", _normalise(text)):
            if m.group(1) != edition:
                fails.append(f"{src_name}: stale edition mention {m.group(1)!r} != {edition!r}")

    # ── bars: data-driven and internally coherent ────────────────────
    if re.search(r'class="bar__fill[^"]*" style="[^"]*width\s*:', html):
        fails.append("a .bar__fill carries a hand-tuned width:; bars must be --v/--m driven")
    groups: dict[str, list[tuple[str, int, int]]] = {}
    bars_blocks = re.split(r'<div class="bars[^"]*">', html)[1:]
    for block in bars_blocks:
        rows = []
        for m in BAR_RE.finditer(block):
            style = m.group("style")
            v = re.search(r"--v:\s*(\d+)", style)
            mx = re.search(r"--m:\s*(\d+)", style)
            val = int(m.group("value"))
            if not (v and mx):
                fails.append(f"bar {m.group('label')!r}: missing --v/--m custom properties")
                continue
            rows.append((m.group("label"), int(v.group(1)), int(mx.group(1)), val))
        if not rows:
            continue
        first = rows[0][0]
        groups[first] = [(lbl, v, val) for (lbl, v, mx, val) in rows]
        true_max = max(v for (_, v, _mx, _val) in rows)
        for lbl, v, mx, val in rows:
            if v != val:
                fails.append(f"bar {lbl!r}: --v {v} != printed value {val}")
            if mx != true_max:
                fails.append(f"bar {lbl!r}: --m {mx} != group maximum {true_max}")

    # ── public-folder chart vs the repository ────────────────────────
    ext, total, frozen = _public_histogram()
    folder = groups.get("source mirrors .txt")
    if folder is None:
        fails.append("public-folder chart not found in readme.html")
    else:
        for lbl, v, _val in folder:
            want = sum(ext.get(e, 0) for e in EXT_GROUPS.get(lbl, ()))
            if not EXT_GROUPS.get(lbl):
                fails.append(f"public-folder chart: unknown row label {lbl!r}")
            elif v != want:
                fails.append(f"public-folder chart {lbl!r}: shows {v}, git ls-files says {want}")
    m = re.search(r'Of <span class="tnum">(\d+)</span> published files', html)
    if m and int(m.group(1)) != total:
        fails.append(f"prose says {m.group(1)} published files, git ls-files says {total}")
    m = re.search(r'<span class="tnum">(\d+)</span> of them belong to frozen', html)
    if m and int(m.group(1)) != frozen:
        fails.append(f"prose says {m.group(1)} frozen-archive files, git ls-files says {frozen}")

    # ── checks chart + stat band vs the live registry ────────────────
    import checks as _checks

    reg = _checks.REGISTRY
    cats = collections.Counter(c.category.name for c in reg)
    tiers = collections.Counter(c.tier.name for c in reg)
    cat_truth = {
        "Security (SEC)": cats.get("SECURITY", 0),
        "Correctness (COR)": cats.get("CORRECTNESS", 0),
        "Quality (QUAL)": cats.get("QUALITY", 0),
    }
    checks_chart = groups.get("Security (SEC)")
    if checks_chart is None:
        fails.append("checks-by-category chart not found in readme.html")
    else:
        for lbl, v, _val in checks_chart:
            want = cat_truth.get(lbl)
            if want is None:
                fails.append(f"checks chart: unknown row label {lbl!r}")
            elif v != want:
                fails.append(f"checks chart {lbl!r}: shows {v}, registry says {want}")
    band = re.findall(
        r'<div class="stat__n[^"]*">(\d+)</div><div class="stat__l">'
        r"(Checks total|Blocking|Advisory)</div>",
        html,
    )
    band_truth = {
        "Checks total": len(reg),
        "Blocking": tiers.get("BLOCKING", 0),
        "Advisory": tiers.get("ADVISORY", 0),
    }
    for shown, lbl in band:
        if int(shown) != band_truth[lbl]:
            fails.append(f"stat band {lbl!r}: shows {shown}, registry says {band_truth[lbl]}")

    # ── image assets ─────────────────────────────────────────────────
    img_srcs = re.findall(r'<img src="([^"]+)"', html)
    for src in img_srcs:
        if not (html_path.parent / src).is_file():
            fails.append(f"readme.html references missing asset: {src}")

    doc = fitz.open(pdf_path)
    embedded = sum(len(page.get_images(full=True)) for page in doc)
    if embedded < len(img_srcs):
        fails.append(
            f"PDF embeds {embedded} raster image(s) but readme.html references "
            f"{len(img_srcs)}; an asset failed to export"
        )

    # ── heading extraction (joined-words regression) ─────────────────
    full_text = _normalise("\n".join(page.get_text() for page in doc))
    doc.close()
    for heading in EXPECTED_HEADINGS:
        if heading not in full_text:
            squashed = heading.replace(" ", "")
            how = "extracts with collapsed spaces" if squashed in full_text else "not found"
            fails.append(f"heading {heading!r} {how} in exported PDF")

    if fails:
        print(f"validate-content: {len(fails)} defect(s):")
        for f_ in fails:
            print(f"  ✗ {f_}")
        return 1
    print(
        f"validate-content: {pdf_path.name} clean — charts match repository data, "
        f"assets embedded, headings intact."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
