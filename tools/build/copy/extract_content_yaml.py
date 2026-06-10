#!/usr/bin/env python3
"""Extract a language subtree of strings.json into content/<lang>/ YAML.

Phase A migration bridge for the bilingual /en/ /fr/ static-editions
migration. Generates content/fr/ as a faithful structural mirror of the
hand-curated content/en/ tree — the shape the bilingual renderer
(tools/render_pages.py) consumes.

The page copy itself is taken verbatim from the fr subtree of
tools/build/copy/strings.json (existing translations — not re-translated here).
Only the small derived shared sections (site / verification / actions),
which bootstrap_yaml.py synthesised from English literals, are supplied
from a per-language map below.

After cut-over content/<lang>/ is the source of truth and strings.json is
retired; this is one-time tooling and no build stage depends on it.

Usage:
    python3 tools/build/copy/extract_content_yaml.py fr
    python3 tools/build/copy/extract_content_yaml.py fr --check   # diff only, no write

Each generated fr page YAML carries a `translation:` block recording the
sha256 of the English page source it tracks and a review status, consumed
by validate_translation_state.py.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

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
from bootstrap_yaml import dump_yaml  # noqa: E402
from build_copy import (  # noqa: E402
    EMITTED_SHARED_SURFACES,
    PAGE_SURFACES,
    ROOT,
)

STRINGS_JSON = ROOT / "tools" / "build" / "copy" / "strings.json"
EN_CONTENT = ROOT / "content" / "en"

# System surfaces (error / maintenance / sw-reset) not owned by the six
# editorial pages. Bundled into content/<lang>/pages/system.yml.
SYSTEM_SURFACES = ["error", "error_404", "error_500", "maintenance", "sw_reset"]
SYSTEM_META_KEYS = ["403", "404", "500", "maintenance"]

# Derived shared sections per language. content/en/shared.yml is hand-curated
# (and left untouched); content/fr/shared.yml takes the verbatim emitted
# surfaces from the fr subtree plus these derived sections. Marked
# machine-assisted — short standard verification/action labels.
DERIVED_SHARED = {
    "fr": {
        "site": {
            "name": "trentpower.fr",
            "location": "Paris, France",
            "proof_line": "Privé · Statique · Signé · Sans suivi",
            "edition_label": "Édition",
        },
        "verification": {
            "manifest": "Manifeste signé",
            "signature": "Signature détachée",
            "public_key": "Clé publique",
            "source_mirror": "Miroir source",
            "page_fingerprint": "Empreinte de page",
            "canonical_url": "URL canonique",
        },
        "actions": {
            "copy": "Copier",
            "copied": "Copié",
            "close": "Fermer",
            "view_source": "Voir le code source",
            "verify_page": "Vérifier cette page",
            "print_profile": "Imprimer le profil",
        },
    },
}


def _sha256(data: bytes) -> str:
    return "sha256-" + hashlib.sha256(data).hexdigest()


def _en_page_hash(page_name: str, en_subtree: dict) -> str:
    """Hash of the English source a translation tracks.

    Prefers the committed content/en/pages/<page>.yml bytes; falls back to a
    canonical JSON dump of the owned surfaces for system pages with no
    hand-curated English YAML yet.
    """
    en_yaml = EN_CONTENT / "pages" / f"{page_name}.yml"
    if en_yaml.exists():
        return _sha256(en_yaml.read_bytes())
    cfg = _surface_config(page_name)
    payload = {s: en_subtree.get(s) for s in cfg["surfaces"]}
    return _sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode())


def _surface_config(page_name: str) -> dict:
    if page_name == "system":
        return {"surfaces": SYSTEM_SURFACES, "meta_keys": SYSTEM_META_KEYS}
    return PAGE_SURFACES[page_name]


def build_shared(lang: str, subtree: dict) -> dict:
    if lang not in DERIVED_SHARED:
        raise SystemExit(f"no derived-shared map for language {lang!r}")
    out: dict = {}
    for section, values in DERIVED_SHARED[lang].items():
        out[section] = dict(values)
    for surface in ("linkdesc", *[s for s in EMITTED_SHARED_SURFACES if s != "linkdesc"]):
        if surface in subtree:
            out[surface] = subtree[surface]
    return out


def build_page(page_name: str, lang: str, subtree: dict, en_subtree: dict) -> dict:
    cfg = _surface_config(page_name)
    out: dict = {}
    # English is the source, not a translation — no translation: block.
    if lang != "en":
        out["translation"] = {
            "source_page": page_name,
            "source_hash": _en_page_hash(page_name, en_subtree),
            "status": "machine-assisted",
            "updated": datetime.date.today().isoformat(),
        }
    meta_block = {k: subtree["meta"][k] for k in cfg["meta_keys"] if k in subtree.get("meta", {})}
    if meta_block:
        out["meta"] = meta_block
    for surface in cfg["surfaces"]:
        if surface in subtree:
            out[surface] = subtree[surface]
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    check = "--check" in sys.argv
    if len(args) != 1:
        print(__doc__)
        return 2
    lang = args[0]

    strings = json.loads(STRINGS_JSON.read_text(encoding="utf-8"))
    if lang not in strings:
        print(f"error: strings.json has no {lang!r} subtree", file=sys.stderr)
        return 2
    subtree = strings[lang]
    en_subtree = strings["en"]

    lang_dir = ROOT / "content" / lang
    planned: dict[Path, dict] = {}

    if lang == "en":
        # content/en/ is hand-curated. Only emit the system surfaces, which
        # currently live only in strings.json; never clobber the rest.
        planned[lang_dir / "pages" / "system.yml"] = build_page("system", lang, subtree, en_subtree)
    else:
        planned[lang_dir / "shared.yml"] = build_shared(lang, subtree)
        for page_name in list(PAGE_SURFACES.keys()) + ["system"]:
            planned[lang_dir / "pages" / f"{page_name}.yml"] = build_page(
                page_name, lang, subtree, en_subtree
            )

    for path, data in planned.items():
        rel = path.relative_to(ROOT)
        if check:
            existing = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
            status = "unchanged" if existing == data else ("NEW" if existing is None else "CHANGED")
            print(f"  [{status}] {rel}")
        else:
            dump_yaml(data, path)
            print(f"  wrote {rel}", file=sys.stderr)

    if not check:
        print(f"\n✓ content/{lang}/ — {len(planned)} files", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
