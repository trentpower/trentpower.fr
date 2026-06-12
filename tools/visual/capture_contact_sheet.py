#!/usr/bin/env python3
"""capture_contact_sheet.py — visual QA contact sheets for the public site.

Serves public/ locally, captures representative pages (both languages,
desktop + mobile, light + dark) and assembles labelled contact sheets.
A publication proofing tool: the sheets help a human answer "does this
still feel like one authored product?". They are not a replacement for
accessibility or functional tests, and never a deploy gate.

Outputs (local-only, gitignored):
    reports/visual/contact-sheet-desktop-light.png
    reports/visual/contact-sheet-desktop-dark.png
    reports/visual/contact-sheet-mobile-light.png
    reports/visual/contact-sheet-mobile-dark.png

Requires the optional Playwright dependency (chromium). When it is not
installed the script prints a note and exits 0 so callers never fail.

Run from anywhere in the repository:
    python3 tools/visual/capture_contact_sheet.py
"""

import functools
import http.server
import io
import sys
import threading

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
from paths import PUBLIC_DIR, REPO_ROOT

OUT_DIR = REPO_ROOT / "reports" / "visual"

# representative pages — root gate, both language trees, machine
# surfaces and error states. label, then path relative to public/.
PAGES = [
    ("root gate", ""),
    ("en home", "en-au/"),
    ("en privacy", "en-au/privacy/"),
    ("en security", "en-au/security/"),
    ("en verify", "en-au/verify/"),
    ("en integrity", "en-au/integrity/"),
    ("en source view", "en-au/source/view/"),
    ("fr home", "fr/"),
    ("fr confidentialite", "fr/confidentialite/"),
    ("fr securite", "fr/securite/"),
    ("fr verifier", "fr/verifier/"),
    ("fr integrite", "fr/integrite/"),
    ("fr source voir", "fr/source/voir/"),
    ("local storage", "local/"),
    ("documentation", "documentation/"),
    ("403", "403.html"),
    ("404", "404.html"),
    ("500", "500.html"),
    ("maintenance", "maintenance.html"),
]

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900},
    "mobile": {"width": 390, "height": 844},
}
SCHEMES = ("light", "dark")
THUMB_SCALE = {"desktop": 0.30, "mobile": 0.50}
COLUMNS = {"desktop": 3, "mobile": 5}
MARGIN = 24
LABEL_H = 28

class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve_public() -> tuple[http.server.ThreadingHTTPServer, str]:
    handler = functools.partial(_QuietHandler, directory=str(PUBLIC_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


def assemble_sheet(Image, ImageDraw, captures, device: str, scheme: str) -> None:
    scale = THUMB_SCALE[device]
    cols = COLUMNS[device]
    vw, vh = VIEWPORTS[device]["width"], VIEWPORTS[device]["height"]
    cell_w, cell_h = int(vw * scale), int(vh * scale)
    rows = (len(captures) + cols - 1) // cols
    sheet_w = MARGIN + cols * (cell_w + MARGIN)
    sheet_h = MARGIN + rows * (cell_h + LABEL_H + MARGIN)
    bg = (250, 247, 240) if scheme == "light" else (27, 25, 22)
    fg = (33, 31, 28) if scheme == "light" else (240, 234, 224)

    sheet = Image.new("RGB", (sheet_w, sheet_h), bg)
    d = ImageDraw.Draw(sheet)
    for i, (label, png_bytes) in enumerate(captures):
        col, row = i % cols, i // cols
        x = MARGIN + col * (cell_w + MARGIN)
        y = MARGIN + row * (cell_h + LABEL_H + MARGIN)
        thumb = Image.open(io.BytesIO(png_bytes)).convert("RGB").resize(
            (cell_w, cell_h), Image.LANCZOS
        )
        sheet.paste(thumb, (x, y))
        d.rectangle([x, y, x + cell_w - 1, y + cell_h - 1], outline=fg, width=1)
        d.text((x, y + cell_h + 8), label, fill=fg)

    out = OUT_DIR / f"contact-sheet-{device}-{scheme}.png"
    sheet.save(out, format="PNG", optimize=True)
    print(f"  wrote {out.relative_to(REPO_ROOT)} ({out.stat().st_size // 1024} KB)")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed — visual QA skipped (pip install playwright; playwright install chromium)")
        return 0
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Pillow not installed — visual QA skipped")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    server, base = serve_public()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for device, viewport in VIEWPORTS.items():
                for scheme in SCHEMES:
                    context = browser.new_context(viewport=viewport, color_scheme=scheme)
                    page = context.new_page()
                    captures = []
                    for label, rel in PAGES:
                        page.goto(base + rel, wait_until="networkidle")
                        captures.append((label, page.screenshot()))
                    context.close()
                    assemble_sheet(Image, ImageDraw, captures, device, scheme)
            browser.close()
    finally:
        server.shutdown()

    print(f"OK: contact sheets in {OUT_DIR.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
