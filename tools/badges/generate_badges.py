#!/usr/bin/env python3
"""generate_badges.py — render the local SVG trust marks.

Generates every colophon mark plus the proof strip from
metadata/badges/badges.json, deterministically: stable ordering, fixed
geometry, no timestamps, no network, no scripts, no embedded or remote
fonts. Text is set in the system monospace stack so the marks carry no
licence question onto GitHub.

Design contract (Trust Marks badge brief, Option 2 Colophon Marks +
Option 3 Proof Strip): each badge brings its own warm-paper surface and
hairline frame, so a single SVG reads identically on GitHub light and
dark. The marks are descriptive labels, not cryptographic proof.

Usage:
    python3 tools/badges/generate_badges.py            # write SVGs
    python3 tools/badges/generate_badges.py --check    # exit 1 on drift
"""

import json
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
from paths import REPO_ROOT

BADGE_DIR = REPO_ROOT / "metadata" / "badges"
DATA_PATH = BADGE_DIR / "badges.json"

# palette — fixed hex so the mark reads the same on any canvas.
PAPER = "#FAF7F0"
INK = "#211F1C"
INK_SOFT = "#5F5A53"
RULE = "#CFC7B8"
ACCENT = "#6E1A14"
SEAL_PAPER = "#F4ECE5"  # 8% oxblood over paper

MONO = (
    'ui-monospace, SFMono-Regular, &quot;SF Mono&quot;, Menlo, Consolas, '
    '&quot;Liberation Mono&quot;, monospace'
)

# geometry from the brief's sample SVG (96x22 "Signed: PGP").
H = 22
RX = 2
PAD_L = 10
PAD_R = 9
GAP = 8
LABEL_SIZE = 10
LABEL_LS = 0.8
VALUE_SIZE = 11
VALUE_LS = 0.2
BASELINE = 15
SEP_Y = 5.5
SEP_H = 11

DESC = (
    "Descriptive trust label generated locally from repository metadata. "
    "Not cryptographic proof: proof remains in the signed integrity "
    "manifest, source mirrors and release archives."
)


def mono_width(text: str, size: float, letter_spacing: float) -> float:
    """Width of mono text: 0.6em per character plus tracking between
    characters. Reproduces the brief's sample geometry exactly."""
    n = len(text)
    if n == 0:
        return 0.0
    return n * size * 0.6 + (n - 1) * letter_spacing


def esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def colophon_svg(label: str, value: str) -> str:
    label_up = label.upper()
    lw = mono_width(label_up, LABEL_SIZE, LABEL_LS)
    vw = mono_width(value, VALUE_SIZE, VALUE_LS)
    sep_x = PAD_L + lw + GAP
    val_x = sep_x + 1 + GAP
    w = round(val_x + vw + PAD_R)
    title = f"{label}: {value}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{H}" '
        f'viewBox="0 0 {w} {H}" role="img" aria-label="{esc(title)}">\n'
        f"  <title>{esc(title)}</title>\n"
        f"  <desc>{esc(DESC)}</desc>\n"
        f'  <rect x=".5" y=".5" width="{w - 1}" height="{H - 1}" rx="{RX}" '
        f'fill="{PAPER}" stroke="{RULE}"/>\n'
        f'  <rect x="{round(sep_x, 1)}" y="{SEP_Y}" width="1" height="{SEP_H}" '
        f'fill="{ACCENT}" opacity=".85"/>\n'
        f'  <text x="{PAD_L}" y="{BASELINE}" fill="{INK_SOFT}" '
        f'font-family="{MONO}" font-size="{LABEL_SIZE}" '
        f'letter-spacing="{LABEL_LS}">{esc(label_up)}</text>\n'
        f'  <text x="{round(val_x, 1)}" y="{BASELINE}" fill="{INK}" '
        f'font-family="{MONO}" font-size="{VALUE_SIZE}" '
        f'letter-spacing="{VALUE_LS}">{esc(value)}</text>\n'
        f"</svg>\n"
    )


# proof strip geometry.
PS_H = 34
PS_KICKER_SIZE = 6.5
PS_KICKER_LS = 0.85
PS_VALUE_SIZE = 9
PS_VALUE_LS = 0.2
PS_PAD_X = 12
PS_KICKER_BASE = 13
PS_VALUE_BASE = 25


def proof_strip_svg(marks: list[dict], seal: dict) -> str:
    cells = []
    # seal cell.
    seal_w = 44
    x = 0.0
    cells.append(
        f'  <rect x=".5" y=".5" width="{seal_w}" height="{PS_H - 1}" fill="{SEAL_PAPER}"/>\n'
        f'  <text x="{seal_w / 2}" y="17" fill="{ACCENT}" text-anchor="middle" '
        f'font-family="serif" font-size="14">{esc(seal["seal_monogram"])}</text>\n'
        f'  <text x="{seal_w / 2}" y="27" fill="{INK_SOFT}" text-anchor="middle" '
        f'font-family="{MONO}" font-size="4.6" letter-spacing=".6">'
        f"{esc(seal['seal_kicker'])}</text>\n"
        f'  <rect x="{seal_w + 0.5}" y="0" width="1" height="{PS_H}" fill="{RULE}"/>\n'
    )
    x = seal_w + 1
    for i, m in enumerate(marks):
        kicker = m["label"].upper()
        value = m["value"]
        kw = mono_width(kicker, PS_KICKER_SIZE, PS_KICKER_LS)
        vw = mono_width(value, PS_VALUE_SIZE, PS_VALUE_LS)
        cell_w = round(max(kw, vw) + 2 * PS_PAD_X)
        tx = round(x + PS_PAD_X, 1)
        cells.append(
            f'  <text x="{tx}" y="{PS_KICKER_BASE}" fill="{INK_SOFT}" '
            f'font-family="{MONO}" font-size="{PS_KICKER_SIZE}" '
            f'letter-spacing="{PS_KICKER_LS}">{esc(kicker)}</text>\n'
            f'  <text x="{tx}" y="{PS_VALUE_BASE}" fill="{INK}" '
            f'font-family="{MONO}" font-size="{PS_VALUE_SIZE}" '
            f'letter-spacing="{PS_VALUE_LS}">{esc(value)}</text>\n'
        )
        x += cell_w
        if i < len(marks) - 1:
            cells.append(
                f'  <rect x="{round(x, 1)}" y="6" width="1" height="{PS_H - 12}" fill="{RULE}"/>\n'
            )
            x += 1
    w = round(x)
    title = "trentpower.fr trust strip: " + " · ".join(
        f"{m['label']} {m['value']}" for m in marks
    )
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{PS_H}" '
        f'viewBox="0 0 {w} {PS_H}" role="img" aria-label="{esc(title)}">\n'
        f"  <title>{esc(title)}</title>\n"
        f"  <desc>{esc(DESC)}</desc>\n"
        f'  <rect x=".5" y=".5" width="{w - 1}" height="{PS_H - 1}" rx="3" '
        f'fill="{PAPER}" stroke="{RULE}"/>\n'
    )
    return head + "".join(cells) + "</svg>\n"


def render_all() -> dict[str, str]:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for mark in data["marks"]:
        out[mark["filename"]] = colophon_svg(mark["label"], mark["value"])
    readme_marks = [m for m in data["marks"] if m["scope"] == "readme"]
    strip = data["proof_strip"]
    out[strip["filename"]] = proof_strip_svg(readme_marks, strip)
    return out


def main() -> int:
    check = "--check" in sys.argv[1:]
    rendered = render_all()
    stale = []
    for filename, svg in sorted(rendered.items()):
        path = BADGE_DIR / filename
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != svg:
                stale.append(filename)
            continue
        path.write_text(svg, encoding="utf-8")
        print(f"  wrote metadata/badges/{filename}")
    if check:
        if stale:
            print(f"STALE: {len(stale)} badge(s) differ from generator output: {', '.join(stale)}")
            print("run `python3 tools/badges/generate_badges.py` and commit the result")
            return 1
        print(f"OK: {len(rendered)} badges match generator output")
        return 0
    print(f"OK: rendered {len(rendered)} SVGs to metadata/badges/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
