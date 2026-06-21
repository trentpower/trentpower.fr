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

Shape (deep module, small interface). The filesystem is the one injected seam,
`Repo(root)`, so the whole gate runs over a fixture repo with no monkeypatching.
PIL/Pillow stays a direct import — it is a binary library, not a seam — and the
graceful PIL-absent degrade is preserved verbatim. Compute (`evaluate`) returns
a Result and never prints or exits; `main()` is the only side-effecting adapter
and reproduces the original stdout byte-for-byte.
"""

from __future__ import annotations

import io
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

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
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

# repo-relative anchors for the canonical image trees (resolved through Repo).
OG_DIR_REL = "public/images/og"
ICONS_DIR_REL = "public/images/icons"

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


def _pil():
    try:
        from PIL import Image

        return Image
    except ImportError:
        return None


# named accessors over the shared Repo seam. the public-tree knowledge (the
# "public/" prefix, recursive walks, the og/icons subpaths) lives here in the
# validator, not on Repo.
def _public_rel(rel: str) -> str:
    """strip the leading "public/" so messages read images/og/foo.png, the
    same surface the original printed via .relative_to(PUBLIC_DIR)."""
    prefix = "public/"
    return rel[len(prefix) :] if rel.startswith(prefix) else rel


def _og_pngs(repo: Repo) -> list[str]:
    """repo-relative paths of canonical OG pngs (sorted by the Repo seam)."""
    return repo.glob(f"{OG_DIR_REL}/*.png")


# active html scanned for og:image references — discovered by walk so
# the bilingual /en/ and /fr/ trees are covered automatically. the
# dated frozen-archive snapshots and the generated editorial review
# documents are excluded.
def _discover_active_html(repo: Repo) -> list:
    out = []
    for rel in repo.glob("public/**/*.html"):
        prel = _public_rel(rel)
        if re.match(r"integrity/releases/[^/]+/", prel):
            continue
        if prel.startswith("editorial/"):
            continue
        out.append(prel)
    return out


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    png_count: int = 0

    @property
    def ok(self) -> bool:
        return not self.fails


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo. this is the test surface; it never prints or exits.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo, active_html: list | None = None) -> Result:
    r = Result()
    fails = r.fails
    warnings = r.warns

    if active_html is None:
        active_html = _discover_active_html(repo)

    Image = _pil()
    if Image is None:
        fails.append("Pillow (PIL) not installed; cannot validate PNG dimensions")

    # dir existence is domain knowledge resolved over the seam root (Repo has
    # is_file but no is_dir; the original used OG_DIR.is_dir()/ICONS_DIR.is_dir()).
    og_dir_exists = (repo.root / OG_DIR_REL).is_dir()
    icons_dir_exists = (repo.root / ICONS_DIR_REL).is_dir()

    # ── 1. canonical og pngs ────────────────────────────────────
    if not og_dir_exists:
        fails.append(f"missing canonical OG dir: {OG_DIR_REL}")
    else:
        for png in _og_pngs(repo):
            pub = _public_rel(png)
            try:
                if Image is not None:
                    with Image.open(io.BytesIO((repo.root / png).read_bytes())) as im:
                        im.load()
                        w, h = im.size
                        mode = im.mode
                        fmt = im.format
                else:
                    w, h, mode, fmt = (None, None, None, None)
            except Exception as e:
                fails.append(f"{pub}: cannot read ({e})")
                continue
            if Image is not None:
                if fmt != "PNG":
                    fails.append(f"{pub}: not a PNG (format={fmt})")
                if (w, h) != (CANONICAL_W, CANONICAL_H):
                    fails.append(f"{pub}: {w}×{h} (expected {CANONICAL_W}×{CANONICAL_H})")
                if mode in ("RGBA", "LA", "PA"):
                    fails.append(f"{pub}: alpha channel present (mode={mode}) — flatten to RGB")
            sz = repo.size(png)
            if sz > FAIL_BYTES:
                fails.append(f"{pub}: {sz} bytes exceeds {FAIL_BYTES}-byte hard limit")
            elif sz > WARN_BYTES:
                warnings.append(f"{pub}: {sz} bytes exceeds {WARN_BYTES}-byte soft limit")

    # ── 2. og:image refs in active html ─────────────────────────
    og_image_re = re.compile(r'<meta\s+property="og:image"\s+content="([^"]+)"', re.IGNORECASE)
    referenced: set[str] = set()
    for rel in active_html:
        pub = f"public/{rel}"
        if not repo.is_file(pub):
            fails.append(f"{rel}: missing active HTML")
            continue
        text = repo.read(pub)
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
    if og_dir_exists:
        for png in _og_pngs(repo):
            name = png.rsplit("/", 1)[-1]
            if name in referenced:
                continue
            if name in ALLOWLIST_UNREFERENCED:
                continue
            warnings.append(
                f"{_public_rel(png)}: canonical PNG not referenced by any og:image in active HTML"
            )

    # ── 4. derivative orphans ───────────────────────────────────
    # if WebP/AVIF derivatives exist, their png masters must too.
    if og_dir_exists:
        for d in repo.glob(f"{OG_DIR_REL}/*.webp"):
            png = d[: -len(".webp")] + ".png"
            if not repo.is_file(png):
                fails.append(f"{_public_rel(d)}: derivative without master PNG")
        for d in repo.glob(f"{OG_DIR_REL}/*.avif"):
            png = d[: -len(".avif")] + ".png"
            if not repo.is_file(png):
                fails.append(f"{_public_rel(d)}: derivative without master PNG")

    # ── 5. root icon ↔ /images/icons/ byte-equality ─────────────
    if not icons_dir_exists:
        fails.append(f"missing canonical icons dir: {ICONS_DIR_REL}")
    else:
        for fn in ROOT_ICON_FILES:
            root = f"public/{fn}"
            canon = f"{ICONS_DIR_REL}/{fn}"
            if not repo.is_file(root):
                fails.append(f"missing root icon {fn} (browsers expect it at /)")
                continue
            if not repo.is_file(canon):
                fails.append(f"missing canonical icon /images/icons/{fn}")
                continue
            if sha256_hex((repo.root / root).read_bytes()) != sha256_hex(
                (repo.root / canon).read_bytes()
            ):
                fails.append(
                    f"/{fn} differs from /images/icons/{fn} — root copy must "
                    f"be byte-equal to the canonical copy"
                )

    r.png_count = len(_og_pngs(repo)) if og_dir_exists else 0
    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. evaluates, renders, returns exit code. the
# only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(repo)

    # ── print summary ───────────────────────────────────────────
    if r.warns:
        print(f"WARNINGS ({len(r.warns)}):")
        for w in r.warns:
            print(f"  ! {w}")

    if r.fails:
        print(f"FAIL: {len(r.fails)} image-system issue(s)", file=sys.stderr)
        for f in r.fails:
            print(f"  ✗ {f}", file=sys.stderr)
        return 1

    print(
        f"OK: image system — {r.png_count} canonical PNGs, {len(ROOT_ICON_FILES)} icon pairs verified"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
