#!/usr/bin/env python3
"""generate_routes_json.py -- project routes.yml into an editor-facing routes.json.

content/shared/routes.yml stays the single source of truth for the bilingual
URL architecture. This script *derives* content/routes.json -- a flat,
machine-readable registry tooling reads to list pages, locate their
content file and schema, and resolve canonical / hreflang. It is generated,
never hand-edited.

Mirrors the generate_htaccess.py --check pattern: a drift gate (registered as
the `routes_json_drift` blocking check) fails the build if the committed
routes.json no longer matches what routes.yml would produce.

Usage:
    python3 tools/generate_routes_json.py          # (re)write content/routes.json
    python3 tools/generate_routes_json.py --check   # exit 1 if committed file drifted
"""

from __future__ import annotations

import argparse
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
from paths import CONTENT_DIR, REPO_ROOT  # noqa: E402

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
import routes as routemap  # noqa: E402

# route key -> content stem (the YAML file under content/<lang>/pages/ and the
# schema under schemas/content/). imported from the renderer so the mapping has
# a single source of truth.
from render_pages import PAGE_YAML  # noqa: E402

OUT_PATH = CONTENT_DIR / "routes.json"
SCHEMA_VERSION = 1

# stems that are cryptographic / transparency trust surfaces.
TRUST_STEMS = {"security", "integrity", "verify", "source"}


def _route_entry(key: str, lang: str) -> dict:
    stem = PAGE_YAML[key]
    seg = routemap.lang_url_segment(lang)
    cluster = routemap.hreflang_cluster(key)
    self_tag = routemap.lang_bcp47(lang)
    alternate = [
        {"hreflang": tag, "href": href} for tag, href in cluster.items() if tag != self_tag
    ]
    return {
        "id": f"{key}.{seg}",
        "route_key": key,
        "path": routemap.route_path(key, lang),
        "language": routemap.lang_bcp47(lang),
        "locale": routemap.lang_og_locale(lang),
        "template": routemap.template_name(key),
        "content": f"content/{lang}/pages/{stem}.yml",
        "schema": f"schemas/content/{stem}.schema.json",
        "canonical": routemap.route_url(key, lang),
        "alternate": alternate,
        "editable": True,
        "preview": True,
        "trust_surface": stem in TRUST_STEMS,
    }


def build() -> dict:
    routes = []
    for key in routemap.route_keys():
        for lang in routemap.languages():
            routes.append(_route_entry(key, lang))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_from": "content/shared/routes.yml",
        "note": "GENERATED — edit content/shared/routes.yml (the source of truth), "
        "not this file. Regenerate with tools/generate_routes_json.py.",
        "languages": [routemap.lang_bcp47(lang) for lang in routemap.languages()],
        "routes": routes,
    }


def _serialize(obj: dict) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="derive content/routes.json from routes.yml")
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed routes.json differs from freshly generated",
    )
    args = ap.parse_args(argv)

    text = _serialize(build())

    if args.check:
        if not OUT_PATH.exists():
            print(
                f"FAIL: {OUT_PATH.relative_to(REPO_ROOT)} is missing — run generate_routes_json.py"
            )
            return 1
        current = OUT_PATH.read_text(encoding="utf-8")
        if current != text:
            print(
                f"FAIL: {OUT_PATH.relative_to(REPO_ROOT)} drifted from routes.yml — "
                "regenerate with tools/generate_routes_json.py"
            )
            return 1
        print(f"OK: {OUT_PATH.relative_to(REPO_ROOT)} matches routes.yml")
        return 0

    OUT_PATH.write_text(text, encoding="utf-8")
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)} ({len(build()['routes'])} route entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
