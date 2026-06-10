#!/usr/bin/env python3
"""One-shot bootstrap: extract current en subtree of tools/build/copy/strings.json
into content/en/shared.yml + content/en/pages/*.yml.

Run once to seed the YAML source tree. After bootstrap, content/en/*.yml is
the source of truth; this script is no longer needed for ongoing work but
is retained for re-bootstrap if needed.

Verification: after running this script, run tools/build/copy/build_copy.py and
diff the resulting strings.json against the pre-bootstrap version — the
file should be byte-identical.
"""

from __future__ import annotations

import json
import sys
from collections import OrderedDict
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

# Reuse surface mapping from build_copy.py
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
from build_copy import (  # noqa: E402
    CONTENT_DIR,
    EMITTED_SHARED_SURFACES,
    PAGE_SURFACES,
    ROOT,
    STRINGS_JSON,
)

# Curated alias targets that promote known duplicated values to shared.* references.
# Format: (predicate_fn(path_tuple, value) -> bool, "shared.x.y.z")
# Predicates run against (path_tuple_after_en, value).
ALIAS_RULES = [
    (
        lambda p, v: (
            p[-3:] == ("print", "footer", "proof")
            and v == "Private · Static · Signed · No tracking"
        ),
        "shared.site.proof_line",
    ),
    (
        lambda p, v: p[-1] == "signature" and v == "Detached signature",
        "shared.verification.signature",
    ),
    (
        lambda p, v: (
            p[-3:] == ("print", "card", "02")
            and p[-4] == "release_archive"
            and v == "Detached signature"
        ),
        "shared.verification.signature",
    ),
    (
        lambda p, v: (
            p == ("integrity", "print", "card", "02", "title") and v == "Detached signature"
        ),
        "shared.verification.signature",
    ),
]

# Seed shared.yml. Alias sections (site, verification, actions) are extracted
# from known canonical values. Emitted surfaces (footer, modal, cite, copy,
# trust_routes) are pulled verbatim from the en subtree.
SHARED_ALIAS_SOURCES = {
    "site": {
        "name": ("hero", None, "trentpower.fr"),  # literal — not in tree
        "location": ("footer", "location", None),
        "proof_line": (None, None, "Private · Static · Signed · No tracking"),
        "edition_label": ("cite", "edition_label", None),
    },
    "verification": {
        "manifest": (None, None, "Signed manifest"),
        "signature": (None, None, "Detached signature"),
        "public_key": (None, None, "Public key"),
        "source_mirror": (None, None, "Source mirror"),
        "page_fingerprint": (None, None, "Page fingerprint"),
        "canonical_url": (None, None, "Canonical URL"),
    },
    "actions": {
        "copy": (None, None, "Copy"),
        "copied": (None, None, "Copied"),
        "close": ("modal", "close", None),
        "view_source": (None, None, "View source"),
        "verify_page": (None, None, "Verify this page"),
        "print_profile": (None, None, "Print profile"),
    },
}


def get_path(d, *keys):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def derive_shared_aliases(en):
    """Build shared.yml alias sections from canonical values in en subtree."""
    out = OrderedDict()
    for section, fields in SHARED_ALIAS_SOURCES.items():
        out[section] = OrderedDict()
        for alias_key, spec in fields.items():
            surface, sub, fallback = spec
            value = None
            if surface and sub:
                value = get_path(en, surface, sub)
            if not value and fallback:
                value = fallback
            if value is None:
                print(
                    f"bootstrap: warning — could not derive shared.{section}.{alias_key}",
                    file=sys.stderr,
                )
                continue
            out[section][alias_key] = value
    return out


def apply_alias_rules(en_path_tuple, value):
    """If value at this path matches a known alias rule, return the reference template."""
    for predicate, ref in ALIAS_RULES:
        try:
            if predicate(en_path_tuple, value):
                return "{{ " + ref + " }}"
        except (IndexError, TypeError):
            continue
    return value


def transform_value(node, path):
    """Recursively transform leaves, inserting shared.* references where known."""
    if isinstance(node, str):
        return apply_alias_rules(path, node)
    if isinstance(node, dict):
        return OrderedDict((k, transform_value(v, path + (k,))) for k, v in node.items())
    if isinstance(node, list):
        return [transform_value(v, path + (f"[{i}]",)) for i, v in enumerate(node)]
    return node


def extract_emitted_shared_surfaces(en):
    out = OrderedDict()
    for surface in EMITTED_SHARED_SURFACES:
        if surface in en:
            out[surface] = en[surface]
    return out


def build_shared_yaml(en):
    shared = OrderedDict()
    aliases = derive_shared_aliases(en)
    for k, v in aliases.items():
        shared[k] = v
    surfaces = extract_emitted_shared_surfaces(en)
    for k, v in surfaces.items():
        shared[k] = v
    return shared


def build_page_yaml(en, page_name, cfg):
    out = OrderedDict()

    # Meta block first
    meta_block = OrderedDict()
    for meta_subkey in cfg["meta_keys"]:
        meta_node = get_path(en, "meta", meta_subkey)
        if meta_node is not None:
            meta_block[meta_subkey] = meta_node
    if meta_block:
        out["meta"] = meta_block

    # Each surface owned by this page
    for surface in cfg["surfaces"]:
        if surface in en:
            transformed = transform_value(en[surface], (surface,))
            out[surface] = transformed
    return out


def dump_yaml(data, path: Path):
    """Write deterministic YAML with stable ordering and reasonable string wrapping."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Use a custom representer to preserve OrderedDict order and avoid sorting
    class OrderedDumper(yaml.SafeDumper):
        pass

    def repr_ordereddict(dumper, data):
        return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())

    def repr_str(dumper, data):
        if "\n" in data:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    OrderedDumper.add_representer(OrderedDict, repr_ordereddict)
    OrderedDumper.add_representer(str, repr_str)

    with path.open("w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            Dumper=OrderedDumper,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=10000,  # avoid line wrapping inside strings
        )


def main():
    with STRINGS_JSON.open() as f:
        strings = json.load(f, object_pairs_hook=OrderedDict)
    en = strings["en"]

    shared = build_shared_yaml(en)
    dump_yaml(shared, CONTENT_DIR / "shared.yml")
    print(f"wrote {(CONTENT_DIR / 'shared.yml').relative_to(ROOT)}", file=sys.stderr)

    pages_dir = CONTENT_DIR / "pages"
    for page_name, cfg in PAGE_SURFACES.items():
        page = build_page_yaml(en, page_name, cfg)
        dump_yaml(page, pages_dir / f"{page_name}.yml")
        print(f"wrote {(pages_dir / f'{page_name}.yml').relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
