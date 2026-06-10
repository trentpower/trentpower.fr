#!/usr/bin/env python3
"""validate_page_provenance.py — every active public page carries one
coherent provenance record.

What this gate proves
---------------------
- every active public HTML page contains exactly one provenance
  comment and exactly one <script type="application/json"
  id="tp-page-record"> block
- the record parses as JSON and carries the required keys
- sourceRepository matches the canonical repository, sourceUrl is the
  repository blob URL derived from sourcePath, edition matches the
  canonical edition
- canonical matches the page's actual public route
- locale coherence: pages in the French tree point at French (or
  shared) sources, English pages at English (or shared) sources
- no active page carries local or private path fragments anywhere in
  its bytes (/home/, /Users/, Desktop/, node_modules, …)

Frozen release snapshots under integrity/releases/<edition>/ are
sealed historical bytes; they are exempt by design (release.json is
their provenance record). The generated editorial review exports are
not public pages and are skipped for the record requirement, but are
still scanned for forbidden fragments.

Usage: validate_page_provenance.py [public-dir]
Quiet on success, precise on failure.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

_TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_TOOLS / "lib"))

from paths import IDENTITY_CANONICAL, PUBLIC_DIR  # noqa: E402

RECORD_RE = re.compile(
    r'<script type="application/json" id="tp-page-record">(.*?)</script>',
    re.DOTALL,
)
COMMENT_RE = re.compile(
    r"<!-- provenance · page record · generated from the public source repository -->"
)

REQUIRED_KEYS = {
    "canonical",
    "sourceRepository",
    "sourcePath",
    "sourceUrl",
    "edition",
    "generated",
}

FORBIDDEN_FRAGMENTS = (
    "/home/",
    "/Users/",
    "C:\\",
    "Desktop/",
    "node_modules",
    "_retired",
    "config.local",
    "id_ed25519",
)


def _expected_canonical(rel: str, base_url: str) -> str:
    if rel == "index.html":
        return f"{base_url}/"
    if rel.endswith("/index.html"):
        return f"{base_url}/{rel.removesuffix('index.html')}"
    return f"{base_url}/{rel}"


def _locale_ok(rel: str, source_path: str) -> bool:
    if source_path.startswith(("content/shared/", "tools/", "templates/")):
        return True
    if rel.startswith("fr/"):
        return source_path.startswith("content/fr/")
    if rel.startswith("en-au/"):
        return source_path.startswith("content/en/")
    # root-level pages (gate handled by shared/, errors fall back to
    # the English edition, /local/ is English-only)
    return source_path.startswith("content/en/")


def main() -> int:
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else PUBLIC_DIR
    if not root.is_dir():
        print(f"  FAIL: page-provenance — public root not found at {root}")
        return 1

    with open(IDENTITY_CANONICAL, encoding="utf-8") as f:
        canon = json.load(f)
    repo = canon.get("repository", {})
    repo_url, branch = repo.get("url", ""), repo.get("branch", "")
    edition = canon.get("edition", "")
    base_url = canon.get("url", "").rstrip("/")
    if not (repo_url and branch and edition and base_url):
        print("  FAIL: page-provenance — identity_canonical.json missing repository/edition/url")
        return 1

    fails: list[str] = []
    checked = 0
    for path in sorted(root.rglob("*.html")):
        rel = str(path.relative_to(root)).replace("\\", "/")
        text = path.read_text(encoding="utf-8")

        for frag in FORBIDDEN_FRAGMENTS:
            if frag in text:
                fails.append(f"{rel}: forbidden fragment {frag!r} in page bytes")

        if re.match(r"integrity/releases/[^/]+/", rel) or rel.startswith("editorial/"):
            continue  # sealed snapshots / non-public review exports

        checked += 1
        comments = COMMENT_RE.findall(text)
        records = RECORD_RE.findall(text)
        if len(comments) != 1:
            fails.append(f"{rel}: expected 1 provenance comment, found {len(comments)}")
        if len(records) != 1:
            fails.append(f"{rel}: expected 1 tp-page-record, found {len(records)}")
            continue

        try:
            rec = json.loads(records[0])
        except json.JSONDecodeError as e:
            fails.append(f"{rel}: tp-page-record is not valid JSON ({e})")
            continue

        missing = REQUIRED_KEYS - set(rec)
        if missing:
            fails.append(f"{rel}: tp-page-record missing keys {sorted(missing)}")
            continue
        if rec["sourceRepository"] != repo_url:
            fails.append(f"{rel}: sourceRepository {rec['sourceRepository']!r} != {repo_url!r}")
        if rec["edition"] != edition:
            fails.append(f"{rel}: edition {rec['edition']!r} != {edition!r}")
        if rec["generated"] is not True:
            fails.append(f"{rel}: generated must be true")
        sp = rec["sourcePath"]
        if sp.startswith(("/", "~")) or ".." in sp:
            fails.append(f"{rel}: sourcePath {sp!r} is not repository-relative")
        expected_url = f"{repo_url}/blob/{branch}/{sp}"
        if rec["sourceUrl"] != expected_url:
            fails.append(f"{rel}: sourceUrl {rec['sourceUrl']!r} != {expected_url!r}")
        expected_canonical = _expected_canonical(rel, base_url)
        if rec["canonical"] != expected_canonical:
            fails.append(f"{rel}: canonical {rec['canonical']!r} != {expected_canonical!r}")
        if not _locale_ok(rel, sp):
            fails.append(f"{rel}: locale mismatch — source {sp!r} for tree {rel.split('/')[0]!r}")
        tp = rec.get("templatePath")
        if tp and (tp.startswith(("/", "~")) or ".." in tp):
            fails.append(f"{rel}: templatePath {tp!r} is not repository-relative")

    if fails:
        print(f"  FAIL: page-provenance — {len(fails)} finding(s) across {checked} pages:")
        for f_ in fails[:40]:
            print(f"    {f_}")
        if len(fails) > 40:
            print(f"    … {len(fails) - 40} more")
        return 1
    print(f"  OK: page-provenance — {checked} pages carry one coherent record each")
    return 0


if __name__ == "__main__":
    sys.exit(main())
