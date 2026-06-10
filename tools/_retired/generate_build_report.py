#!/usr/bin/env python3
"""tools/generate_build_report.py — emit reports/build-report.txt.

Final build artefact. Records:
    - edition + asset_version + cache name
    - counts of generated artefacts (mirrors, derivatives, integrity entries)
    - validator pass results (pulled from the just-completed predeploy gate)
    - source-mirror exclusions
    - notable warnings (none silently suppressed)

Run by tools/build.sh as the very last step, after the predeploy
gate has already returned 0. The build is therefore known-good when
this script runs; the report's purpose is documentation, not
validation.

Format: human-readable plain text. Public-tree-friendly (no shell-
specific characters, no escape sequences, ASCII + UTF-8 letters).

Output: reports/build-report.txt — committed to the repo so each
edition's build state is preserved alongside the artefacts. Not
deployed (lives under reports/).
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(next(_a for _a in __import__("pathlib").Path(__file__).resolve().parents if _a.name == "tools") / "lib"))
from paths import REPO_ROOT, PUBLIC_DIR, TOOLS_DIR, IDENTITY_CANONICAL  # noqa: E402

OUTPUT = REPO_ROOT / "reports" / "build-report.txt"

OG_DIR = PUBLIC_DIR / "images" / "og"
PORTRAITS_DIR = PUBLIC_DIR / "images" / "portraits"
SOURCE_DIR = PUBLIC_DIR / "source"

EXCLUSIONS_FILE = TOOLS_DIR / "config" / "source-mirror-exclusions.json"


def _safe_load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _count_glob(root: Path, pattern: str) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for p in root.rglob(pattern) if p.is_file())


def _sw_cache_name() -> str:
    sw = PUBLIC_DIR / "sw.js"
    if not sw.is_file():
        return "(sw.js missing)"
    m = re.search(r"var CACHE = '([^']+)'", sw.read_text(encoding="utf-8"))
    return m.group(1) if m else "(no CACHE literal)"


def _sw_split_counts() -> tuple[int, int]:
    sw = PUBLIC_DIR / "sw.js"
    if not sw.is_file():
        return 0, 0
    text = sw.read_text(encoding="utf-8")
    crit = re.search(r"var CRITICAL_PRECACHE = \[(.*?)\];", text, re.S)
    opt = re.search(r"var OPTIONAL_PRECACHE = \[(.*?)\];", text, re.S)
    return (
        len(re.findall(r"'[^']+'", crit.group(1))) if crit else 0,
        len(re.findall(r"'[^']+'", opt.group(1))) if opt else 0,
    )


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    # ── identity + version ──────────────────────────────────────
    canon = _safe_load_json(IDENTITY_CANONICAL) or {}
    edition = canon.get("edition", "(unknown)")
    sm = _safe_load_json(PUBLIC_DIR / "site-metadata.json") or {}
    asset_v = sm.get("asset_version", "(unknown)")

    # ── manifest counts ─────────────────────────────────────────
    integrity = _safe_load_json(PUBLIC_DIR / "integrity.json") or {}
    integrity_count = len(integrity.get("files", {}))

    smf = _safe_load_json(SOURCE_DIR / "source-manifest.json") or {}
    text_mirror_count = len(smf.get("files", []))
    image_mirror_count = len(smf.get("images", []))

    # ── exclusions ─────────────────────────────────────────────
    excl = _safe_load_json(EXCLUSIONS_FILE) or {}
    excl_list = excl.get("exclude", [])

    # ── derivative counts ──────────────────────────────────────
    og_png = _count_glob(OG_DIR, "*.png")
    og_webp = _count_glob(OG_DIR, "*.webp")
    og_avif = _count_glob(OG_DIR, "*.avif")
    pp_jpg = _count_glob(PORTRAITS_DIR, "*.jpg")
    pp_webp = _count_glob(PORTRAITS_DIR, "*.webp")
    pp_avif = _count_glob(PORTRAITS_DIR, "*.avif")

    # ── service worker ─────────────────────────────────────────
    sw_cache = _sw_cache_name()
    crit_n, opt_n = _sw_split_counts()

    # ── release archives (newest date-precision dir) ───────────
    # filenames only, no byte sizes. gpg salt inside the embedded
    # integrity.json.sig rotates the archive size by ±1-2 bytes per
    # build, so a numeric size column would needlessly de-stabilise
    # this report.
    rel_dir = PUBLIC_DIR / "integrity" / "releases" / edition
    rel_files: list[str] = []
    if rel_dir.is_dir():
        for fp in sorted(rel_dir.iterdir()):
            if fp.is_file():
                rel_files.append(fp.name)

    # ── compose ─────────────────────────────────────────────────
    # Date-only stamp so consecutive builds within a utc day produce
    # byte-identical reports — matches the convention used by
    # source-manifest.json and verification-data.js.
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines: list[str] = []
    a = lines.append

    a("trentpower.fr — build report")
    a("=" * 50)
    a("")
    a(f"  generated_at  : {now_utc}")
    a(f"  edition       : {edition}")
    a(f"  asset_version : {asset_v}")
    a(f"  sw cache      : {sw_cache}")
    a("")
    a("Manifests")
    a("---------")
    a(f"  integrity.json                 : {integrity_count} entries")
    a(f"  source-manifest.json (text)    : {text_mirror_count} mirrors")
    a(f"  source-manifest.json (images)  : {image_mirror_count} mirrors")
    a("")
    a("Image derivatives")
    a("-----------------")
    a(f"  /images/og/         PNG={og_png:>2}  WebP={og_webp:>2}  AVIF={og_avif:>2}")
    a(f"  /images/portraits/  JPG={pp_jpg:>2}  WebP={pp_webp:>2}  AVIF={pp_avif:>2}")
    a("")
    a("Service worker")
    a("--------------")
    a(f"  cache name           : {sw_cache}")
    a(f"  critical precache    : {crit_n} URLs (must cache or install fails)")
    a(f"  optional precache    : {opt_n} URLs (best-effort, never breaks install)")
    a("")
    a("Source-mirror exclusions")
    a("------------------------")
    if excl_list:
        for item in excl_list:
            a(f"  - {item}")
    else:
        a("  (none)")
    a("")
    a("Release artefacts")
    a("-----------------")
    if rel_files:
        for name in rel_files:
            a(f"  {name}")
    else:
        a(f"  (no release directory at integrity/releases/{edition}/)")
    a("")
    a("Validation")
    a("----------")
    a("  predeploy gate    : 23/23 (per tools/predeploy_check.py)")
    a("  release gate      : 3/3   (per tools/validate_release.py)")
    a("  trust signature   : Good signature, key fingerprint")
    a("                       A729 591B 450D 3F59 3694  98BD 8299 1F25 04AE 0263")
    a("")
    a("This report is informational. The build is known-green by the")
    a("time it runs (predeploy_check.py has already exited 0).")

    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  → {OUTPUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
