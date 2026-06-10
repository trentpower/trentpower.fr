#!/usr/bin/env python3
"""tools/validate_no_orphan_images.py — strict orphan-image gate.

Every file under public/images/ must be referenced from a consumer
that the build or runtime actually reads. References are matched
against an aggregated text corpus drawn from:

  • All *.html, *.css, *.js, *.json, *.webmanifest, *.xml, *.txt
    under public/
  • public/.htaccess
  • All *.template.js under templates/

A file passes if any of these is true:
  1. Its canonical web path (e.g. /images/og/home-og.png) appears
     verbatim in the corpus.
  2. Its basename appears verbatim in the corpus (catches CSS
     url(images/foo.png) and JSON entries that store basenames).
  3. It matches a registered dynamic-template pattern. The only
     one wired today is the architecture per-language SVG loader:
     app.template.js builds the path from the locale, so the file
     is never spelled literally. The validator reads LANGS from
     tools/_generate_architecture_svgs.py so the two stay in sync.

Manifest-style consumers (integrity.json, file-metadata.json,
images-manifest.json if present, source-manifest.json) are not
treated as references — they only describe what is on disk, and
relying on them would let orphans cite themselves.

Exit 0 = clean; exit 1 = orphan(s) found.
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
from paths import PUBLIC_DIR, TEMPLATES_DIR, TOOLS_DIR  # noqa: E402

IMAGES_DIR = PUBLIC_DIR / "images"

# manifests that describe the disk rather than reference it. excluded
# so an asset can't self-justify by appearing only in a manifest.
MANIFEST_EXCLUDES = {
    "integrity.json",
    "file-metadata.json",
    "images-manifest.json",
    "site-metadata.json",
    "sw-cache-manifest.json",
}
# source-manifest.json lives under public/source/; excluded by name.
SOURCE_MANIFEST_NAME = "source-manifest.json"

CORPUS_SUFFIXES = {
    ".html",
    ".css",
    ".js",
    ".json",
    ".webmanifest",
    ".xml",
    ".txt",
}


def _load_langs_from_arch_generator() -> list[str]:
    """Read LANGS = [...] from the architecture-svg generator. single
    source of truth for which per-language variants are live."""
    src = (TOOLS_DIR / "build" / "_generate_architecture_svgs.py").read_text(encoding="utf-8")
    m = re.search(r"^LANGS\s*=\s*\[([^\]]*)\]", src, re.MULTILINE)
    if not m:
        print("  FAIL: cannot read LANGS from _generate_architecture_svgs.py")
        sys.exit(1)
    return [s.strip().strip('"').strip("'") for s in m.group(1).split(",") if s.strip()]


def _build_corpus() -> str:
    parts: list[str] = []
    for root in (PUBLIC_DIR, TEMPLATES_DIR):
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            # skip the images tree itself and the manifests that
            # only describe disk.
            try:
                rel = p.relative_to(PUBLIC_DIR)
                if rel.parts and rel.parts[0] == "images":
                    continue
                if p.name in MANIFEST_EXCLUDES:
                    continue
                if p.name == SOURCE_MANIFEST_NAME:
                    continue
            except ValueError:
                pass  # not under PUBLIC_DIR (i.e. templates/)
            if p.suffix.lower() in CORPUS_SUFFIXES or p.name == ".htaccess":
                try:
                    parts.append(p.read_text(encoding="utf-8", errors="ignore"))
                except OSError:
                    continue
    return "\n".join(parts)


def _is_arch_lang_variant(rel_path: str, langs: list[str]) -> bool:
    """match /images/architecture/architecture[-mobile].<lang>.svg
    where <lang> is in the live LANGS list. the literal path
    /images/architecture/ must also appear in the corpus for this
    to count — otherwise the whole feature is orphaned."""
    m = re.fullmatch(
        r"/images/architecture/(architecture(?:-mobile)?)\.([a-z]{2})\.svg",
        rel_path,
    )
    if not m:
        return False
    return m.group(2) in langs


def main() -> int:
    if not IMAGES_DIR.is_dir():
        print(f"  OK: no images directory at {IMAGES_DIR}")
        return 0

    langs = _load_langs_from_arch_generator()
    corpus = _build_corpus()
    orphans: list[str] = []

    for img in sorted(IMAGES_DIR.rglob("*")):
        if not img.is_file():
            continue
        rel = "/" + img.relative_to(PUBLIC_DIR).as_posix()
        basename = img.name

        if rel in corpus:
            continue
        if basename in corpus:
            continue
        if _is_arch_lang_variant(rel, langs):
            # extra guard: confirm the architecture path namespace
            # is actually referenced somewhere live. if not, the
            # whole feature is orphaned and the dynamic pattern
            # alone can't justify the file.
            if "/images/architecture/" in corpus:
                continue
        orphans.append(rel)

    if orphans:
        print(
            f"  FAIL: {len(orphans)} orphan image(s) under /images/ "
            f"(no reference in HTML/CSS/JS/JSON/webmanifest/xml/txt/htaccess "
            f"or templates):"
        )
        for o in orphans:
            print(f"    {o}")
        return 1

    print(f"  OK: every image under /images/ is referenced (LANGS={langs}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
