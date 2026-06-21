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

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the scan runs over a fixture repo with no monkeypatching. The
LANGS source-of-truth read can fail before the scan, so the load step returns
either a Ctx (the live LANGS) or errors; `evaluate(repo, ctx)` is the pure
compute path returning a Result; `main()` is the only adapter that prints/exits.
The reference-scan, exclusions, and messages are byte-identical to the former
module-global form.

Exit 0 = clean; exit 1 = orphan(s) found.
"""

from __future__ import annotations

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
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

# repo-relative roots (resolved through the Repo seam).
PUBLIC_REL = "public"
TEMPLATES_REL = "templates"
IMAGES_REL = "public/images"
ARCH_GENERATOR_REL = "tools/build/_generate_architecture_svgs.py"

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


@dataclass(frozen=True)
class Ctx:
    langs: list[str]


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    oks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


def _load_langs_from_arch_generator(repo: Repo) -> list[str] | None:
    """Read LANGS = [...] from the architecture-svg generator. single
    source of truth for which per-language variants are live. returns
    None if the list cannot be read (the caller surfaces the error)."""
    src = repo.read(ARCH_GENERATOR_REL)
    m = re.search(r"^LANGS\s*=\s*\[([^\]]*)\]", src, re.MULTILINE)
    if not m:
        return None
    return [s.strip().strip('"').strip("'") for s in m.group(1).split(",") if s.strip()]


def _build_corpus(repo: Repo) -> str:
    parts: list[str] = []
    for root in (PUBLIC_REL, TEMPLATES_REL):
        for rel in repo.glob(f"{root}/**/*"):
            # skip the images tree itself and the manifests that
            # only describe disk.
            if rel.startswith(PUBLIC_REL + "/"):
                prel = rel[len(PUBLIC_REL) + 1 :]
                parts_rel = prel.split("/")
                if parts_rel and parts_rel[0] == "images":
                    continue
                name = parts_rel[-1]
                if name in MANIFEST_EXCLUDES:
                    continue
                if name == SOURCE_MANIFEST_NAME:
                    continue
            name = rel.rsplit("/", 1)[-1]
            suffix = ("." + name.rsplit(".", 1)[1]) if "." in name else ""
            if suffix.lower() in CORPUS_SUFFIXES or name == ".htaccess":
                parts.append(repo.read(rel))
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


# ---------------------------------------------------------------------------
# load — read + validate the inputs. returns (ctx, errors); never prints/exits.
# ---------------------------------------------------------------------------
def load(repo: Repo) -> tuple[Ctx | None, list[str]]:
    langs = _load_langs_from_arch_generator(repo)
    if langs is None:
        return None, ["  FAIL: cannot read LANGS from _generate_architecture_svgs.py"]
    return Ctx(langs=langs), []


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo. this is the test surface.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo, ctx: Ctx) -> Result:
    r = Result()

    images_dir = repo.root / IMAGES_REL
    if not images_dir.is_dir():
        r.oks.append(f"  OK: no images directory at {images_dir}")
        return r

    image_rels = sorted(repo.glob(f"{IMAGES_REL}/**/*"))
    corpus = _build_corpus(repo)
    orphans: list[str] = []

    for img_rel in image_rels:
        prel = img_rel[len(PUBLIC_REL) + 1 :]
        rel = "/" + prel
        basename = prel.rsplit("/", 1)[-1]

        if rel in corpus:
            continue
        if basename in corpus:
            continue
        if _is_arch_lang_variant(rel, ctx.langs):
            # extra guard: confirm the architecture path namespace
            # is actually referenced somewhere live. if not, the
            # whole feature is orphaned and the dynamic pattern
            # alone can't justify the file.
            if "/images/architecture/" in corpus:
                continue
        orphans.append(rel)

    if orphans:
        r.fails.append(
            f"  FAIL: {len(orphans)} orphan image(s) under /images/ "
            f"(no reference in HTML/CSS/JS/JSON/webmanifest/xml/txt/htaccess "
            f"or templates):"
        )
        for o in orphans:
            r.fails.append(f"    {o}")
        return r

    r.oks.append(f"  OK: every image under /images/ is referenced (LANGS={ctx.langs}).")
    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. loads, evaluates, renders, returns exit
# code. the only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)

    ctx, errors = load(repo)
    if errors:
        for e in errors:
            print(e)
        return 1

    r = evaluate(repo, ctx)
    for line in r.oks:
        print(line)
    for line in r.fails:
        print(line)
    return 1 if r.fails else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
