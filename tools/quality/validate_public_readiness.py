#!/usr/bin/env python3
"""tools/quality/validate_public_readiness.py — public-repo posture gate.

Unlike its siblings, which govern the public web bytes under public/, this
validator deliberately scopes to the REPOSITORY ROOT: the repo itself is a
public artefact (source + deployment source on GitHub), and its posture has
its own invariants:

  - the licence and community files exist and say what they must
  - README carries no private-repo claim
  - no dependency trees, secret-named files, or licensed binaries are tracked
  - the font exclusions on disk, in git, and in metadata/repo-exclusions.json
    agree with the declared policy
  - the internal process records stay untracked

Declared facts live in tools/config/public-release.json.

With --full (the release ceremony, not the routine gate) it additionally
requires a fresh, clean full-history secret scan report from
tools/quality/secret_scan.py. The report is local-only and gitignored, so the
routine gate — which must pass on a fresh CI checkout — never asks for it.

Shape (deep module, small interface). Two dependencies are injected seams —
`Repo(root)` for the filesystem and `Proc()` for the git crossings (what is
tracked, the HEAD hash, the merge-base ancestor check) — so the whole gate is
exercised through `evaluate(repo, proc, full=...) -> Result` over a fixture
repo with a FakeProc, no monkeypatching. Compute (`evaluate`) is separate from
render (`main`): the former returns a Result and never prints or exits; the
latter is the only side-effecting adapter.

Run standalone:
    python3 tools/quality/validate_public_readiness.py
    python3 tools/quality/validate_public_readiness.py --full
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_TOOLS = next(_a for _a in Path(__file__).resolve().parents if _a.name == "tools")
sys.path.insert(0, str(_TOOLS / "lib"))
sys.path.insert(0, str(_TOOLS / "quality"))

from paths import REPO_ROOT  # noqa: E402
from proc import Proc  # noqa: E402  (shared subprocess evidence seam)
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)
from validate_repository_hygiene import FORBIDDEN_NAMES  # noqa: E402

# repo-relative locations of the inputs (resolved through the Repo seam).
CONFIG_REL = "tools/config/public-release.json"
EXCLUSIONS_REL = "metadata/repo-exclusions.json"
SCAN_REPORT_REL = "reports/checks/last-secret-scan.json"

# deployment-metadata leak signatures. the host + sftp account must never be
# committed (they live in env / the GitHub production secrets); the concrete
# lftp recipe is rendered locally from a template and gitignored. the env-
# placeholder forms (${VAR}, $VAR) and the secret KEY names in the workflow are
# fine — only literal values trip these.
_DEPLOY_PATTERNS = (
    ("lftp open directive (host+user)", re.compile(r"\bopen\s+-u\b")),
    ("literal sftp host", re.compile(r"sftp://[A-Za-z0-9]")),
    ("Gandi gpaas host", re.compile(r"gpaas\.net")),
    (
        "SFTP_* assigned a literal value",
        re.compile(r"\bSFTP_(?:USERNAME|USER|HOST|REMOTE_PATH|PASSWORD)\s*=\s*[^\s$#'\"]"),
    ),
)
# files that legitimately carry the patterns: the template (placeholders only),
# the CI workflow (names secret keys, not values), this gate + its test (the
# pattern list), and the secret-scan config (the matching rule).
_DEPLOY_SCAN_ALLOWLIST = frozenset(
    {
        "tools/release/deploy.sftp.lftp.template",
        "tools/release/render_deploy_lftp.py",
        ".github/workflows/deploy.yml",
        "tools/quality/validate_public_readiness.py",
        "tools/quality/tests/test_public_readiness.py",
        ".gitleaks.toml",
    }
)
_DEPLOY_SCAN_SUFFIXES = (
    ".lftp", ".sh", ".yml", ".yaml", ".md", ".txt", ".py", ".json", ".cfg",
    ".ini", ".toml", ".example",
)


# ---------------------------------------------------------------------------
# Result — the value that flows through the interface. evaluate() produces it;
# main() renders it. tests assert on Result, never on stdout.
# ---------------------------------------------------------------------------
@dataclass
class Result:
    fails: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


# ---------------------------------------------------------------------------
# load — read the declared-facts config through the Repo seam.
# ---------------------------------------------------------------------------
def load(repo: Repo) -> dict:
    return json.loads(repo.read(CONFIG_REL))


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo + Proc. this is the test surface.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo, proc: Proc, full: bool = False) -> Result:
    cfg = load(repo)
    r = Result()
    fails = r.fails

    def _git(*args: str) -> str:
        return proc.run(["git", *args], cwd=repo.root).stdout

    # required root files, present and non-empty, with the load-bearing phrases.
    for name in cfg["required_root_files"]:
        if not repo.is_file(name) or repo.size(name) == 0:
            fails.append(f"required root file missing or empty: {name}")
    if repo.is_file("LICENSE") and "MIT License" not in repo.read("LICENSE"):
        fails.append("LICENSE does not contain the MIT License text")
    if repo.is_file("CONTENT-RIGHTS.md") and "CC BY-SA 4.0" not in repo.read("CONTENT-RIGHTS.md"):
        fails.append("CONTENT-RIGHTS.md does not name CC BY-SA 4.0")

    # README: no private-repo claim, and it must point at both licences.
    readme = repo.read("README.md")
    for phrase in cfg["forbidden_readme_phrases"]:
        if phrase in readme:
            fails.append(f"README.md still claims: {phrase!r}")
    for ref in ("LICENSE", "CONTENT-RIGHTS.md"):
        if ref not in readme:
            fails.append(f"README.md does not reference {ref}")

    # .gitattributes must keep public/ marked generated.
    if repo.is_file(".gitattributes") and "public/** linguist-generated" not in repo.read(
        ".gitattributes"
    ):
        fails.append(".gitattributes lost the public/** linguist-generated marker")

    # nothing forbidden tracked: dependency trees, secret-named files.
    if _git("ls-files", "node_modules").strip():
        fails.append("node_modules is tracked")
    tracked = _git("ls-files", "-z").split("\0")
    for rel in tracked:
        if rel and Path(rel).name.lower() in FORBIDDEN_NAMES:
            fails.append(f"forbidden filename tracked: {rel}")

    # no deployment metadata (sftp host / account / lftp recipe) in tracked
    # source. the live recipe is rendered from a template into a gitignored file;
    # a literal host or `open -u` directive committed here is an exposure (the
    # repo is public). scan tracked NON-public source only — published bytes have
    # their own leak gate.
    for rel in tracked:
        if (
            not rel
            or rel.startswith("public/")
            or rel in _DEPLOY_SCAN_ALLOWLIST
            or not rel.endswith(_DEPLOY_SCAN_SUFFIXES)
        ):
            continue
        try:
            text = repo.read(rel)
        except UnicodeDecodeError:
            continue
        for label, pat in _DEPLOY_PATTERNS:
            m = pat.search(text)
            if m:
                line = text.count("\n", 0, m.start()) + 1
                fails.append(f"deployment metadata in tracked source: {rel}:{line} ({label})")
                break

    # font policy: untracked in git, declared in the exclusion manifest,
    # present on disk so the local build stays honest.
    if cfg["font_policy"] == "untracked":
        tracked_fonts = _git("ls-files", "--", *cfg["untracked_font_globs"]).strip()
        if tracked_fonts:
            fails.append(f"licensed font binaries are tracked: {tracked_fonts.splitlines()[:3]}")
        declared = {e["path"] for e in json.loads(repo.read(EXCLUSIONS_REL))["files"]}
        on_disk = set()
        for glob in cfg["untracked_font_globs"]:
            on_disk.update(repo.glob(glob))
        for path in sorted(on_disk - declared):
            fails.append(f"font on disk but not declared in repo-exclusions.json: {path}")
        for path in sorted(declared - on_disk):
            fails.append(
                f"declared font missing on disk: {path} (run tools/build/fetch_licensed_fonts.py)"
            )

    # internal process records stay out of the tree.
    for rel in cfg["untracked_internal_records"]:
        if _git("ls-files", "--", rel).strip():
            fails.append(f"internal record is tracked: {rel}")

    # release ceremony only: a fresh, clean full-history secret scan.
    if full:
        if not repo.is_file(SCAN_REPORT_REL):
            fails.append("no secret-scan report — run tools/quality/secret_scan.py")
        else:
            scan = json.loads(repo.read(SCAN_REPORT_REL))
            if scan.get("status") != "passed":
                fails.append(f"secret scan status is {scan.get('status')!r}, not passed")
            head = _git("rev-parse", "HEAD").strip()
            scanned = scan.get("scanned_commit", "")
            if scanned != head:
                ancestor = proc.run(
                    ["git", "merge-base", "--is-ancestor", scanned, head],
                    cwd=repo.root,
                ).returncode
                if ancestor != 0:
                    fails.append("secret scan was run on an unrelated commit — rerun it")
            generated = scan.get("generated_at", "")
            try:
                age = datetime.datetime.now(datetime.UTC) - datetime.datetime.strptime(
                    generated, "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=datetime.UTC)
                if age.days > int(cfg["secret_scan_max_age_days"]):
                    fails.append(f"secret scan is {age.days} days old — rerun it")
            except ValueError:
                fails.append(f"secret scan report has no parseable timestamp: {generated!r}")

    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. builds the seams, evaluates, renders,
# returns exit code. the only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    ap = argparse.ArgumentParser(description="public-repo posture gate")
    ap.add_argument(
        "--full",
        action="store_true",
        help="also require a fresh, clean full-history secret scan (release ceremony)",
    )
    args = ap.parse_args()

    repo = Repo(repo_root)
    proc = Proc()
    r = evaluate(repo, proc, full=args.full)

    if r.fails:
        print(f"FAIL: {len(r.fails)} public-readiness violation(s):")
        for f in r.fails:
            print(f"  ✗ {f}")
        return 1
    mode = "full" if args.full else "routine"
    print(f"OK: public-repo posture holds ({mode} mode)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
