#!/usr/bin/env python3
"""
trentpower.fr
Inject the per-page provenance record into every active public page.

Inputs:
- tools/config/identity_canonical.json (edition + repository)
- content/routes.json (route inventory: canonical, content, template)
- final rendered public HTML

Outputs (per active page, injected just before </head>):
- a human-readable provenance comment (canonical url, public source
  location, repository, edition)
- a machine-readable <script type="application/json"
  id="tp-page-record"> block carrying the same facts

Constraints:
- Public GitHub paths only. Local build paths, private directories and
  machine names must never appear in the injected bytes.
- Deterministic: same inputs, same bytes. Idempotent: re-running
  replaces the previous record instead of stacking a second one.
- Frozen release snapshots under integrity/releases/<edition>/ are
  sealed historical bytes and are never touched; their provenance is
  carried by release.json inside each archive directory.
- Runs after every page generator and before the integrity manifest,
  verification map and source mirrors, so the record is part of the
  signed, mirrored bytes.
"""

import json
import os
import pathlib
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
import routes as _routes  # noqa: E402
from paths import (  # noqa: E402
    IDENTITY_CANONICAL as IDENTITY_CANONICAL,
)
from paths import (  # noqa: E402
    PUBLIC_DIR as ROOT,
)
from paths import (  # noqa: E402
    REPO_ROOT as REPO_ROOT,
)

ROUTES_JSON = REPO_ROOT / "content" / "routes.json"

# fragments that must never appear in injected bytes. the generator
# fails loudly rather than shipping a leak.
FORBIDDEN_FRAGMENTS = (
    "/home/",
    "/Users/",
    "Desktop/",
    ".env",
    "node_modules",
    "_retired",
    "/private/",
    "config.local",
)

RECORD_ID = "tp-page-record"

# strip any previously injected block so the sweep is idempotent.
# both historical shapes are matched: the original multi-line comment
# and the current one-line section label.
_OLD_COMMENT_RE = re.compile(
    r"\n?[ \t]*<!--(?:\n  page record · provenance\n.*?| provenance · page record[^>]*)-->\n",
    re.DOTALL,
)
_OLD_RECORD_RE = re.compile(
    r'[ \t]*<script type="application/json" id="tp-page-record">.*?</script>\n',
    re.DOTALL,
)


def _load_json(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _error_pages() -> list[tuple[str, str, str]]:
    """(relative html path, language code, content yaml) for every
    error document: per-tree bilingual copies plus the root English
    fallbacks served for unmatched requests."""
    codes = ("403", "404", "500", "maintenance")
    out = []
    for lang in _routes.languages():
        seg = _routes.lang_url_segment(lang)
        for code in codes:
            out.append((f"{seg}/{code}.html", lang, f"content/{lang}/pages/system.yml"))
    for code in codes:
        out.append((f"{code}.html", "en", "content/en/pages/system.yml"))
    return out


def build_page_map(base_url: str) -> dict[str, dict]:
    """relative html path under public/ → provenance facts.

    sourcePath is the most honest authored input: the content YAML for
    rendered pages, the generator module for machine-assembled
    surfaces. templatePath is present only where a page template
    participates.
    """
    pages: dict[str, dict] = {}

    routes = _load_json(ROUTES_JSON)["routes"]
    for r in routes:
        rel = r["path"].strip("/") + "/index.html"
        pages[rel] = {
            "canonical": r["canonical"],
            "sourcePath": r["content"],
            "templatePath": f"templates/pages/{r['template']}.html",
        }

    for rel, _lang, content in _error_pages():
        code = pathlib.Path(rel).stem
        pages[rel] = {
            "canonical": f"{base_url}/{rel}",
            "sourcePath": content,
            "templatePath": f"templates/pages/{code}.html",
        }

    # the root language gate — its own template + bilingual copy file,
    # not the English homepage source.
    pages["index.html"] = {
        "canonical": f"{base_url}/",
        "sourcePath": "content/shared/gate.yml",
        "templatePath": "templates/pages/language-gate.html",
    }

    # single-edition diagnostic surface.
    pages["local/index.html"] = {
        "canonical": f"{base_url}/local/",
        "sourcePath": "content/en/pages/local.yml",
        "templatePath": "templates/pages/local.html",
    }

    # machine-assembled surfaces: no single authored content file, so
    # the honest source is the generator module itself.
    for rel, generator in (
        ("documentation/index.html", "tools/build/generate_documentation.py"),
        ("tests/index.html", "tools/build/generate_tests_page.py"),
        ("source/index.html", "tools/build/generate_source_view.py"),
        ("source/view/index.html", "tools/build/generate_source_reader.py"),
    ):
        pages[rel] = {
            "canonical": f"{base_url}/{rel.removesuffix('index.html')}",
            "sourcePath": generator,
            "templatePath": None,
        }

    return pages


def _active_html() -> list[str]:
    import glob

    out = []
    for p in sorted(glob.glob("**/*.html", recursive=True)):
        if re.match(r"integrity/releases/[^/]+/", p):
            continue
        if p.startswith("editorial/"):
            continue
        out.append(p)
    return out


def _block(meta: dict, repo_url: str, branch: str, edition: str) -> str:
    """The injected surface mirrors the head's own design language: a
    terse one-line section comment (like "head · structured data") and
    a pretty-printed JSON body indented exactly like the JSON-LD graph
    beside it. The record is both the machine surface and the
    human-readable one."""
    source_url = f"{repo_url}/blob/{branch}/{meta['sourcePath']}"
    record = {
        "canonical": meta["canonical"],
        "sourceRepository": repo_url,
        "sourcePath": meta["sourcePath"],
    }
    if meta["templatePath"]:
        record["templatePath"] = meta["templatePath"]
    record["sourceUrl"] = source_url
    record["edition"] = edition
    record["generated"] = True
    record_js = json.dumps(record, ensure_ascii=True, indent=2)
    return (
        "\n  <!-- provenance · page record · generated from the public source repository -->\n"
        f'  <script type="application/json" id="{RECORD_ID}">\n'
        f"{record_js}\n"
        "  </script>\n"
    )


def inject(rel: str, meta: dict, repo_url: str, branch: str, edition: str) -> bool:
    path = pathlib.Path(rel)
    text = path.read_text(encoding="utf-8")
    block = _block(meta, repo_url, branch, edition)
    for frag in FORBIDDEN_FRAGMENTS:
        if frag in block:
            raise SystemExit(f"FAIL: forbidden fragment {frag!r} in provenance block for {rel}")
    new = _OLD_COMMENT_RE.sub("", text)
    new = _OLD_RECORD_RE.sub("", new)
    if "</head>" not in new:
        raise SystemExit(f"FAIL: no </head> in {rel}")
    new = new.replace("</head>", block + "</head>", 1)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def main() -> int:
    os.chdir(ROOT)
    canon = _load_json(IDENTITY_CANONICAL)
    repo = canon.get("repository", {})
    repo_url, branch = repo.get("url"), repo.get("branch")
    edition = canon.get("edition")
    base_url = canon.get("url", "").rstrip("/")
    if not (repo_url and branch and edition and base_url):
        print("FAIL: identity_canonical.json missing repository/edition/url", file=sys.stderr)
        return 1

    pages = build_page_map(base_url)
    active = _active_html()

    unmapped = [p for p in active if p not in pages]
    if unmapped:
        print("FAIL: active pages without a provenance mapping:", file=sys.stderr)
        for p in unmapped:
            print(f"  {p}", file=sys.stderr)
        return 1

    # authored sources must exist in the repository; a missing file
    # means the mapping (not the page) is wrong.
    missing_src = sorted(
        {m["sourcePath"] for r, m in pages.items() if r in active}
        | {m["templatePath"] for r, m in pages.items() if r in active and m["templatePath"]}
    )
    missing_src = [s for s in missing_src if not (REPO_ROOT / s).is_file()]
    if missing_src:
        print("FAIL: provenance source paths missing on disk:", file=sys.stderr)
        for s in missing_src:
            print(f"  {s}", file=sys.stderr)
        return 1

    changed = sum(1 for rel in active if inject(rel, pages[rel], repo_url, branch, edition))
    print(f"  → page provenance: {len(active)} pages carry a record ({changed} updated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
