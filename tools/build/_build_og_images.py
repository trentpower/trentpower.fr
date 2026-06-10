#!/usr/bin/env python3
"""build_og_images.py — generate 1200x630 OG images for trust pages.

Uses the site's actual fonts (Newsreader serif, IBM Plex Mono) by
converting WOFF2 → TTF in-memory via fontTools, so previews share the
visual identity of the screen pages. No external assets, deterministic
output, runs in ~1s per image.

Output: public/images/og/{home,privacy,verify,integrity,source,security,releases}-og.png

Run from the repo root (resolves paths via parent/public):
    python3 tools/build_og_images.py
"""

import io
import pathlib
import sys

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

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
from paths import PUBLIC_DIR as ROOT

FONT_DIR = ROOT / "fonts"
OUT_DIR = ROOT / "images" / "social"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# visual tokens — match the screen design system.
W, H = 1200, 630
BG = (246, 244, 240)  # --bg : warm ivory  #f6f4f0
FG = (31, 30, 28)  # --fg : near-black  #1f1e1c
FG2 = (92, 89, 85)  # --fg2: muted body  #5c5955
FG3 = (112, 107, 102)  # --fg3: hairline    #706b66
AC = (181, 74, 40)  # --ac : oxblood     #b54a28

# layout
PAD_X = 96
PAD_Y = 96


def load_woff2(path: pathlib.Path, size: int) -> ImageFont.FreeTypeFont:
    """Convert a .woff2 file to a TTF byte stream and load with PIL."""
    f = TTFont(path)
    f.flavor = None
    buf = io.BytesIO()
    f.save(buf)
    buf.seek(0)
    return ImageFont.truetype(buf, size=size)


# Pre-load font weights at the sizes we use. match the screen identity
# via the canonical (unversioned) @font-face files served at runtime:
# Signifier-Light for the title (editorial serif, masthead family),
# söhne mono kräftig for the kicker (mid-weight mono, oxblood), and
# söhne mono buch for the trust line and host (book-weight mono).
TITLE_FONT = load_woff2(FONT_DIR / "signifier-light.woff2", 96)
TITLE_FONT_S = load_woff2(FONT_DIR / "signifier-light.woff2", 76)
KICKER_FONT = load_woff2(FONT_DIR / "soehne-mono-kraftig.woff2", 22)
TRUST_FONT = load_woff2(FONT_DIR / "soehne-mono-buch.woff2", 24)


def text_size(draw: ImageDraw.ImageDraw, txt: str, font) -> tuple[int, int]:
    box = draw.textbbox((0, 0), txt, font=font)
    return box[2] - box[0], box[3] - box[1]


def render_image(
    out_path: pathlib.Path, title: str, trust_line: str = "Static · Signed · Inspectable"
):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Top-left: trent power mark (mono, uppercase, oxblood, small).
    kicker = "TRENT POWER"
    d.text((PAD_X, PAD_Y), kicker, font=KICKER_FONT, fill=AC)

    # hairline below the mark
    kw, kh = text_size(d, kicker, KICKER_FONT)
    rule_y = PAD_Y + kh + 14
    d.line([(PAD_X, rule_y), (PAD_X + 60, rule_y)], fill=FG3, width=1)

    # title — large serif, multi-line if needed (manual wrap on " · ").
    # pick the smaller font if the title is wide enough to risk overflow.
    font = TITLE_FONT
    tw, _ = text_size(d, title, font)
    if tw > W - 2 * PAD_X:
        font = TITLE_FONT_S
        tw, _ = text_size(d, title, font)
    # vertical centering: place around y = h * 0.45
    th = font.size + 12  # rough line height
    title_y = int(H * 0.42)
    # allow wrap on " & " for long titles
    if tw > W - 2 * PAD_X and " & " in title:
        a, b = title.split(" & ", 1)
        a += " &"
        d.text((PAD_X, title_y - th // 2 - 6), a, font=font, fill=FG)
        d.text((PAD_X, title_y + th // 2 + 6), b, font=font, fill=FG)
    else:
        d.text((PAD_X, title_y - th // 2), title, font=font, fill=FG)

    # trust line at bottom-left.
    if trust_line:
        d.text((PAD_X, H - PAD_Y - 24), trust_line, font=TRUST_FONT, fill=FG2)

    # Bottom-right: hairline + canonical host (mono, fg3).
    host = "trentpower.fr"
    hw, hh = text_size(d, host, TRUST_FONT)
    hx = W - PAD_X - hw
    hy = H - PAD_Y - hh
    d.text((hx, hy), host, font=TRUST_FONT, fill=FG3)

    img.save(out_path, format="PNG", optimize=True)
    print(f"  wrote {out_path.relative_to(ROOT)} ({out_path.stat().st_size // 1024} KB)")


PAGES = [
    ("home-og.png", "Client Strategy & Growth Systems"),
    ("privacy-og.png", "Privacy & Trust"),
    ("verify-og.png", "Verify this page"),
    ("integrity-og.png", "Integrity"),
    ("source-og.png", "Source mirrors"),
    ("security-og.png", "Security & Threat Model"),
    ("releases-og.png", "Releases"),
]


def main() -> int:
    for name, title in PAGES:
        render_image(OUT_DIR / name, title)
    print(f"OK: rendered {len(PAGES)} OG images to {OUT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
