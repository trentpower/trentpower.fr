#!/usr/bin/env python3
"""validate_public_exposure.py — prove the public-exposure manifest covers reality.

The manifest at tools/config/public-exposure.json declares every URL shape the
deployable public/ tree is allowed to expose. This validator walks the
on-disk public/ tree and proves three independent invariants:

  1. every file under public/ is reachable through at least one allow
     rule in the manifest (no silently-deployed file)
  2. no file under public/ matches a deny rule (no leaked secret, no
     forbidden extension, no .git/.env/etc landmines)
  3. every internal link in every public *.html page resolves both
     against an allow rule AND to a real file on disk (no dangling
     <a href> / <link href> / <script src> / og:image / preload)
  4. the integrity artefact baseline is present (root + per-edition)

Exit 0 = green; exit 1 = at least one violation, with all violators
listed (don't stop on first).

Shape (deep module, small interface). The external interface is `main() -> int`
plus the OK/FAIL text contract. Internally two dependencies are injected seams —
`Repo(root)` for the filesystem and a `pre_archive` flag for the pre-signature
gate pass — so the whole gate is exercised through `evaluate(repo, manifest,
pre_archive) -> Result` over a fixture repo, with no monkeypatching and no
reliance on process environment. Compute (`evaluate`) is separate from render
(`main`): the former returns a Result and never prints or exits; the latter is
the only side-effecting adapter.
"""

from __future__ import annotations

import json
import os
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

MANIFEST_REL = "tools/config/public-exposure.json"
SCHEMA_TAG = "trentpower.public-exposure.v1"

# the apache .htaccess file lives at public/.htaccess but is never
# served to a browser — it controls rewrites / headers / mime types.
# treat it as neither allow-listed nor deny-flagged.
APACHE_CONTROL_FILE = ".htaccess"

# /.well-known/ starts with a dot but is the IETF-blessed public
# discovery prefix. it must escape the "leading-dot path" deny.
WELL_KNOWN_PREFIX = ".well-known/"


# named accessors over the shared Repo seam. the public-tree knowledge stays
# here in the validator, not on the seam.
def _read_public(repo: Repo, prel: str) -> str:
    return repo.read(f"public/{prel}")


def _public_is_file(repo: Repo, prel: str) -> bool:
    return repo.is_file(f"public/{prel}")


# ─── glob → regex ───────────────────────────────────────────────
# python's fnmatch doesn't natively understand ** as a path-spanning
# wildcard. convert manifest globs to a regex with the conventional
# semantics:
#
#   **   →  .*                 (any path, including /)
#   *    →  [^/]*              (any single segment chunk)
#   ?    →  [^/]               (any single char, not /)
#   .    →  \.                 (literal dot)
#
# anchored at both ends so "/fonts/*.woff2" doesn't accidentally match
# "/fonts/sub/foo.woff2".
def glob_to_regex(pattern: str) -> re.Pattern:
    out: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        if c == "?":
            out.append("[^/]")
            i += 1
            continue
        if c in r".+()[]{}|^$\\":
            out.append("\\" + c)
            i += 1
            continue
        out.append(c)
        i += 1
    return re.compile("^" + "".join(out) + "$")


def compile_globs(globs: list[str]) -> list[re.Pattern]:
    return [glob_to_regex(g) for g in globs]


def any_match(url: str, patterns: list[re.Pattern]) -> bool:
    return any(p.match(url) for p in patterns)


# ─── disk walk ──────────────────────────────────────────────────
def walk_public_files(
    repo: Repo,
    deploy_excluded: list[re.Pattern] | None = None,
) -> list[tuple[str, str]]:
    """Return [(public_rel, server_url)] for every file under public/.
    server_url is leading-slash + posix relpath.

    Files matching any pattern in deploy_excluded are dropped — they
    exist in the repo but the sftp deploy pipeline excludes them from
    the live web root, so they cannot be exposed and must not be
    validated against allow / deny rules.
    """
    out: list[tuple[str, str]] = []
    deploy_excluded = deploy_excluded or []
    prefix = "public/"
    for repo_rel in repo.glob("public/**/*"):
        rel = repo_rel[len(prefix) :]
        url = "/" + rel
        if any(p.match(url) for p in deploy_excluded):
            continue
        out.append((rel, url))
    return out


# ─── allow-rule matcher ─────────────────────────────────────────
class AllowRules:
    def __init__(self, manifest: dict) -> None:
        self.routes = set(manifest.get("public_routes", []))
        self.root_files = set(manifest.get("public_root_files", []))
        self.well_known = set(manifest.get("public_well_known_files", []))
        self.verify_files = set(manifest.get("public_verify_files", []))
        self.editorial_files = set(manifest.get("public_editorial_files", []))
        self.documentation_files = set(manifest.get("public_documentation_files", []))
        self.asset_globs = compile_globs(manifest.get("public_asset_globs", []))
        self.versioned_globs = compile_globs(manifest.get("public_versioned_globs", []))
        self.source_globs = compile_globs(manifest.get("public_source_globs", []))
        self.integrity_globs = compile_globs(manifest.get("public_integrity_globs", []))

    def url_directory(self, url: str) -> str | None:
        """Return the directory form of a URL ending in index.html, else None."""
        if url.endswith("/index.html"):
            return url[: -len("index.html")]
        if url == "/index.html":
            return "/"
        return None

    def matches(self, url: str) -> bool:
        # exact-match sets.
        if url in self.root_files:
            return True
        if url in self.well_known:
            return True
        if url in self.verify_files:
            return True
        if url in self.editorial_files:
            return True
        if url in self.documentation_files:
            return True
        # directory route — for index.html files, also test the parent
        # directory URL.
        dir_url = self.url_directory(url)
        if dir_url is not None and dir_url in self.routes:
            return True
        if url in self.routes:
            return True
        # glob families.
        if any_match(url, self.asset_globs):
            return True
        if any_match(url, self.versioned_globs):
            return True
        if any_match(url, self.source_globs):
            return True
        if any_match(url, self.integrity_globs):
            return True
        return False


# ─── deny-rule matcher ──────────────────────────────────────────
class DenyRules:
    def __init__(self, manifest: dict) -> None:
        self.ext_set = {e.lower() for e in manifest.get("deny_extension_patterns", [])}
        self.path_globs = compile_globs(manifest.get("deny_path_patterns", []))
        self.basename_globs = compile_globs(manifest.get("deny_basename_patterns", []))

    def violates(self, url: str, basename: str) -> list[str]:
        """Return list of deny-rule labels this file trips, [] if clean."""
        hits: list[str] = []
        ext = os.path.splitext(basename)[1].lower()
        if ext and ext in self.ext_set:
            hits.append(f"extension {ext!r}")
        for pat in self.basename_globs:
            if pat.match(basename):
                hits.append(f"basename matches {pat.pattern!r}")
                break
        for pat in self.path_globs:
            if pat.match(url):
                hits.append(f"path matches {pat.pattern!r}")
                break
        return hits


# ─── url → disk path (mirrors public_inventory.url_to_disk_path) ─
def url_to_disk_path(url: str) -> str:
    """/  → index.html ; /foo/ → foo/index.html ; /foo.css → foo.css."""
    if not url.startswith("/"):
        raise ValueError(f"expected leading slash, got {url!r}")
    if url == "/":
        return "index.html"
    rel = url.lstrip("/")
    if url.endswith("/"):
        return rel + "index.html"
    return rel


# ─── html link extraction ───────────────────────────────────────
# regex-based; matches the project's house style (other validators
# use regex over HTML, not bs4). attribute order tolerated, single or
# double quotes both accepted.

# generic attribute patterns. each captures the URL value.
_HREF_RE = re.compile(r"""\bhref\s*=\s*(['"])([^'"]+)\1""", re.IGNORECASE)
_SRC_RE = re.compile(r"""\bsrc\s*=\s*(['"])([^'"]+)\1""", re.IGNORECASE)
_DATA_SRC_RE = re.compile(r"""\bdata-src\s*=\s*(['"])([^'"]+)\1""", re.IGNORECASE)
_SRCSET_RE = re.compile(r"""\bsrcset\s*=\s*(['"])([^'"]+)\1""", re.IGNORECASE)
_OG_IMG_RE = re.compile(
    r"""<meta\b[^>]*\bproperty\s*=\s*(['"])og:image\1[^>]*\bcontent\s*=\s*(['"])([^'"]+)\2""",
    re.IGNORECASE,
)
_OG_IMG_REV_RE = re.compile(
    r"""<meta\b[^>]*\bcontent\s*=\s*(['"])([^'"]+)\1[^>]*\bproperty\s*=\s*(['"])og:image\3""",
    re.IGNORECASE,
)
_TW_IMG_RE = re.compile(
    r"""<meta\b[^>]*\bname\s*=\s*(['"])twitter:image\1[^>]*\bcontent\s*=\s*(['"])([^'"]+)\2""",
    re.IGNORECASE,
)
_TW_IMG_REV_RE = re.compile(
    r"""<meta\b[^>]*\bcontent\s*=\s*(['"])([^'"]+)\1[^>]*\bname\s*=\s*(['"])twitter:image\3""",
    re.IGNORECASE,
)


def extract_urls(html: str) -> set[str]:
    """Pull every internal URL from one html document.

    Returns server-relative URLs with query strings stripped. Skips
    mailto:, tel:, anchor-only #fragments, and any URL not starting
    with '/'.
    """
    found: set[str] = set()

    def keep(raw: str) -> None:
        if not raw:
            return
        u = raw.strip()
        if not u:
            return
        # strip fragments — anchors are page-internal.
        if "#" in u:
            u = u.split("#", 1)[0]
            if not u:
                return
        # strip query strings — versioned urls like /styles.css?v=2026-05-17
        # should match the same allow rule as /styles.css.
        if "?" in u:
            u = u.split("?", 1)[0]
            if not u:
                return
        lower = u.lower()
        if lower.startswith(("mailto:", "tel:", "javascript:", "data:")):
            return
        if lower.startswith(("http://", "https://", "//")):
            return
        if not u.startswith("/"):
            return
        found.add(u)

    for _, val in _HREF_RE.findall(html):
        keep(val)
    for _, val in _SRC_RE.findall(html):
        keep(val)
    for _, val in _DATA_SRC_RE.findall(html):
        keep(val)
    # srcset values are comma-separated candidate strings, each with
    # an optional width/density descriptor (e.g. "foo.png 2x"). split
    # on commas, then on whitespace, and keep the leading URL token.
    for _, val in _SRCSET_RE.findall(html):
        for candidate in val.split(","):
            tok = candidate.strip().split()
            if tok:
                keep(tok[0])
    # og:image / twitter:image — attribute order varies in the wild,
    # so try both orderings.
    for m in _OG_IMG_RE.finditer(html):
        keep(m.group(3))
    for m in _OG_IMG_REV_RE.finditer(html):
        keep(m.group(2))
    for m in _TW_IMG_RE.finditer(html):
        keep(m.group(3))
    for m in _TW_IMG_REV_RE.finditer(html):
        keep(m.group(2))

    return found


# ─── steps ──────────────────────────────────────────────────────
def step_file_coverage(files: list[tuple[str, str]], allow: AllowRules) -> list[str]:
    """Step 2 — every public file is allow-list reachable."""
    fails: list[str] = []
    for rel, url in files:
        basename = rel.rsplit("/", 1)[-1]
        # the apache control file is never served; skip allow check.
        if rel == APACHE_CONTROL_FILE:
            continue
        # try url first.
        if allow.matches(url):
            continue
        # for index.html, also try the directory route form.
        if basename == "index.html":
            dir_url = url[: -len("index.html")]
            if dir_url in allow.routes:
                continue
            if allow.matches(dir_url):
                continue
        fails.append(f"UNCOVERED: {url} (no allow rule matched)")
    return fails


def step_deny_coverage(files: list[tuple[str, str]], deny: DenyRules) -> list[str]:
    """Step 3 — no public file matches deny patterns."""
    fails: list[str] = []
    for rel, url in files:
        basename = rel.rsplit("/", 1)[-1]
        # exceptions: apache control file and the well-known prefix
        # both legitimately have leading-dot components.
        if rel == APACHE_CONTROL_FILE:
            continue
        if rel.startswith(WELL_KNOWN_PREFIX):
            # still apply deny but the leading-dot path glob should
            # not punish .well-known. caller-supplied deny patterns
            # must be authored to allow this; if they don't, we still
            # honour them — but the common case is that path globs
            # target .git/.env, not .well-known. continue running
            # the deny check.
            pass
        hits = deny.violates(url, basename)
        if hits:
            fails.append(f"DENY: {url} ({'; '.join(hits)})")
    return fails


def step_integrity_artefacts(repo: Repo, manifest: dict, pre_archive: bool) -> list[str]:
    """Step 5 — baseline integrity files exist on disk."""
    fails: list[str] = []
    required = [
        "integrity.json",
        "integrity.json.sig",
        ".well-known/pgp-key.asc",
        "SHA256SUMS",
        "SHA256SUMS.sig",
    ]
    edition = manifest.get("edition", "")
    if isinstance(edition, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", edition):
        if not pre_archive:
            required.append(f"integrity/releases/{edition}/SHA256SUMS")
            required.append(f"integrity/releases/{edition}/SHA256SUMS.sig")
    else:
        fails.append(
            f"INTEGRITY: manifest edition {edition!r} is not an ISO date — "
            f"cannot derive per-edition SHA256SUMS paths"
        )
    for rel in required:
        if not _public_is_file(repo, rel):
            fails.append(f"INTEGRITY: required artefact missing — /{rel}")
    return fails


_RELEASE_ARTEFACT_RE = re.compile(r"\.(zip|tar\.gz|sig|sha256)$", re.IGNORECASE)


def step_html_links(
    repo: Repo,
    files: list[tuple[str, str]],
    allow: AllowRules,
    current_edition: str | None,
    pre_archive: bool,
) -> tuple[list[str], int, int]:
    """Step 4 — every internal URL on every HTML page resolves.

    Frozen-archive HTML is skipped *except* for two cases:
      - the current edition's per-edition index.html
      - any link whose URL points to a release artefact
        (.zip / .tar.gz / .sig / .sha256)

    The artefact carve-out enforces brief item #5: fail the build if
    HTML links to missing release artefacts. Frozen prior-edition
    HTML may otherwise reference versioned assets that have been
    pruned from /public/ head — those non-artefact links are allowed
    to dangle.

    Returns (fails, html_page_count, link_count).
    """
    fails: list[str] = []
    page_count = 0
    link_count = 0
    current_edition_prefix = f"integrity/releases/{current_edition}/" if current_edition else None
    for rel, _ in files:
        if not rel.lower().endswith(".html"):
            continue
        # frozen-archive html may legitimately link to versioned assets
        # that no longer exist in /public/ head; their bytes are sealed.
        is_frozen_archive = rel.startswith("integrity/releases/") and not rel.endswith(
            "integrity/releases/index.html"
        )
        # carve-out: the current edition's own index.html must be
        # checked fully — it ships THIS build and any broken link is
        # a real bug, not a sealed-bytes artefact.
        is_current_edition_index = bool(
            current_edition_prefix and rel == f"{current_edition_prefix}index.html"
        )
        skip_general_links = is_frozen_archive and not is_current_edition_index
        if skip_general_links and not is_frozen_archive:
            continue
        page_count += 1
        html = _read_public(repo, rel)
        urls = extract_urls(html)
        for u in sorted(urls):
            link_count += 1
            is_release_artefact = bool(_RELEASE_ARTEFACT_RE.search(u))
            # frozen-archive pages: only check release-artefact links.
            if skip_general_links and not is_release_artefact:
                continue
            # allow-rule check.
            ok_allow = allow.matches(u)
            if not ok_allow:
                fails.append(f"BROKEN-ALLOW: /{rel} → {u} (no allow rule)")
                continue
            # disk-presence check.
            disk_rel = url_to_disk_path(u)
            if not _public_is_file(repo, disk_rel):
                # the in-flight edition's release dir (SHA256SUMS, the archives and
                # their sigs) is built post-signature (build.sh stage 08); at the
                # pre-archive gate tolerate any not-yet-built file under THAT edition's
                # prefix only. index.html/TESTRESULTS already exist and still resolve.
                if (
                    pre_archive
                    and current_edition_prefix
                    and disk_rel.startswith(current_edition_prefix)
                ):
                    continue
                tag = "MISSING-ARTEFACT" if is_release_artefact else "BROKEN-LINK"
                fails.append(f"{tag}: /{rel} → {u} (no file at {disk_rel})")
    return fails, page_count, link_count


# ─── load / evaluate / render ───────────────────────────────────
def load(repo: Repo) -> tuple[dict | None, list[str]]:
    """read + schema-check the manifest. returns (manifest, errors); never
    prints or exits."""
    if not repo.is_file(MANIFEST_REL):
        return None, [f"manifest not found at {MANIFEST_REL}"]
    try:
        data = json.loads(repo.read(MANIFEST_REL))
    except json.JSONDecodeError as e:
        return None, [f"manifest is not valid JSON ({e})"]
    schema = data.get("schema")
    if schema != SCHEMA_TAG:
        return None, [f"manifest schema {schema!r} != expected {SCHEMA_TAG!r}"]
    return data, []


@dataclass
class Result:
    step_results: list[tuple[str, list[str]]] = field(default_factory=list)
    file_count: int = 0
    page_count: int = 0
    link_count: int = 0

    @property
    def total_fails(self) -> int:
        return sum(len(f) for _, f in self.step_results)

    @property
    def ok(self) -> bool:
        return self.total_fails == 0


def evaluate(repo: Repo, manifest: dict, pre_archive: bool) -> Result:
    allow = AllowRules(manifest)
    deny = DenyRules(manifest)
    deploy_excluded = compile_globs(manifest.get("deploy_excluded_globs", []))
    files = walk_public_files(repo, deploy_excluded)

    current_edition = manifest.get("edition") if isinstance(manifest, dict) else None
    if not (
        isinstance(current_edition, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", current_edition or "")
    ):
        current_edition = None

    result = Result(file_count=len(files))
    result.step_results.append(("file coverage", step_file_coverage(files, allow)))
    result.step_results.append(("deny coverage", step_deny_coverage(files, deny)))
    lc, pages, links = step_html_links(repo, files, allow, current_edition, pre_archive)
    result.step_results.append(("html links", lc))
    result.step_results.append(
        ("integrity artefacts", step_integrity_artefacts(repo, manifest, pre_archive))
    )
    result.page_count = pages
    result.link_count = links
    return result


# ─── main ───────────────────────────────────────────────────────
def main(repo_root: Path = REPO_ROOT, pre_archive: bool | None = None) -> int:
    repo = Repo(repo_root)
    # Pre-signature pass: build.sh builds the in-flight edition's release archives
    # only AFTER signing (stage 08), so at the pre-signature gate (stage 05) the
    # current edition's per-edition SHA256SUMS/.sig do not exist yet. gate.py exports
    # GATE_SKIP_SIGNATURE=1 for that pass. The post-signature gate and CI run without
    # it, so the archives are still fully required before anything ships.
    if pre_archive is None:
        pre_archive = os.environ.get("GATE_SKIP_SIGNATURE") == "1"

    manifest, errors = load(repo)
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1

    result = evaluate(repo, manifest, pre_archive)

    for label, fails in result.step_results:
        if fails:
            print(f"FAIL [{label}]: {len(fails)} issue(s)")
            for line in fails:
                print(f"  {line}")
        else:
            print(f"OK   [{label}]")

    if not result.ok:
        print(f"FAIL: {result.total_fails} public-exposure issue(s)")
        return 1

    print(
        f"OK: public exposure validated "
        f"({result.file_count} files, {result.page_count} HTML pages, "
        f"{result.link_count} links checked)"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
