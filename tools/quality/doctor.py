#!/usr/bin/env python3
"""tools/quality/doctor.py — environment diagnosis for the trentpower.fr repo.

A fresh clone or an extracted source archive can fail its checks for entirely
expected reasons: no `.git` metadata (archives carry none), the licensed Klim
fonts absent (the licence forbids redistribution; they are restored locally),
the Python / Hypothesis / node_modules toolchain not installed, or `gpg`
missing. Run standalone those surface as confusing stack traces. This module
inspects the local environment and reports — calmly, honestly — whether the
repo can run **full**, **partial**, **archive**-only, or is **blocked**.

It is diagnosis ONLY: it never runs the build/test/gate, never installs, never
downloads, never imports a key into a keyring, never re-hashes a font. The
ceremony (colour, panels) lives in tools/quality/doctor.sh; this file decides
what is true and, with --json, prints a machine-readable report the shell
renders. ADR-0002 shape — load()/evaluate()/main() with the work behind injected
seams (Repo, Proc, Env), so every scenario is testable with zero host
dependence (tools/quality/tests/test_doctor.py).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

_TOOLS = next(_a for _a in Path(__file__).resolve().parents if _a.name == "tools")
sys.path.insert(0, str(_TOOLS / "lib"))

from env import Env  # noqa: E402  (interpreter-environment evidence seam)
from paths import REPO_ROOT  # noqa: E402
from proc import Proc  # noqa: E402  (subprocess evidence seam)
from repo import Repo  # noqa: E402  (filesystem evidence seam)

# ── what "ready" means, named once ───────────────────────────────────────────

# Source of truth for the licensed binaries deliberately absent from the repo.
FONTS_MANIFEST = "metadata/repo-exclusions.json"
# Default restore command if the manifest can't name its own (kept in sync with
# the manifest's top-level "restore" field).
FONTS_RESTORE_FALLBACK = "python3 tools/build/fetch_licensed_fonts.py"

# Import NAMES (not pip distribution names) the gate + test suite need. pyyaml
# installs the `yaml` module, jsonschema installs `jsonschema`. The human-facing
# install command's source of truth stays .github/requirements/source-quality.txt.
REQUIRED_MODULES = ("jsonschema", "yaml")
HYPOTHESIS_MODULE = "hypothesis"
PY_DEPS_INSTALL = "pip install -r .github/requirements/source-quality.txt"

# The published signing key, present in the repo (not a keyring import).
PGP_KEY = "public/.well-known/pgp-key.asc"

# Root markers that identify THIS repo. If none are present we cannot trust any
# relative probe, so the verdict is `blocked` rather than a confident `archive`.
REPO_MARKERS = ("Makefile", "tools/lib/paths.py")

# Validators that read git history / metadata; named (not modified) as
# unavailable in archive mode so the operator knows what cannot be proven.
GIT_DEPENDENT_VALIDATORS = (
    "tools/quality/validate_public_readiness.py",
    "tools/build/detect_edition_changes.py",
    "tools/verify/scan_git_history.py",
)


# ── report shape ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Check:
    section: str
    name: str
    status: str  # present|ok|plausible | missing|partial|unavailable|sot-unavailable | n/a
    detail: str = ""
    next_action: str = ""


@dataclass
class DoctorReport:
    mode: str  # full | partial | archive | blocked
    checks: list[Check] = field(default_factory=list)
    full_checks_available: bool = False
    archive_checks_available: bool = False
    next_actions: list[str] = field(default_factory=list)
    recommended_next: str = ""


# ── load: the only place that parses the fonts manifest ──────────────────────


def load(repo: Repo) -> tuple[list[str], str, bool]:
    """Return (font_paths, restore_command, sot_ok). sot_ok is False when the
    manifest is absent or unparseable — the caller degrades to a warning rather
    than crashing on a malformed source of truth."""
    raw = repo.read(FONTS_MANIFEST)
    if not raw:
        return [], FONTS_RESTORE_FALLBACK, False
    try:
        data = json.loads(raw)
        files = [f["path"] for f in data["files"]]
    except (ValueError, KeyError, TypeError):
        return [], FONTS_RESTORE_FALLBACK, False
    restore = data.get("restore") or ""
    restore_cmd = f"python3 {restore}" if restore else FONTS_RESTORE_FALLBACK
    return files, restore_cmd, True


# ── evaluate: pure. no print, no exit, no side effects ───────────────────────


def evaluate(repo: Repo, proc: Proc, env: Env) -> DoctorReport:
    checks: list[Check] = []
    actions: list[str] = []

    # 1. Repository ----------------------------------------------------------
    git_bin = env.which("git")
    has_git_meta = repo.is_file(".git") or repo.is_dir(".git")  # worktree file OR dir
    inside_work_tree = bool(git_bin) and (
        # probe the tree being diagnosed, not the process cwd — a source archive
        # unpacked beside a real checkout must still read as "no work tree".
        proc.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo.root).returncode == 0
    )
    git_available = has_git_meta and inside_work_tree

    checks.append(
        Check(
            "Repository",
            "git binary",
            "present" if git_bin else "missing",
            git_bin or "not on PATH",
            "" if git_bin else "install git",
        )
    )
    checks.append(
        Check(
            "Repository",
            "git metadata",
            "present" if has_git_meta else "missing",
            ".git present" if has_git_meta else "no .git (source archive)",
        )
    )
    checks.append(
        Check(
            "Repository",
            "work tree",
            "ok" if inside_work_tree else "missing",
            "inside a git work tree" if inside_work_tree else "git cannot read this tree",
        )
    )

    # 2. Licensed assets -----------------------------------------------------
    font_paths, restore_cmd, sot_ok = load(repo)
    if not sot_ok:
        fonts_ok = False
        checks.append(
            Check(
                "Licensed assets",
                "font source of truth",
                "sot-unavailable",
                f"{FONTS_MANIFEST} missing or malformed",
                "restore the repo metadata; fonts cannot be verified",
            )
        )
    else:
        present = [p for p in font_paths if repo.is_file(p)]
        total = len(font_paths)
        n = len(present)
        if n == total:
            fstatus, fonts_ok = "present", True
            fdetail = f"{n}/{total} licensed fonts present"
        elif n == 0:
            fstatus, fonts_ok = "missing", False
            fdetail = f"0/{total} licensed fonts (expected on a fresh tree)"
        else:
            fstatus, fonts_ok = "partial", False
            fdetail = f"{n}/{total} licensed fonts present"
        checks.append(
            Check(
                "Licensed assets", "Klim fonts", fstatus, fdetail, "" if fonts_ok else restore_cmd
            )
        )
        if not fonts_ok:
            actions.append(restore_cmd)

    # 3. Python --------------------------------------------------------------
    checks.append(Check("Python", "interpreter", "ok", f"python {env.python_version()}"))
    libs_ok = True
    for mod in REQUIRED_MODULES:
        ok = env.has_module(mod)
        libs_ok = libs_ok and ok
        checks.append(
            Check(
                "Python",
                f"module: {mod}",
                "present" if ok else "missing",
                "importable" if ok else "not importable",
                "" if ok else PY_DEPS_INSTALL,
            )
        )
    hypothesis_ok = env.has_module(HYPOTHESIS_MODULE)
    checks.append(
        Check(
            "Python",
            "hypothesis",
            "present" if hypothesis_ok else "missing",
            "property tests available" if hypothesis_ok else "property tests cannot run",
            "" if hypothesis_ok else PY_DEPS_INSTALL,
        )
    )
    if not libs_ok or not hypothesis_ok:
        actions.append(PY_DEPS_INSTALL)

    # 4. Node ----------------------------------------------------------------
    node_bin = env.which("node")
    npm_bin = env.which("npm")
    node_modules = repo.is_dir("node_modules")
    node_ok = bool(node_bin) and bool(npm_bin) and node_modules
    checks.append(
        Check(
            "Node",
            "node binary",
            "present" if node_bin else "missing",
            node_bin or "not on PATH",
            "" if node_bin else "install node",
        )
    )
    checks.append(
        Check(
            "Node",
            "npm binary",
            "present" if npm_bin else "missing",
            npm_bin or "not on PATH",
            "" if npm_bin else "install npm",
        )
    )
    checks.append(
        Check(
            "Node",
            "node_modules",
            "present" if node_modules else "missing",
            "installed" if node_modules else "not installed",
            "" if node_modules else "npm install",
        )
    )
    if not node_modules:
        actions.append("npm install")

    # 5. Cryptography (GPG) — presence only, no keyring, no signature run ----
    gpg_bin = env.which("gpg")
    key_present = repo.is_file(PGP_KEY)
    gpg_ok = bool(gpg_bin) and key_present
    checks.append(
        Check(
            "Cryptography",
            "gpg binary",
            "present" if gpg_bin else "missing",
            gpg_bin or "not on PATH",
            "" if gpg_bin else "install gnupg",
        )
    )
    checks.append(
        Check(
            "Cryptography",
            "public key",
            "present" if key_present else "missing",
            PGP_KEY if key_present else f"{PGP_KEY} absent",
        )
    )
    checks.append(
        Check(
            "Cryptography",
            "signature verification",
            "plausible" if gpg_ok else "unavailable",
            "deep verify is `make verify`" if gpg_ok else "gpg or key missing",
        )
    )
    if not gpg_ok:
        actions.append("install gnupg (deep signature verification is `make verify`)")

    # 6. Capability — classify (blocked > archive > partial > full) ----------
    has_markers = all(repo.is_file(m) for m in REPO_MARKERS)
    all_present = git_available and fonts_ok and libs_ok and hypothesis_ok and node_ok and gpg_ok
    if not has_markers:
        mode = "blocked"
    elif not has_git_meta:
        mode = "archive"
    elif all_present:
        mode = "full"
    else:
        mode = "partial"

    if mode == "archive":
        checks.append(
            Check(
                "Repository",
                "git-dependent gates",
                "n/a",
                "unavailable in archive mode: " + ", ".join(GIT_DEPENDENT_VALIDATORS),
                "clone with git history to run these",
            )
        )
        actions.append(
            "git-dependent gates cannot run from a source archive "
            "(public-readiness, edition-change detection, history scan)"
        )

    recommended = _recommend(mode, fonts_ok, restore_cmd, libs_ok, hypothesis_ok)

    return DoctorReport(
        mode=mode,
        checks=checks,
        full_checks_available=(mode == "full"),
        archive_checks_available=libs_ok,  # archive-safe validators are Python + jsonschema/yaml
        next_actions=actions,
        recommended_next=recommended,
    )


def _recommend(mode, fonts_ok, restore_cmd, libs_ok, hypothesis_ok) -> str:
    """The single most useful next command, so the cockpit is actionable."""
    if mode == "blocked":
        return "run from inside a trentpower.fr checkout"
    if mode == "archive":
        return "make doctor inside a full git clone to run every gate"
    if mode == "full":
        return "make test"
    if not fonts_ok:
        return f"{restore_cmd}, then make gate"
    if not libs_ok or not hypothesis_ok:
        return f"{PY_DEPS_INSTALL}, then make test"
    return "make gate"


# ── main: build real seams, emit ─────────────────────────────────────────────


def main(
    argv: list[str] | None = None,
    *,
    repo: Repo | None = None,
    proc: Proc | None = None,
    env: Env | None = None,
) -> int:
    # seams are injectable so tests drive main() over fixtures with no real
    # repo / git / gpg / PATH (ADR-0002). Production passes none of them.
    ap = argparse.ArgumentParser(description="diagnose the local environment")
    ap.add_argument("--json", action="store_true", help="emit the machine-readable report")
    args = ap.parse_args(argv)

    report = evaluate(repo or Repo(REPO_ROOT), proc or Proc(), env or Env())

    if args.json:
        print(json.dumps(dataclasses.asdict(report), indent=2))
    else:
        # minimal plain fallback so `python3 doctor.py` alone still says something.
        print(f"mode: {report.mode}")
        for c in report.checks:
            print(f"  [{c.status:>15}]  {c.section} · {c.name}  {c.detail}")
        print(f"recommended next: {report.recommended_next}")

    return 1 if report.mode == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
