#!/usr/bin/env python3
"""tools/quality/secret_scan.py — full-history secret scan for the public repository.

Scans every committed blob on every ref for secret material before the
repository is pushed to a public remote. Two engines:

  gitleaks      preferred; downloaded release binary (linux arm64) verified
                against the published checksum file. Scans the full commit
                history (--log-opts=--all).
  fallback      tools/verify/scan_git_history.py --strict (the repo's own
                pattern-based history sweep) plus a pattern pass over the
                tracked working tree. Used only when gitleaks is unavailable;
                the report records which engine ran so a fallback run is
                never mistaken for a full gitleaks scan.

Either way a tracked-working-tree content pass always runs, reusing the
SECRET_PATTERNS from validate_repository_hygiene.py — one source of truth
for what counts as secret-shaped.

The report lands at reports/checks/last-public-readiness sibling
reports/checks/last-secret-scan.json (gitignored, local-only) in the
check_report envelope head shape.

Run standalone:
    python3 tools/quality/secret_scan.py             # scan, report, exit 0/1
    python3 tools/quality/secret_scan.py --install   # fetch gitleaks first
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

_TOOLS = next(_a for _a in Path(__file__).resolve().parents if _a.name == "tools")
sys.path.insert(0, str(_TOOLS / "lib"))
sys.path.insert(0, str(_TOOLS / "quality"))

from check_report import SCHEMA_VERSION, atomic_write_json, utc_now_iso  # noqa: E402
from paths import REPO_ROOT  # noqa: E402
from proc import Proc  # noqa: E402  (shared subprocess evidence seam)
from validate_repository_hygiene import (  # noqa: E402
    SECRET_PATTERNS,
    TEXT_SUFFIXES,
)

GITLEAKS_VERSION = "8.21.2"
GITLEAKS_URL = (
    "https://github.com/gitleaks/gitleaks/releases/download/"
    f"v{GITLEAKS_VERSION}/gitleaks_{GITLEAKS_VERSION}_linux_arm64.tar.gz"
)
GITLEAKS_CHECKSUMS_URL = (
    "https://github.com/gitleaks/gitleaks/releases/download/"
    f"v{GITLEAKS_VERSION}/gitleaks_{GITLEAKS_VERSION}_checksums.txt"
)
LOCAL_BIN = Path.home() / ".local" / "bin"
REPORT_PATH = REPO_ROOT / "reports" / "checks" / "last-secret-scan.json"

# filenames that should never appear anywhere in history, tracked or not.
# pgp-key.asc is the published *public* key and is exempt by basename below.
HISTORY_EXEMPT_BASENAMES = {"pgp-key.asc", "pgp-key.asc.txt"}


def _git(proc: Proc, *args: str) -> str:
    return proc.run(["git", *args], cwd=REPO_ROOT).stdout


def find_gitleaks() -> Path | None:
    found = shutil.which("gitleaks")
    if found:
        return Path(found)
    local = LOCAL_BIN / "gitleaks"
    if local.is_file():
        return local
    return None


def install_gitleaks() -> Path | None:  # pragma: no cover - network + binary download
    """Download the gitleaks release tarball, verify its sha256, install to ~/.local/bin."""
    import hashlib

    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(GITLEAKS_CHECKSUMS_URL, timeout=60) as r:
            sums = r.read().decode()
        expected = None
        for line in sums.splitlines():
            if line.strip().endswith(f"gitleaks_{GITLEAKS_VERSION}_linux_arm64.tar.gz"):
                expected = line.split()[0]
                break
        if not expected:
            print("secret-scan: checksum entry not found in release checksums file")
            return None
        with tempfile.TemporaryDirectory() as td:
            tarball = Path(td) / "gitleaks.tar.gz"
            with urllib.request.urlopen(GITLEAKS_URL, timeout=300) as r, open(tarball, "wb") as fh:
                shutil.copyfileobj(r, fh)
            digest = hashlib.sha256(tarball.read_bytes()).hexdigest()
            if digest != expected:
                print(f"secret-scan: checksum mismatch for gitleaks download ({digest})")
                return None
            with tarfile.open(tarball) as tf:
                member = tf.getmember("gitleaks")
                tf.extract(member, td)
            target = LOCAL_BIN / "gitleaks"
            shutil.move(str(Path(td) / "gitleaks"), target)
            target.chmod(0o755)
            return target
    except Exception as exc:  # network failure, GitHub outage, etc.
        print(f"secret-scan: gitleaks install failed: {exc}")
        return None


def run_gitleaks(proc: Proc, binary: Path) -> tuple[list[dict], str]:
    """Full-history scan over every ref. Returns (findings, version)."""
    version = proc.run([str(binary), "version"]).stdout.strip()
    with tempfile.TemporaryDirectory() as td:
        report = Path(td) / "gitleaks.json"
        result = proc.run(
            [
                str(binary),
                "detect",
                "--source",
                str(REPO_ROOT),
                "--log-opts=--all",
                "--report-format",
                "json",
                "--report-path",
                str(report),
                "--no-banner",
            ],
        )
        # exit 0 = clean, 1 = leaks found; anything else is an engine error.
        if result.returncode not in (0, 1):
            raise RuntimeError(f"gitleaks failed: {result.stderr.strip()[:400]}")
        raw = json.loads(report.read_text()) if report.is_file() else []
    findings = [
        {
            "rule": f.get("RuleID"),
            "file": f.get("File"),
            "commit": (f.get("Commit") or "")[:12],
            "line": f.get("StartLine"),
            "description": f.get("Description"),
        }
        for f in raw
    ]
    return findings, version


def scan_tracked_tree(proc: Proc) -> list[dict]:
    """Content pass over tracked text files using the hygiene gate's patterns."""
    findings: list[dict] = []
    tracked = _git(proc, "ls-files", "-z").split("\0")
    for rel in tracked:
        if not rel:
            continue
        p = REPO_ROOT / rel
        if p.suffix.lower() not in TEXT_SUFFIXES or not p.is_file():
            continue
        if p.name in HISTORY_EXEMPT_BASENAMES:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for pat, label in SECRET_PATTERNS:
                if pat.search(line):
                    findings.append(
                        {
                            "rule": label,
                            "file": rel,
                            "commit": "worktree",
                            "line": lineno,
                            "description": line.strip()[:80],
                        }
                    )
    return findings


def scan_history_fallback(proc: Proc) -> list[dict]:
    """Delegate the history sweep to the repo's own scanner (strict mode)."""
    result = proc.run(
        [sys.executable, str(_TOOLS / "verify" / "scan_git_history.py"), "--strict"],
        cwd=REPO_ROOT,
    )
    if result.returncode == 0:
        return []
    lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    return [
        {
            "rule": "scan_git_history finding",
            "file": ln[:160],
            "commit": "history",
            "line": None,
            "description": "see tools/verify/scan_git_history.py output",
        }
        for ln in lines[-40:]
    ]


def main(proc: Proc | None = None) -> int:
    ap = argparse.ArgumentParser(description="full-history secret scan")
    ap.add_argument("--install", action="store_true", help="download gitleaks if missing")
    ap.add_argument("--json", type=Path, default=REPORT_PATH, help="report output path")
    args = ap.parse_args()

    if proc is None:
        proc = Proc()

    binary = find_gitleaks()
    if binary is None and args.install:  # pragma: no cover - network install path
        print("secret-scan: installing gitleaks…")
        binary = install_gitleaks()

    findings: list[dict] = []
    if binary is not None:
        print(f"secret-scan: engine gitleaks at {binary}")
        gl_findings, version = run_gitleaks(proc, binary)
        engine = f"gitleaks {version or GITLEAKS_VERSION}"
        findings.extend(gl_findings)
    else:
        print("secret-scan: gitleaks unavailable — falling back to scan_git_history.py")
        engine = "scan_git_history-fallback"
        findings.extend(scan_history_fallback(proc))

    tree_findings = scan_tracked_tree(proc)
    findings.extend(tree_findings)

    head = _git(proc, "rev-parse", "HEAD").strip()
    refs = len(_git(proc, "for-each-ref", "--format=%(refname)").splitlines())
    status = "failed" if findings else "passed"
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "command": "secret_scan.py",
        "status": status,
        "summary": {"passed": 0 if findings else 1, "failed": len(findings), "warnings": 0},
        "engine": engine,
        "scanned_commit": head,
        "refs_scanned": refs,
        "findings": findings,
    }
    atomic_write_json(report, args.json)
    print(f"secret-scan: engine={engine} refs={refs} findings={len(findings)}")
    print(f"secret-scan: report → {args.json}")
    if findings:
        print(f"FAIL: {len(findings)} potential secret(s) found:")
        for f in findings[:25]:
            print(f"  ✗ [{f['rule']}] {f['file']} @ {f['commit']}")
        if len(findings) > 25:
            print(f"  … and {len(findings) - 25} more (see report)")
        return 1
    print("OK: no secrets found across all refs and the tracked tree")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
