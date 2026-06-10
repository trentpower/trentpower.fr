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

Run standalone:
    python3 tools/quality/validate_public_readiness.py
    python3 tools/quality/validate_public_readiness.py --full
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

_TOOLS = next(_a for _a in Path(__file__).resolve().parents if _a.name == "tools")
sys.path.insert(0, str(_TOOLS / "lib"))
sys.path.insert(0, str(_TOOLS / "quality"))

from paths import REPO_ROOT  # noqa: E402
from validate_repository_hygiene import FORBIDDEN_NAMES  # noqa: E402

CONFIG = _TOOLS / "config" / "public-release.json"
EXCLUSIONS = REPO_ROOT / "metadata" / "repo-exclusions.json"
SCAN_REPORT = REPO_ROOT / "reports" / "checks" / "last-secret-scan.json"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True).stdout


def main() -> int:
    ap = argparse.ArgumentParser(description="public-repo posture gate")
    ap.add_argument(
        "--full",
        action="store_true",
        help="also require a fresh, clean full-history secret scan (release ceremony)",
    )
    args = ap.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    fails: list[str] = []

    # required root files, present and non-empty, with the load-bearing phrases.
    for name in cfg["required_root_files"]:
        p = REPO_ROOT / name
        if not p.is_file() or p.stat().st_size == 0:
            fails.append(f"required root file missing or empty: {name}")
    licence = REPO_ROOT / "LICENSE"
    if licence.is_file() and "MIT License" not in licence.read_text(encoding="utf-8"):
        fails.append("LICENSE does not contain the MIT License text")
    content_licence = REPO_ROOT / "CONTENT-RIGHTS.md"
    if content_licence.is_file() and "CC BY-SA 4.0" not in content_licence.read_text(
        encoding="utf-8"
    ):
        fails.append("CONTENT-RIGHTS.md does not name CC BY-SA 4.0")

    # README: no private-repo claim, and it must point at both licences.
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for phrase in cfg["forbidden_readme_phrases"]:
        if phrase in readme:
            fails.append(f"README.md still claims: {phrase!r}")
    for ref in ("LICENSE", "CONTENT-RIGHTS.md"):
        if ref not in readme:
            fails.append(f"README.md does not reference {ref}")

    # .gitattributes must keep public/ marked generated.
    attrs = REPO_ROOT / ".gitattributes"
    if attrs.is_file() and "public/** linguist-generated" not in attrs.read_text(encoding="utf-8"):
        fails.append(".gitattributes lost the public/** linguist-generated marker")

    # nothing forbidden tracked: dependency trees, secret-named files.
    if _git("ls-files", "node_modules").strip():
        fails.append("node_modules is tracked")
    tracked = _git("ls-files", "-z").split("\0")
    for rel in tracked:
        if rel and Path(rel).name.lower() in FORBIDDEN_NAMES:
            fails.append(f"forbidden filename tracked: {rel}")

    # font policy: untracked in git, declared in the exclusion manifest,
    # present on disk so the local build stays honest.
    if cfg["font_policy"] == "untracked":
        tracked_fonts = _git("ls-files", "--", *cfg["untracked_font_globs"]).strip()
        if tracked_fonts:
            fails.append(f"licensed font binaries are tracked: {tracked_fonts.splitlines()[:3]}")
        declared = {e["path"] for e in json.loads(EXCLUSIONS.read_text(encoding="utf-8"))["files"]}
        on_disk = set()
        for glob in cfg["untracked_font_globs"]:
            base, _, pattern = glob.rpartition("/")
            on_disk.update(
                p.relative_to(REPO_ROOT).as_posix() for p in (REPO_ROOT / base).glob(pattern)
            )
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
    if args.full:
        if not SCAN_REPORT.is_file():
            fails.append("no secret-scan report — run tools/quality/secret_scan.py")
        else:
            scan = json.loads(SCAN_REPORT.read_text(encoding="utf-8"))
            if scan.get("status") != "passed":
                fails.append(f"secret scan status is {scan.get('status')!r}, not passed")
            head = _git("rev-parse", "HEAD").strip()
            scanned = scan.get("scanned_commit", "")
            if scanned != head:
                ancestor = subprocess.run(
                    ["git", "merge-base", "--is-ancestor", scanned, head],
                    cwd=REPO_ROOT,
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

    if fails:
        print(f"FAIL: {len(fails)} public-readiness violation(s):")
        for f in fails:
            print(f"  ✗ {f}")
        return 1
    mode = "full" if args.full else "routine"
    print(f"OK: public-repo posture holds ({mode} mode)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
