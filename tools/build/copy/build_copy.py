#!/usr/bin/env python3
"""Build copy: YAML sources in content/en/ -> en subtree of tools/build/copy/strings.json.

content/en/shared.yml is the source of truth for cross-page editorial copy.
content/en/pages/{home,privacy,integrity,source,verify,security}.yml hold
page-specific copy. Page YAMLs may reference shared values with {{ shared.x.y }}.

The fr subtree of strings.json is preserved unchanged. Surfaces outside the
six migrated pages (maintenance, sw_reset, error_404, error_500, error.*)
keep whatever the existing en subtree holds.

Exit codes:
  0  build succeeded (warnings printed to stderr)
  1  build failed (lint errors); strings.json was NOT touched
  2  setup error (missing file, missing PyYAML)
"""

from __future__ import annotations

import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[3]
CONTENT_DIR = ROOT / "content" / "en"
STRINGS_JSON = ROOT / "tools" / "build" / "copy" / "strings.json"

# Each entry maps a page YAML name -> strings.json surfaces it owns,
# plus the meta.* sub-keys it owns.
PAGE_SURFACES = OrderedDict(
    [
        (
            "home",
            {
                "surfaces": [
                    "hero",
                    "approach",
                    "credentials",
                    "trajectory",
                    "projects",
                    "contact",
                    "home",
                    "print",
                ],
                "meta_keys": ["home"],
            },
        ),
        (
            "privacy",
            {
                "surfaces": ["privacy"],
                "meta_keys": ["privacy"],
            },
        ),
        (
            "integrity",
            {
                "surfaces": ["integrity", "releases", "release_archive"],
                "meta_keys": ["integrity", "releases"],
            },
        ),
        (
            "source",
            {
                "surfaces": ["source", "source_reader"],
                "meta_keys": ["source"],
            },
        ),
        (
            "verify",
            {
                "surfaces": ["verify", "verify_intro", "verify_locally"],
                "meta_keys": ["verify", "verify_locally"],
            },
        ),
        (
            "security",
            {
                "surfaces": ["security", "acknowledgments"],
                "meta_keys": ["security", "acknowledgments"],
            },
        ),
    ]
)

# Top-level keys in shared.yml that emit directly to en.<key>.
EMITTED_SHARED_SURFACES = ["footer", "modal", "cite", "copy", "trust_routes", "linkdesc"]

# Top-level keys in shared.yml that are alias-only (reference targets, not emitted).
ALIAS_SHARED_KEYS = ["site", "actions", "verification", "print_terms"]

REF_RE = re.compile(r"\{\{\s*shared\.([a-zA-Z0-9_.]+)\s*\}\}")

# A string >= this many characters that appears more than DUPE_THRESHOLD times
# outside shared.yml triggers a warning to promote it to shared.
LONG_PHRASE_CHARS = 30
DUPE_THRESHOLD = 3


def load_yaml(path: Path):
    if not path.exists():
        print(f"error: missing {path.relative_to(ROOT)}", file=sys.stderr)
        sys.exit(2)
    with path.open() as f:
        data = yaml.safe_load(f)
    return data or {}


def walk_strings(node, path=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk_strings(v, path + (str(k),))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_strings(v, path + (f"[{i}]",))
    elif isinstance(node, str):
        yield path, node


def resolve_refs(node, shared, errors, where):
    if isinstance(node, str):

        def replace(m):
            parts = m.group(1).split(".")
            cur = shared
            for p in parts:
                if isinstance(cur, dict) and p in cur:
                    cur = cur[p]
                else:
                    errors.append(
                        f"{where}: unresolved reference {{{{ shared.{'.'.join(parts)} }}}}"
                    )
                    return m.group(0)
            if not isinstance(cur, str):
                errors.append(
                    f"{where}: shared.{'.'.join(parts)} resolves to a {type(cur).__name__}, not a string"
                )
                return m.group(0)
            return cur

        return REF_RE.sub(replace, node)
    if isinstance(node, dict):
        return OrderedDict(
            (k, resolve_refs(v, shared, errors, f"{where}.{k}")) for k, v in node.items()
        )
    if isinstance(node, list):
        return [resolve_refs(v, shared, errors, f"{where}[{i}]") for i, v in enumerate(node)]
    return node


def load_inputs():
    shared = load_yaml(CONTENT_DIR / "shared.yml")
    pages = OrderedDict()
    for name in PAGE_SURFACES:
        pages[name] = load_yaml(CONTENT_DIR / "pages" / f"{name}.yml")
    return shared, pages


def validate_shared_no_chains(shared, errors):
    """Shared values must not themselves contain references — one level only."""
    for path, val in walk_strings(shared, ("shared",)):
        if REF_RE.search(val):
            errors.append(
                f"{'.'.join(path)}: shared values may not contain {{{{ shared.* }}}} references"
            )


def assemble_en_subtree(original_en, shared_resolved, pages_resolved, errors):
    """Rebuild the en subtree, preserving original surface order and merging YAML content."""
    new_en = OrderedDict()

    for surface_key in original_en:
        if surface_key in EMITTED_SHARED_SURFACES:
            if surface_key not in shared_resolved:
                errors.append(f'shared.yml: missing required surface "{surface_key}"')
                new_en[surface_key] = original_en[surface_key]
            else:
                new_en[surface_key] = shared_resolved[surface_key]
            continue

        if surface_key == "meta":
            new_en["meta"] = _assemble_meta(original_en["meta"], pages_resolved, errors)
            continue

        owning_page = _find_owning_page(surface_key)
        if owning_page:
            page = pages_resolved[owning_page]
            if surface_key not in page:
                errors.append(
                    f'pages/{owning_page}.yml: missing required top-level key "{surface_key}"'
                )
                new_en[surface_key] = original_en[surface_key]
            else:
                new_en[surface_key] = page[surface_key]
            continue

        # Out-of-scope surface (maintenance, sw_reset, error_404, error_500, error, etc.)
        new_en[surface_key] = original_en[surface_key]

    # Append any brand-new surfaces declared in page YAMLs but not yet in
    # the original en subtree (e.g. when a new editorial section is added).
    for page_name, cfg in PAGE_SURFACES.items():
        page = pages_resolved[page_name]
        for surface_key in cfg["surfaces"]:
            if surface_key in new_en:
                continue
            if surface_key not in page:
                continue
            new_en[surface_key] = page[surface_key]

    # Same for brand-new shared surfaces declared in shared.yml but not yet
    # in the original en subtree.
    for surface_key in EMITTED_SHARED_SURFACES:
        if surface_key in new_en:
            continue
        if surface_key not in shared_resolved:
            continue
        new_en[surface_key] = shared_resolved[surface_key]

    return new_en


def _find_owning_page(surface_key):
    for page_name, cfg in PAGE_SURFACES.items():
        if surface_key in cfg["surfaces"]:
            return page_name
    return None


def _find_meta_owner(meta_subkey):
    for page_name, cfg in PAGE_SURFACES.items():
        if meta_subkey in cfg["meta_keys"]:
            return page_name
    return None


def _assemble_meta(original_meta, pages_resolved, errors):
    new_meta = OrderedDict()
    for meta_subkey in original_meta:
        owner = _find_meta_owner(meta_subkey)
        if owner is None:
            new_meta[meta_subkey] = original_meta[meta_subkey]
            continue
        page = pages_resolved[owner]
        page_meta = page.get("meta") or {}
        if meta_subkey not in page_meta:
            errors.append(f"pages/{owner}.yml: meta.{meta_subkey} is required but not defined")
            new_meta[meta_subkey] = original_meta[meta_subkey]
        else:
            new_meta[meta_subkey] = page_meta[meta_subkey]
    return new_meta


def lint_unresolved(en_subtree, errors):
    for path, val in walk_strings(en_subtree, ("en",)):
        if "{{" in val:
            errors.append(f"{'.'.join(path)}: contains unresolved template marker: {val!r}")


def lint_duplicate_phrases(pages_resolved, shared_resolved, warnings):
    shared_values = {v for _, v in walk_strings(shared_resolved) if isinstance(v, str)}

    counts = {}
    locations = {}
    for page_name, page in pages_resolved.items():
        for path, val in walk_strings(page, (page_name,)):
            if len(val) >= LONG_PHRASE_CHARS and val not in shared_values:
                counts[val] = counts.get(val, 0) + 1
                locations.setdefault(val, []).append(".".join(path))

    for phrase, count in counts.items():
        if count > DUPE_THRESHOLD:
            sample = locations[phrase][:5]
            tail = f" (+{len(locations[phrase]) - 5} more)" if len(locations[phrase]) > 5 else ""
            warnings.append(
                f"phrase {phrase!r} appears {count}x (>{DUPE_THRESHOLD}); "
                f"consider promoting to shared.yml. Locations: {', '.join(sample)}{tail}"
            )


def main():
    errors = []
    warnings = []

    shared, pages = load_inputs()

    validate_shared_no_chains(shared, errors)
    if errors:
        _emit(errors, warnings)
        sys.exit(1)

    shared_resolved = resolve_refs(shared, shared, errors, "shared.yml")
    pages_resolved = OrderedDict(
        (name, resolve_refs(data, shared, errors, f"pages/{name}.yml"))
        for name, data in pages.items()
    )

    if errors:
        _emit(errors, warnings)
        sys.exit(1)

    with STRINGS_JSON.open() as f:
        strings = json.load(f, object_pairs_hook=OrderedDict)

    new_en = assemble_en_subtree(strings["en"], shared_resolved, pages_resolved, errors)
    lint_unresolved(new_en, errors)

    if errors:
        _emit(errors, warnings)
        sys.exit(1)

    lint_duplicate_phrases(pages_resolved, shared_resolved, warnings)

    strings["en"] = new_en
    out = json.dumps(strings, ensure_ascii=False, indent=2) + "\n"
    STRINGS_JSON.write_text(out, encoding="utf-8")

    _emit(errors, warnings)
    print(
        f"build_copy: rewrote en subtree of {STRINGS_JSON.relative_to(ROOT)} "
        f"({len(pages_resolved)} page yamls + shared.yml)",
        file=sys.stderr,
    )


def _emit(errors, warnings):
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    for e in errors:
        print(f"error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
