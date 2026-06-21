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

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the whole gate runs over a fixture repo with no monkeypatching.
`load(repo)` reads + validates the canonical identity; `evaluate(repo, ctx)` is
the pure compute path returning a Result (it never prints or exits); `main()` is
the only adapter that prints and exits. Behaviour is byte-identical to the
former PUBLIC_DIR-walking script.

Usage: validate_page_provenance.py
Quiet on success, precise on failure.
"""

from __future__ import annotations

import json
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

# repo-relative location of the canonical identity (resolved through the seam).
IDENTITY_CANONICAL_REL = "tools/config/identity_canonical.json"

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


# named accessors over the shared Repo seam. the public-tree knowledge (the
# "public/" prefix, the recursive html walk) lives here in the validator.
def _read_public(repo: Repo, prel: str) -> str:
    return repo.read(f"public/{prel}")


def _public_html(repo: Repo) -> list[str]:
    """public-relative posix paths of every .html under public/, sorted."""
    prefix = "public/"
    return [rel[len(prefix) :] for rel in repo.glob(f"{prefix}**/*.html")]


# ---------------------------------------------------------------------------
# Ctx / Result — the values that flow through the interface. load() produces
# Ctx (or errors); evaluate() produces Result; main() renders it. tests assert
# on Result, never on stdout.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Ctx:
    repo_url: str
    branch: str
    edition: str
    base_url: str


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    oks: list[str] = field(default_factory=list)
    checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.fails


# ---------------------------------------------------------------------------
# load — read + validate the canonical identity. returns (ctx, errors); never
# prints/exits. mirrors the original main()'s up-front canonical checks.
# ---------------------------------------------------------------------------
def load(repo: Repo) -> tuple[Ctx | None, list[str]]:
    if not (repo.root / "public").is_dir():
        return None, [f"public root not found at {repo.root / 'public'}"]
    canon = json.loads(repo.read(IDENTITY_CANONICAL_REL))
    repo_block = canon.get("repository", {})
    repo_url, branch = repo_block.get("url", ""), repo_block.get("branch", "")
    edition = canon.get("edition", "")
    base_url = canon.get("url", "").rstrip("/")
    if not (repo_url and branch and edition and base_url):
        return None, ["identity_canonical.json missing repository/edition/url"]
    return Ctx(repo_url=repo_url, branch=branch, edition=edition, base_url=base_url), []


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo. this is the test surface. lifted verbatim from the original main() loop.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo, ctx: Ctx) -> Result:
    r = Result()
    repo_url, branch, edition, base_url = ctx.repo_url, ctx.branch, ctx.edition, ctx.base_url
    fails = r.fails

    checked = 0
    for rel in _public_html(repo):
        text = _read_public(repo, rel)

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

    r.checked = checked
    r.oks.append(f"page-provenance — {checked} pages carry one coherent record each")
    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. loads, evaluates, renders, returns exit
# code. the only place stdout and exit codes live; reproduces the original
# OK/FAIL text contract exactly.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)

    ctx, errors = load(repo)
    if errors:
        for e in errors:
            print(f"  FAIL: page-provenance — {e}")
        return 1

    r = evaluate(repo, ctx)
    if r.fails:
        print(f"  FAIL: page-provenance — {len(r.fails)} finding(s) across {r.checked} pages:")
        for f_ in r.fails[:40]:
            print(f"    {f_}")
        if len(r.fails) > 40:
            print(f"    … {len(r.fails) - 40} more")
        return 1
    print(f"  OK: {r.oks[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
