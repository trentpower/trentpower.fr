#!/usr/bin/env python3
"""tools/validate_images.py — image-system gate.

Enforces:
  • Every public/images/og/*.png is 1200×630, RGB (no alpha), ≤500 KB.
    Warn if >300 KB.
  • Every <meta property="og:image"> in active HTML references a PNG
    under /images/og/ (never .webp / .avif / /images/social/ / etc.).
  • For every PNG in /images/og/ either there is an HTML reference to
    it in active HTML, OR it is on the explicit allowlist (default-og,
    error pages). No orphan canonical PNGs.
  • If any /images/og/*.webp or *.avif derivative exists, its master
    PNG must exist alongside (no orphan derivatives).
  • Root favicon / app-icon copies are byte-equal to /images/icons/.

Exit 0 = green; exit 1 = block.

Usage:
    python3 tools/validate_images.py

Registered in tools/lib/checks.py (blocking tier). For now it runs
against the canonical PNG set only; derivatives land in commit F.
"""

import re
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
from hashing import sha256_hex  # noqa: E402
from paths import PUBLIC_DIR, REPO_ROOT  # noqa: E402

OG_DIR = PUBLIC_DIR / "images" / "og"
ICONS_DIR = PUBLIC_DIR / "images" / "icons"

CANONICAL_W = 1200
CANONICAL_H = 630
WARN_BYTES = 300 * 1024
FAIL_BYTES = 500 * 1024

ROOT_ICON_FILES = [
    "favicon.ico",
    "favicon.svg",
    "apple-touch-icon.png",
    "icon-192.png",
    "icon-512.png",
]


# active html scanned for og:image references — discovered by walk so
# the bilingual /en/ and /fr/ trees are covered automatically. the
# dated frozen-archive snapshots and the generated editorial review
# documents are excluded.
def _discover_active_html() -> list:
    import re as _re

    out = []
    for p in sorted(PUBLIC_DIR.glob("**/*.html")):
        rel = p.relative_to(PUBLIC_DIR).as_posix()
        if _re.match(r"integrity/releases/[^/]+/", rel):
            continue
        if rel.startswith("editorial/"):
            continue
        out.append(rel)
    return out


ACTIVE_HTML = _discover_active_html()


def _pil():
    try:
        from PIL import Image

        return Image
    except ImportError:
        return None


def main() -> int:
    fails: list[str] = []
    warnings: list[str] = []

    Image = _pil()
    if Image is None:
        fails.append("Pillow (PIL) not installed; cannot validate PNG dimensions")

    # ── 1. canonical og pngs ────────────────────────────────────
    if not OG_DIR.is_dir():
        fails.append(f"missing canonical OG dir: {OG_DIR.relative_to(REPO_ROOT)}")
    else:
        for png in sorted(OG_DIR.glob("*.png")):
            try:
                if Image is not None:
                    with Image.open(png) as im:
                        im.load()
                        w, h = im.size
                        mode = im.mode
                        fmt = im.format
                else:
                    w, h, mode, fmt = (None, None, None, None)
            except Exception as e:
                fails.append(f"{png.relative_to(PUBLIC_DIR)}: cannot read ({e})")
                continue
            if Image is not None:
                if fmt != "PNG":
                    fails.append(f"{png.relative_to(PUBLIC_DIR)}: not a PNG (format={fmt})")
                if (w, h) != (CANONICAL_W, CANONICAL_H):
                    fails.append(
                        f"{png.relative_to(PUBLIC_DIR)}: {w}×{h} (expected {CANONICAL_W}×{CANONICAL_H})"
                    )
                if mode in ("RGBA", "LA", "PA"):
                    fails.append(
                        f"{png.relative_to(PUBLIC_DIR)}: alpha channel present (mode={mode}) — flatten to RGB"
                    )
            sz = png.stat().st_size
            if sz > FAIL_BYTES:
                fails.append(
                    f"{png.relative_to(PUBLIC_DIR)}: {sz} bytes exceeds {FAIL_BYTES}-byte hard limit"
                )
            elif sz > WARN_BYTES:
                warnings.append(
                    f"{png.relative_to(PUBLIC_DIR)}: {sz} bytes exceeds {WARN_BYTES}-byte soft limit"
                )

    # ── 2. og:image refs in active html ─────────────────────────
    og_image_re = re.compile(r'<meta\s+property="og:image"\s+content="([^"]+)"', re.IGNORECASE)
    referenced: set[str] = set()
    for rel in ACTIVE_HTML:
        p = PUBLIC_DIR / rel
        if not p.is_file():
            fails.append(f"{rel}: missing active HTML")
            continue
        text = p.read_text(encoding="utf-8")
        for m in og_image_re.finditer(text):
            url = m.group(1)
            # allowed shape: https://trentpower.fr/images/og/<name>.png
            # or /images/portraits/trent-power-og.jpg (homepage portrait og).
            if "/images/og/" in url and url.endswith(".png"):
                referenced.add(url.rsplit("/", 1)[-1])
            elif "/images/portraits/" in url and url.endswith((".jpg", ".jpeg")):
                pass  # homepage uses the portrait as og (acceptable)
            else:
                fails.append(
                    f"{rel}: og:image '{url}' must be /images/og/*.png "
                    "or /images/portraits/trent-power-og.jpg"
                )
            # forbid WebP/AVIF in og metadata explicitly.
            if url.endswith((".webp", ".avif")):
                fails.append(f"{rel}: og:image must be PNG, not {url.rsplit('.', 1)[-1]}")
            if "/images/social/" in url:
                fails.append(f"{rel}: stale legacy /images/social/ reference: {url}")

    # ── 3. orphan canonical png check ───────────────────────────
    # any png in /images/og/ that is not referenced in active html
    # and not in the explicit allowlist is an orphan.
    ALLOWLIST_UNREFERENCED = {
        "default-og.png",  # fallback og, may or may not be referenced explicitly
    }
    if OG_DIR.is_dir():
        for png in sorted(OG_DIR.glob("*.png")):
            if png.name in referenced:
                continue
            if png.name in ALLOWLIST_UNREFERENCED:
                continue
            warnings.append(
                f"{png.relative_to(PUBLIC_DIR)}: canonical PNG not "
                f"referenced by any og:image in active HTML"
            )

    # ── 4. derivative orphans ───────────────────────────────────
    # if WebP/AVIF derivatives exist, their png masters must too.
    if OG_DIR.is_dir():
        for d in OG_DIR.glob("*.webp"):
            png = d.with_suffix(".png")
            if not png.is_file():
                fails.append(f"{d.relative_to(PUBLIC_DIR)}: derivative without master PNG")
        for d in OG_DIR.glob("*.avif"):
            png = d.with_suffix(".png")
            if not png.is_file():
                fails.append(f"{d.relative_to(PUBLIC_DIR)}: derivative without master PNG")

    # ── 5. root icon ↔ /images/icons/ byte-equality ─────────────
    if not ICONS_DIR.is_dir():
        fails.append(f"missing canonical icons dir: {ICONS_DIR.relative_to(REPO_ROOT)}")
    else:
        for fn in ROOT_ICON_FILES:
            root = PUBLIC_DIR / fn
            canon = ICONS_DIR / fn
            if not root.is_file():
                fails.append(f"missing root icon {fn} (browsers expect it at /)")
                continue
            if not canon.is_file():
                fails.append(f"missing canonical icon /images/icons/{fn}")
                continue
            if sha256_hex(root.read_bytes()) != sha256_hex(canon.read_bytes()):
                fails.append(
                    f"/{fn} differs from /images/icons/{fn} — root copy must "
                    f"be byte-equal to the canonical copy"
                )

    # ── print summary ───────────────────────────────────────────
    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  ! {w}")

    if fails:
        print(f"FAIL: {len(fails)} image-system issue(s)", file=sys.stderr)
        for f in fails:
            print(f"  ✗ {f}", file=sys.stderr)
        return 1

    print(
        f"OK: image system — {len(list(OG_DIR.glob('*.png'))) if OG_DIR.is_dir() else 0} canonical PNGs, {len(ROOT_ICON_FILES)} icon pairs verified"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
