#!/usr/bin/env python3
"""build_github_social_preview.py — render the GitHub social preview card.

Renders a single 1280x640 PNG in the print register of README.pdf
(warm paper, iron ink, oxblood accent) using the site's licensed fonts
converted WOFF2 → TTF in-memory via fontTools. Deterministic output,
no external assets.

Output: metadata/social-preview/trentpower-fr-github-social.png

The PNG is committed so the artefact stays available without the
licensed fonts. Upload manually: GitHub → Settings → General →
Social preview (see metadata/social-preview/README.md).

Run from anywhere in the repository:
    python3 tools/visual/build_github_social_preview.py
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
from paths import PUBLIC_DIR, REPO_ROOT

FONT_DIR = PUBLIC_DIR / "fonts"
OUT_DIR = REPO_ROOT / "metadata" / "social-preview"
OUT_PATH = OUT_DIR / "trentpower-fr-github-social.png"

# visual tokens — the README.pdf print register, not the screen palette.
W, H = 1280, 640
PAPER = (250, 247, 240)  # warm paper      #faf7f0
INK = (33, 31, 28)  # iron ink        #211f1c
INK_MUTED = (109, 104, 98)  # muted ink       #6d6862
OXBLOOD = (110, 26, 20)  # restrained accent #6e1a14

PAD_X = 104
PAD_Y = 96


def load_woff2(path: pathlib.Path, size: int) -> ImageFont.FreeTypeFont:
    """Convert a .woff2 file to a TTF byte stream and load with PIL."""
    f = TTFont(path)
    f.flavor = None
    buf = io.BytesIO()
    f.save(buf)
    buf.seek(0)
    return ImageFont.truetype(buf, size=size)


def require_fonts() -> None:
    needed = [
        "signifier-light.woff2",
        "soehne-mono-kraftig.woff2",
        "soehne-mono-buch.woff2",
    ]
    missing = [n for n in needed if not (FONT_DIR / n).is_file()]
    if missing:
        print(f"missing licensed fonts in {FONT_DIR.relative_to(REPO_ROOT)}: {', '.join(missing)}")
        print("run `python3 tools/build/fetch_licensed_fonts.py` first")
        raise SystemExit(1)


def text_size(draw: ImageDraw.ImageDraw, txt: str, font) -> tuple[int, int]:
    box = draw.textbbox((0, 0), txt, font=font)
    return box[2] - box[0], box[3] - box[1]


def render() -> None:
    title_font = load_woff2(FONT_DIR / "signifier-light.woff2", 110)
    kicker_font = load_woff2(FONT_DIR / "soehne-mono-kraftig.woff2", 24)
    trust_font = load_woff2(FONT_DIR / "soehne-mono-buch.woff2", 28)
    sub_font = load_woff2(FONT_DIR / "soehne-mono-buch.woff2", 24)

    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    # top-left: mark (mono, uppercase, oxblood) + short hairline.
    kicker = "TRENT POWER"
    d.text((PAD_X, PAD_Y), kicker, font=kicker_font, fill=OXBLOOD)
    _, kh = text_size(d, kicker, kicker_font)
    rule_y = PAD_Y + kh + 16
    d.line([(PAD_X, rule_y), (PAD_X + 60, rule_y)], fill=INK_MUTED, width=1)

    # top-right: repository host (mono, muted), on the kicker line.
    host = "github.com/trentpower/trentpower.fr"
    hw, _ = text_size(d, host, sub_font)
    d.text((W - PAD_X - hw, PAD_Y), host, font=sub_font, fill=INK_MUTED)

    # title — large editorial serif, optically centred.
    title = "trentpower.fr"
    d.text((PAD_X, int(H * 0.40) - title_font.size // 2), title, font=title_font, fill=INK)

    # trust line + subtitle, bottom-left, stacked.
    trust = "Static · Signed · Source-verifiable"
    sub = "A bilingual personal publication system"
    _, sh = text_size(d, sub, sub_font)
    _, th = text_size(d, trust, trust_font)
    sub_y = H - PAD_Y - sh
    trust_y = sub_y - th - 22
    d.text((PAD_X, trust_y), trust, font=trust_font, fill=INK)
    d.text((PAD_X, sub_y), sub, font=sub_font, fill=INK_MUTED)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img.save(OUT_PATH, format="PNG", optimize=True)
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)} ({OUT_PATH.stat().st_size // 1024} KB)")


def main() -> int:
    require_fonts()
    render()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
