#!/usr/bin/env python3
"""generate_editorial_binaries.py — render the DOCX and PDF review
artefacts from the Markdown and HTML inputs.

DOCX: pandoc converts the editorial Markdown into a Word document.
PDF:  headless Chromium prints the styled HTML to a print-quality PDF
      (preserves typography and table layout).

Both renderers are external binaries (`pandoc`, `chromium`); if either
is unavailable the corresponding output is skipped with a calm note.
The build pipeline treats this step as non-blocking.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
EDITORIAL = ROOT / "public" / "editorial"


# multilingual + English-only variant pairs. each row maps a markdown
# source to a docx target and an html source to a pdf target.
def _read_edition() -> str:
    canon = ROOT / "tools" / "config" / "identity_canonical.json"
    if canon.is_file():
        import json

        try:
            return json.loads(canon.read_text(encoding="utf-8")).get("edition", "")
        except Exception:
            return ""
    return ""


_EDITION = _read_edition()


# system b (extract_editorial_copy.py + generate_editorial_review.py) was
# retired; only the copywriter-facing review built from the canonical
# content/en/ YAML by build_copy_review.py remains.
VARIANTS = [
    {
        "label": "copywriter-yaml",
        "title": "Copy Review · YAML sources · English",
        "src_html": EDITORIAL / "copy-review.html",
        "out_docx": EDITORIAL / "copy-review.docx",
        "out_pdf": EDITORIAL / "copy-review.pdf",
    },
]


REFERENCE_DOCX = ROOT / "tools" / "build" / "assets" / "editorial-review-reference.docx"


# ── chromium pdf folio templates ──────────────────────────────────
# chromium's --header-template / --footer-template accept a small
# self-contained html snippet rendered on every printed page. the
# special spans .title, .pagenumber, .totalpages are replaced at
# print time. css support inside is limited; we keep it minimal and
# rely on inline styles for cross-platform consistency.


def header_template(title: str) -> str:
    # tiny restrained banner: site / document / edition. sits above
    # the page body within the @page top margin reserved by the
    # styled html's @page rule.
    return (
        '<div style="font-family: -apple-system, sans-serif; '
        "font-size: 8pt; color: #9A9388; width: 100%; padding: 0 22mm; "
        'box-sizing: border-box; letter-spacing: 0.06em;">'
        '<div style="display: flex; justify-content: space-between; '
        'align-items: baseline;">'
        f"<span>trentpower.fr</span>"
        f'<span style="font-style: italic;">{title}</span>'
        f"<span>Edition {_EDITION}</span>"
        "</div>"
        "</div>"
    )


def footer_template() -> str:
    return (
        '<div style="font-family: -apple-system, sans-serif; '
        "font-size: 8pt; color: #9A9388; width: 100%; padding: 0 22mm; "
        'box-sizing: border-box; letter-spacing: 0.06em;">'
        '<div style="display: flex; justify-content: space-between; '
        'align-items: baseline;">'
        '<span style="text-transform: uppercase; letter-spacing: 0.18em;">'
        "Editorial &mdash; Confidential</span>"
        "<span>"
        '<span class="pageNumber"></span> / <span class="totalPages"></span>'
        "</span>"
        "</div>"
        "</div>"
    )


def render_docx(src_html: pathlib.Path, out_docx: pathlib.Path, label: str) -> bool:
    """Convert the styled editorial HTML into DOCX via pandoc, applying
    the TP-* paragraph styles defined in the reference docx. The HTML
    carries `custom-style="TP …"` attributes that pandoc maps onto
    those styles."""
    pandoc = shutil.which("pandoc")
    if pandoc is None:
        print(f"  ⚠ pandoc not found — DOCX [{label}] generation skipped")
        return False
    if not src_html.is_file():
        print(f"  ⚠ {src_html} missing — DOCX [{label}] generation skipped")
        return False
    EDITORIAL.mkdir(parents=True, exist_ok=True)
    cmd = [
        pandoc,
        str(src_html),
        "-f",
        "html+native_divs+native_spans",
        "-t",
        "docx",
        "-o",
        str(out_docx),
        "--toc",
        "--toc-depth=2",
        "--standalone",
    ]
    if REFERENCE_DOCX.is_file():
        cmd.extend(["--reference-doc", str(REFERENCE_DOCX)])
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"  ⚠ pandoc [{label}] failed: {e.stderr.strip()[:240]}")
        return False
    print(f"  → {out_docx.relative_to(ROOT)} ({out_docx.stat().st_size // 1024} KB)")
    return True


def render_pdf(src_html: pathlib.Path, out_pdf: pathlib.Path, label: str, title: str) -> bool:
    """Render the styled HTML to PDF via Playwright + system Chromium.
    Playwright's page.pdf() supports header_template / footer_template,
    which Chromium's bare --print-to-pdf CLI does not."""
    if not src_html.is_file():
        print(f"  ⚠ {src_html} missing — PDF [{label}] generation skipped")
        return False
    chrom = (
        shutil.which("chromium")
        or shutil.which("chromium-browser")
        or shutil.which("google-chrome")
    )
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"  ⚠ playwright not available — PDF [{label}] generation skipped")
        return False
    EDITORIAL.mkdir(parents=True, exist_ok=True)
    src_url = src_html.resolve().as_uri()
    try:
        with sync_playwright() as p:
            launch_kwargs = {}
            if chrom is not None:
                launch_kwargs["executable_path"] = chrom
            browser = p.chromium.launch(**launch_kwargs)
            try:
                page = browser.new_page()
                page.goto(src_url, wait_until="load", timeout=60000)
                # the html's @page rule already reserves 24mm/26mm
                # margins; we widen the top/bottom to make room for
                # the running header and folio.
                page.pdf(
                    path=str(out_pdf),
                    format="A4",
                    print_background=True,
                    display_header_footer=True,
                    header_template=header_template(title),
                    footer_template=footer_template(),
                    margin={
                        "top": "30mm",
                        "bottom": "26mm",
                        "left": "22mm",
                        "right": "22mm",
                    },
                    prefer_css_page_size=False,
                )
            finally:
                browser.close()
    except Exception as e:
        print(f"  ⚠ playwright [{label}] failed: {type(e).__name__}: {str(e)[:240]}")
        return False
    if not out_pdf.is_file() or out_pdf.stat().st_size == 0:
        print(f"  ⚠ playwright [{label}] produced no output")
        return False
    print(f"  → {out_pdf.relative_to(ROOT)} ({out_pdf.stat().st_size // 1024} KB)")
    return True


def main() -> int:
    for v in VARIANTS:
        render_docx(v["src_html"], v["out_docx"], v["label"])
        render_pdf(v["src_html"], v["out_pdf"], v["label"], v["title"])
    return 0  # non-blocking either way


if __name__ == "__main__":
    sys.exit(main())
