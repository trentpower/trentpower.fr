#!/usr/bin/env python3
"""tools/build_font_subsets.py — emit homepage-critical font subsets.

The hero serif, nav sans and mono labels each need only a small
glyph set above the fold across the 5 site languages. Full editorial
weights still ship at /fonts/* for below-fold content; the subsets
keep the LCP critical request chain tiny.

Inputs
  tools/font-subsets/home-hero.txt    — Signifier hero glyphs
  tools/font-subsets/nav-labels.txt   — Söhne nav glyphs
  tools/font-subsets/mono-labels.txt  — Söhne Mono label glyphs

Outputs
  public/fonts/subsets/signifier-light-hero.woff2
  public/fonts/subsets/soehne-kraftig-nav.woff2
  public/fonts/subsets/soehne-mono-buch-labels.woff2

Each subset is desubroutinised + WOFF2 compressed; layout features
preserved so the font still renders correctly when applied via the
critical aliases declared in styles.src.css.

Run by tools/build.sh after tools/generate_site.py emits the
minified styles.css and before generate_sri.py / generate_integrity.py
hash the public tree.

Hard requirements:
  • fontTools must be importable (pip install fonttools[woff] or
    apt install python3-fonttools). Build aborts otherwise so a
    silent stale subset cannot ship.
  • Source full fonts at public/fonts/*.woff2 must exist.
"""

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
from paths import PUBLIC_DIR, TOOLS_DIR  # noqa: E402

try:
    from fontTools.subset import Options, Subsetter, load_font, save_font
except ImportError:
    print(
        "ERROR: fontTools not installed (pip install 'fonttools[woff]'). "
        "Cannot build font subsets.",
        file=sys.stderr,
    )
    sys.exit(1)


SUBSETS = [
    {
        "name": "Signifier hero",
        "src": PUBLIC_DIR / "fonts" / "signifier-light.woff2",
        "out": PUBLIC_DIR / "fonts" / "subsets" / "signifier-light-hero.woff2",
        "glyphs": TOOLS_DIR / "build" / "fonts" / "home-hero.txt",
    },
    {
        "name": "Söhne nav",
        "src": PUBLIC_DIR / "fonts" / "soehne-kraftig.woff2",
        "out": PUBLIC_DIR / "fonts" / "subsets" / "soehne-kraftig-nav.woff2",
        "glyphs": TOOLS_DIR / "build" / "fonts" / "nav-labels.txt",
    },
    {
        "name": "Söhne Mono labels",
        "src": PUBLIC_DIR / "fonts" / "soehne-mono-buch.woff2",
        "out": PUBLIC_DIR / "fonts" / "subsets" / "soehne-mono-buch-labels.woff2",
        "glyphs": TOOLS_DIR / "build" / "fonts" / "mono-labels.txt",
    },
]


def _build(spec: dict) -> int:
    src = spec["src"]
    out = spec["out"]
    glyphs_path = spec["glyphs"]
    if not src.is_file():
        print(f"  FAIL: source font missing: {src}", file=sys.stderr)
        return 1
    if not glyphs_path.is_file():
        print(f"  FAIL: glyph file missing: {glyphs_path}", file=sys.stderr)
        return 1
    text = glyphs_path.read_text(encoding="utf-8").rstrip("\n")

    options = Options()
    options.flavor = "woff2"
    options.with_zopfli = False
    options.desubroutinize = True
    options.layout_features = ["*"]
    options.notdef_outline = True
    options.no_hinting = False
    options.drop_tables = []  # keep all tables fonttools leaves by default

    font = load_font(str(src), options)
    subsetter = Subsetter(options=options)
    subsetter.populate(text=text)
    subsetter.subset(font)

    out.parent.mkdir(parents=True, exist_ok=True)
    save_font(font, str(out), options)
    src_size = src.stat().st_size
    out_size = out.stat().st_size
    saved = src_size - out_size
    pct = (saved / src_size) * 100 if src_size else 0
    print(
        f"  ✓ {spec['name']:18}  {src.name:36} → {out.name:38}  "
        f"{src_size:5} → {out_size:5} bytes  ({pct:.0f}% saved)"
    )
    return 0


def main() -> int:
    print("Subsetting fonts for the homepage critical path:")
    rc = 0
    for spec in SUBSETS:
        rc |= _build(spec)
    if rc != 0:
        print("FAIL: at least one subset did not build.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
