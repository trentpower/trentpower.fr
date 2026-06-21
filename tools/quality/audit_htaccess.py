#!/usr/bin/env python3
"""audit_htaccess.py — focused audit of public/.htaccess and CSP freshness.

Complements the existing validators by reporting things they don't:
  - BEGIN/END marker pairs are present and balanced
  - the generated regions match what generate_htaccess.py would emit
  - CSP inline-script hashes still match the inline scripts on disk
  - release artefact completeness summary (per-edition)
  - a single "audit numbers" line for the build report

Exit 0 = green; non-zero on any drift.

Shape (deep module, small interface). The external interface is `main() -> int`
plus the audit-numbers + OK/FAIL text contract. The filesystem is the injected
`Repo(root)` seam, so the whole gate runs through `evaluate(repo) -> Result`
over a fixture repo with no monkeypatching. Compute (`evaluate`) is separate
from render (`main`): the former returns a Result and never prints or exits; the
latter is the only side-effecting adapter. The audit summary numbers ride on the
Result so main() renders them without re-walking the tree.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sys
import textwrap
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
# generate_htaccess lives under the build pillar.
sys.path.insert(
    0,
    str(
        next(
            _a
            for _a in __import__("pathlib").Path(__file__).resolve().parents
            if _a.name == "tools"
        )
        / "build"
    ),
)
import htaccess_config as cfg  # noqa: E402
from generate_htaccess import (  # noqa: E402
    CSP_BEGIN,
    CSP_END,
    EXPOSURE_BEGIN,
    EXPOSURE_END,
    _render_csp_block,
    _render_exposure_block,
)
from hashing import sri_sha256  # noqa: E402
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)
from script_blocks import iter_script_blocks  # noqa: E402

# repo-relative locations of the inputs (resolved through the Repo seam).
HTACCESS_REL = "public/.htaccess"
MANIFEST_REL = "tools/config/public-exposure.json"


def _read_htaccess(repo: Repo) -> str | None:
    """text of public/.htaccess, or None if it is missing."""
    if not repo.is_file(HTACCESS_REL):
        return None
    return repo.read(HTACCESS_REL)


def _check_markers(text: str) -> list[str]:
    issues: list[str] = []
    for begin, end in [
        ("# BEGIN PUBLIC EXPOSURE", "# END PUBLIC EXPOSURE"),
        ("# BEGIN CSP", "# END CSP"),
    ]:
        if text.count(begin) != 1 or text.count(end) != 1:
            issues.append(f"marker pair imbalanced: {begin} / {end}")
            continue
        if text.find(begin) > text.find(end):
            issues.append(f"end marker precedes begin: {begin} / {end}")
    return issues


def _extract_marker_body(text: str, begin: str, end: str) -> str | None:
    """Return the bytes between the BEGIN/END marker lines, exclusive."""
    m = re.search(
        r"^[^\S\n]*" + re.escape(begin) + r".*?\n(.*?)^[^\S\n]*" + re.escape(end),
        text,
        re.DOTALL | re.MULTILINE,
    )
    return m.group(1) if m else None


def _normalize(body: str) -> str:
    """Dedent + strip trailing whitespace per line; one trailing newline tolerated."""
    dedented = textwrap.dedent(body)
    lines = [ln.rstrip() for ln in dedented.splitlines()]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _check_generated_freshness(text: str) -> list[str]:
    """Byte-compare the contents inside each marker pair against what the
    renderers would emit right now. Catches stray hand-edits that left
    no obvious trace (an extra RewriteRule inserted inside the gate, a
    flipped CSP directive order, etc.)."""
    issues: list[str] = []
    for label, begin, end, renderer in [
        ("PUBLIC EXPOSURE", EXPOSURE_BEGIN, EXPOSURE_END, _render_exposure_block),
        ("CSP", CSP_BEGIN, CSP_END, _render_csp_block),
    ]:
        disk = _extract_marker_body(text, begin, end)
        if disk is None:
            issues.append(f"{label} markers not found")
            continue
        disk_norm = _normalize(disk)
        expected_norm = _normalize(renderer())
        if disk_norm == expected_norm:
            continue
        diff = list(
            difflib.unified_diff(
                expected_norm.splitlines(),
                disk_norm.splitlines(),
                fromfile=f"{label} (expected)",
                tofile=f"{label} (on disk)",
                lineterm="",
            )
        )
        snippet = "\n    ".join(diff[:30])
        more = "" if len(diff) <= 30 else f"\n    ... ({len(diff) - 30} more diff lines)"
        issues.append(f"{label} marker body drift:\n    {snippet}{more}")
    return issues


# Inline-script hash freshness. we re-compute hashes from the HTML on
# disk and compare against the static list in htaccess_config.py.
# a miss means a template changed but the config wasn't updated.
#
# CSP only governs *executable* inline scripts: a <script> with no
# type, or with a JavaScript MIME type. data blocks (application/json,
# application/ld+json, importmap, speculationrules, ...) carry a type
# the browser does not execute, and therefore do not need a hash.
# ScriptBlock.is_executable() encodes exactly that rule.
# pages that ship inline scripts we own. add a path here when adding
# a new bootstrapped page.
_INLINE_SCRIPT_PAGES = [
    "index.html",
    "privacy/index.html",
    "security/index.html",
    "security/acknowledgments/index.html",
    "integrity/index.html",
    "integrity/releases/index.html",
    "integrity/verify-locally/index.html",
    "verify/index.html",
    "403.html",
    "404.html",
    "500.html",
    "maintenance.html",
    "sw-reset/index.html",
    "source/index.html",
    "source/view/index.html",
]


def _check_csp_hash_freshness(repo: Repo) -> tuple[list[str], int]:
    """Hash every inline <script> body in the listed pages; confirm
    each hash appears in CSP_INLINE_HASHES_GLOBAL ∪ ..._SOURCE_VIEW_DELTA."""
    declared = {h for h, _ in cfg.CSP_INLINE_HASHES_GLOBAL}
    declared |= {h for h, _ in cfg.CSP_INLINE_HASHES_SOURCE_VIEW_DELTA}
    issues: list[str] = []
    hashed = 0
    for rel in _INLINE_SCRIPT_PAGES:
        prel = f"public/{rel}"
        if not repo.is_file(prel):
            continue
        html = repo.read(prel)
        for blk in iter_script_blocks(html):
            if not blk.is_executable():
                continue  # external script or data block — CSP hash irrelevant.
            body = blk.body
            if not body.strip():
                continue
            h = sri_sha256(body.encode("utf-8"))
            hashed += 1
            if h not in declared:
                issues.append(f"inline script in /{rel} hashes to {h} — not in htaccess_config.py")
    return issues, hashed


def _release_completeness(repo: Repo) -> tuple[list[str], int]:
    """Per-edition snapshot: count signed artefacts under each release dir.

    The brief's "release artefact completeness" line — a quick summary
    for the build report; full coverage is enforced by
    validate_public_exposure.py.

    The legacy 2026-02 release shipped its own integrity.json + assets/
    tree instead of SHA256SUMS; that shape is grandfathered.
    """
    issues: list[str] = []
    releases_prefix = "public/integrity/releases"
    # discover edition subdirectories by their index.html / artefacts on disk.
    members = repo.glob(f"{releases_prefix}/**/*")
    if not members:
        return issues, 0
    # Pre-signature gate (build.sh stage 05): the in-flight edition's archives
    # are built post-signature (stage 08), so defer that edition's SHA256SUMS/.sig
    # here. The post-signature gate and CI run without the flag and require them.
    pre_archive = os.environ.get("GATE_SKIP_SIGNATURE") == "1"
    current_edition = ""
    if pre_archive:
        try:
            current_edition = json.loads(repo.read("public/integrity.json")).get("edition", "")
        except (OSError, ValueError):
            current_edition = ""
    # collect immediate child directory names under releases/ (the edition dirs).
    prefix = f"{releases_prefix}/"
    edition_names: set[str] = set()
    for rel in members:
        tail = rel[len(prefix) :]
        first = tail.split("/", 1)[0]
        if first:
            edition_names.add(first)
    edition_count = 0
    for name in sorted(edition_names):
        if not re.match(r"^\d{4}-\d{2}(-\d{2})?$", name):
            continue
        edition_count += 1
        if name == "2026-02":
            # legacy shape: integrity.json + assets/ instead of SHA256SUMS.
            for required in ("integrity.json", "integrity.json.sig", "index.html"):
                if not repo.is_file(f"{prefix}{name}/{required}"):
                    issues.append(f"edition {name} missing {required}")
            continue
        if pre_archive and name == current_edition:
            # in-flight edition: index.html exists now; archives come post-signature.
            required_set = ("index.html",)
        else:
            required_set = ("SHA256SUMS", "SHA256SUMS.sig", "index.html")
        for required in required_set:
            if not repo.is_file(f"{prefix}{name}/{required}"):
                issues.append(f"edition {name} missing {required}")
    return issues, edition_count


def _candidate_urls_for_dead_rule_scan(repo: Repo) -> list[str]:
    """Build the URL set a mod_rewrite rule could plausibly match.

    Per-directory .htaccess strips the leading slash before matching;
    return relative posix paths with no leading slash. Also fold in
    directory routes (both `foo/` and `foo` forms) so allow patterns
    ending in `(/|$)?` can match the directory shape.
    """
    urls: list[str] = []
    dirs: set[str] = set()
    prefix = "public/"
    for repo_rel in repo.glob("public/**/*"):
        rel = repo_rel[len(prefix) :]
        if rel == ".htaccess":
            continue
        urls.append(rel)
        # also register every ancestor directory, in both `foo/` and
        # `foo` shapes, so allow patterns like `integrity/releases/
        # YYYY-MM-DD/?$` can match the directory form mod_dir resolves.
        parts = rel.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            d = "/".join(parts[:i])
            dirs.add(d)
            dirs.add(d + "/")
    urls.extend(sorted(dirs))
    if repo.is_file(MANIFEST_REL):
        data = json.loads(repo.read(MANIFEST_REL))
        for route in data.get("public_routes", []):
            r = route.lstrip("/")
            if not r:
                urls.append("")  # root /
                continue
            urls.append(r)  # "privacy/"
            urls.append(r.rstrip("/"))  # "privacy"
    return urls


def _check_dead_allow_rules(repo: Repo) -> tuple[list[str], int]:
    """Each allow pattern that matches zero candidate URLs is reported
    unless declared in ALLOW_RULE_FORWARD_LOOK."""
    issues: list[str] = []
    excused = 0
    candidates = _candidate_urls_for_dead_rule_scan(repo)
    forward_look = getattr(cfg, "ALLOW_RULE_FORWARD_LOOK", {})
    for heading, rules in cfg.ALLOW_RULE_FAMILIES:
        for pat in rules:
            try:
                compiled = re.compile(pat)
            except re.error as e:
                issues.append(f"family {heading!r}: invalid regex {pat!r} ({e})")
                continue
            if any(compiled.search(u) for u in candidates):
                continue
            if pat in forward_look:
                excused += 1
                continue
            issues.append(f"family {heading!r}: allow rule {pat!r} matches no file on disk")
    return issues, excused


def _count_lines(text: str) -> int:
    return text.count("\n") + (0 if text.endswith("\n") else 1)


# ---------------------------------------------------------------------------
# Result — the value that flows through the interface. evaluate() produces it;
# main() renders it. tests assert on Result, never on stdout. the audit summary
# numbers ride alongside the issue list so the render half does not re-walk.
# ---------------------------------------------------------------------------
@dataclass
class Result:
    issues: list[tuple[str, str]] = field(default_factory=list)
    n_allow_rules: int = 0
    n_allow_families: int = 0
    n_deny_rules: int = 0
    n_hashed: int = 0
    n_editions: int = 0
    n_excused: int = 0
    n_lines: int = 0
    htaccess_missing: bool = False

    @property
    def ok(self) -> bool:
        return not self.issues and not self.htaccess_missing

    @property
    def fails(self) -> list[str]:
        """rendered failure lines, one per issue (for assertion ergonomics)."""
        return [f"[{label}] {msg}" for label, msg in self.issues]


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo. this is the test surface.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo) -> Result:
    text = _read_htaccess(repo)
    if text is None:
        return Result(htaccess_missing=True)

    issues_markers = _check_markers(text)
    issues_freshness = _check_generated_freshness(text)
    issues_hashes, n_hashed = _check_csp_hash_freshness(repo)
    issues_releases, n_editions = _release_completeness(repo)
    issues_dead, n_excused = _check_dead_allow_rules(repo)

    all_issues = (
        [("markers", i) for i in issues_markers]
        + [("csp", i) for i in issues_freshness]
        + [("csp-hash", i) for i in issues_hashes]
        + [("release", i) for i in issues_releases]
        + [("dead-rule", i) for i in issues_dead]
    )

    n_allow_families = len(cfg.ALLOW_RULE_FAMILIES)
    n_allow_rules = sum(len(rules) for _, rules in cfg.ALLOW_RULE_FAMILIES)
    n_deny_rules = (
        len(cfg.DENY_PATH_RULES) + len(cfg.DENY_EXTENSION_RULES) + len(cfg.DENY_DIRECTORY_RULES)
    )

    return Result(
        issues=all_issues,
        n_allow_rules=n_allow_rules,
        n_allow_families=n_allow_families,
        n_deny_rules=n_deny_rules,
        n_hashed=n_hashed,
        n_editions=n_editions,
        n_excused=n_excused,
        n_lines=_count_lines(text),
    )


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. evaluates, renders, returns exit code.
# the only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(repo)

    if r.htaccess_missing:
        print(f"FAIL: {repo_root / HTACCESS_REL} not found", file=sys.stderr)
        return 1

    print(
        "  htaccess audit: "
        f"{r.n_allow_rules} allow rules in {r.n_allow_families} families, "
        f"{r.n_deny_rules} deny rules, "
        f"{r.n_hashed} inline scripts hashed, "
        f"{r.n_editions} release editions, "
        f"{r.n_excused} forward-look excused, "
        f"{r.n_lines} lines"
    )

    if r.issues:
        print(f"FAIL: {len(r.issues)} htaccess audit issue(s):")
        for label, msg in r.issues:
            print(f"  [{label}] {msg}")
        return 1

    print("OK: .htaccess + CSP audit clean")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
