#!/usr/bin/env python3
"""validate_release.py — single-command release verification gate.

Wraps the deploy-blocking gate (tools/gate.py — security + correctness:
edition consistency, source-mirror byte-equality, gpg signature, integrity
manifest + signature freshness, verification-map dates, asset_version
coherence, service-worker precache, local-path leakage, hidden-artefact +
archive-content safety, frozen-archive immutability, public-exposure,
.htaccess allow-list, and more) and adds a small set of release-specific
checks the gate does not cover:

  R1. /.well-known/security.txt Expires must be more than 60 days
      from today (RFC 9116 §2.5.5; some clients warn earlier).
  R2. The redistributable archive manifest at
      /integrity/releases/<edition>/integrity-redistributable.json
      must list every file present inside the matching ZIP, with
      hashes that match the in-archive bytes.
  R3. The redistributable manifest's detached signature must verify
      against the published public key.

Exit 0 = green; exit 1 = block.

Shape (ADR-0002). The external interface is `main(repo_root) -> int` plus the
OK/FAIL text contract. The two dependencies are injected seams — `Repo(root)`
for the filesystem and `Proc()` for the subprocess crossings (the gate re-run
and the gpg verifications) — so the whole gate is exercised through
`evaluate(repo, proc) -> Result` over a fixture repo with no monkeypatching.
Compute (`evaluate`) is separate from render (`main`): the former returns a
Result and never prints or exits; the latter is the only side-effecting adapter.

Usage:
    python3 tools/verify/validate_release.py
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field

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
from hashing import sri_sha256  # noqa: E402
from paths import REPO_ROOT  # noqa: E402
from proc import Proc  # noqa: E402  (shared subprocess evidence seam)
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

# the deploy-blocking gate (security + correctness). advisory quality lint
# lives in tools/lint.py and is run non-blocking in CI, not here. resolved
# through the Repo seam so the path tracks repo.root.
GATE_REL = "tools/quality/gate.py"

# the published web root, relative to repo.root. the original module rooted
# everything at public/ (paths.PUBLIC_DIR); here the Repo seam is rooted at
# repo.root, so public-tree locations carry the "public/" prefix.
PUBLIC_REL = "public"

EXPIRES_WINDOW_DAYS = 60


# ---------------------------------------------------------------------------
# Result — what flows out of evaluate(). carries, per release step, the exact
# OK/FAIL lines the original printed so main() reproduces stdout verbatim, plus
# the gate's own return code and the fail-fast outcome. tests assert on Result,
# never on stdout.
# ---------------------------------------------------------------------------
@dataclass
class Result:
    # the gate.py subprocess return code.
    gate_rc: int = 0
    # the FAIL line emitted when gate.py is missing (else None).
    gate_missing_line: str | None = None
    # gate.py's captured stdout (the seam captures what used to stream inline).
    gate_stdout: str = ""
    # release steps actually reached, in order: (step_no, label, [lines], rc).
    steps: list[tuple[int, str, list[str], int]] = field(default_factory=list)
    fails: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


def _public_path(repo: Repo, prel: str) -> pathlib.Path:
    """real filesystem path under public/ — gpg, zip and directory walks need a
    path, not text. derived from the Repo seam's root."""
    return repo.root / PUBLIC_REL / prel


# ---------------------------------------------------------------------------
# release checks — each is pure: it returns (rc, lines), accumulating the
# OK/FAIL lines the original printed. no check prints or exits.
# ---------------------------------------------------------------------------
def run_predeploy(repo: Repo, proc: Proc) -> tuple[int, str, str | None]:
    """run the blocking gate.py via the Proc seam. returns (rc, gate_stdout,
    missing_line). the original printed the banner (3 lines) then ran gate.py
    with INHERITED stdout: against a pipe the parent's block-buffered prints
    flushed AFTER the child's, so the captured baseline shows gate output first,
    then the banner. the seam captures gate stdout, and main() re-emits it in
    exactly that order to preserve the contract."""
    gate = repo.root / GATE_REL
    if not gate.is_file():
        return 1, "", f"  FAIL: {gate} not found"
    r = proc.run([sys.executable, str(gate)])
    return r.returncode, r.stdout, None


def check_security_txt_expires(repo: Repo) -> tuple[int, list[str]]:
    """RFC 9116 §2.5.5 — Expires must be a future date. We require a
    60-day cushion so the certificate of currency does not lapse
    silently between releases."""
    sec_rel = ".well-known/security.txt"
    if not repo.is_file(f"{PUBLIC_REL}/{sec_rel}"):
        return 1, [f"  FAIL: {sec_rel} missing"]
    text = repo.read(f"{PUBLIC_REL}/{sec_rel}")
    m = re.search(r"^Expires:\s*(\S+)\s*$", text, re.MULTILINE)
    if not m:
        return 1, ["  FAIL: security.txt has no Expires: line"]
    raw = m.group(1)
    # accept either "2027-02-10T00:00:00.000Z" or "2027-02-10T00:00:00Z"
    try:
        # python 3.11+ understands trailing z directly; older needs munging.
        normalised = raw.replace("Z", "+00:00")
        # trim sub-second precision python's fromisoformat doesn't accept on <3.11.
        normalised = re.sub(r"\.\d+", "", normalised)
        expires = dt.datetime.fromisoformat(normalised)
    except ValueError:
        return 1, [f"  FAIL: security.txt Expires: '{raw}' is not parseable ISO 8601"]
    now = dt.datetime.now(dt.UTC)
    delta_days = (expires - now).days
    if delta_days < EXPIRES_WINDOW_DAYS:
        return 1, [
            f"  FAIL: security.txt Expires {raw} is only {delta_days} day(s)",
            f"        away (window is {EXPIRES_WINDOW_DAYS} days). Update",
            "        the Expires line and re-sign attribution.sig.",
        ]
    return 0, [f"  OK: security.txt Expires {raw} ({delta_days} days from now)"]


def _find_release_dir(repo: Repo) -> pathlib.Path | None:
    rel = repo.root / PUBLIC_REL / "integrity" / "releases"
    if not rel.is_dir():
        return None
    for child in sorted(rel.iterdir(), reverse=True):
        if child.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", child.name):
            return child
    return None


def _current_exclusion_manifest(rel_dir: pathlib.Path) -> pathlib.Path | None:
    """Return the exclusion manifest that describes the CURRENT live
    bytes: the newest build-dated rebuild (EXCLUDED_FILES-<date>.json)
    when across-day drift has occurred, else the canonical
    EXCLUDED_FILES.json. every variant is emitted with its own detached
    signature, so preferring the newest keeps the tamper cross-check
    intact while letting the canonical edition stay byte-stable."""
    dated = sorted(rel_dir.glob("EXCLUDED_FILES-????-??-??.json"), reverse=True)
    if dated:
        return dated[0]
    canonical = rel_dir / "EXCLUDED_FILES.json"
    return canonical if canonical.is_file() else None


def check_redistributable_manifest(repo: Repo) -> tuple[int, list[str]]:
    root = repo.root / PUBLIC_REL
    rel_dir = _find_release_dir(repo)
    if rel_dir is None:
        return 0, ["  OK: no date-precision release directory present — nothing to check"]
    manifest_path = rel_dir / "integrity-redistributable.json"
    if not manifest_path.is_file():
        return 1, [
            f"  FAIL: {manifest_path.relative_to(root)} missing — run build_release_archives.py"
        ]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return 1, [f"  FAIL: {manifest_path.name} invalid JSON ({e})"]
    declared = manifest.get("files", {})
    if not isinstance(declared, dict) or not declared:
        return 1, [f"  FAIL: {manifest_path.name} missing 'files' map"]

    # find the matching zip. when an across-day parallel rebuild has
    # shipped, the release directory contains BOTH the canonical
    # trentpower-fr-<edition>.zip and one or more dated
    # trentpower-fr-<build_date>.zip rebuilds. integrity-redistributable.json
    # is the CANONICAL manifest and describes the CANONICAL archive,
    # so pick that one explicitly. glob order is filesystem-dependent
    # and not safe.
    manifest_edition = manifest.get("edition", "")
    canonical_zip = rel_dir / f"trentpower-fr-{manifest_edition}.zip"
    if canonical_zip.is_file():
        zip_path = canonical_zip
    else:
        zip_candidates = sorted(rel_dir.glob("trentpower-fr-*.zip"))
        if not zip_candidates:
            return 1, [f"  FAIL: no trentpower-fr-*.zip in {rel_dir.relative_to(root)}"]
        zip_path = zip_candidates[0]

    fails: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        archive_paths = set(zf.namelist())
        # every declared path is in the zip and bytes hash matches.
        for path, expected in declared.items():
            if path not in archive_paths:
                fails.append(f"declared {path!r} not in {zip_path.name}")
                continue
            actual = sri_sha256(zf.read(path))
            if actual != expected:
                fails.append(
                    f"{path!r}: manifest says {expected[:24]}…, archive bytes hash {actual[:24]}…"
                )
        # every archive path is declared in the manifest.
        for path in archive_paths:
            if path not in declared:
                fails.append(f"archive contains {path!r} but manifest does not declare it")
    if fails:
        lines = [f"  FAIL: {len(fails)} redistributable-manifest issue(s):"]
        for f in fails[:12]:
            lines.append(f"    {f}")
        if len(fails) > 12:
            lines.append(f"    ... ({len(fails) - 12} more)")
        return 1, lines
    return 0, [f"  OK: {len(declared)} declared files match {zip_path.name} byte-for-byte"]


def _verify_with_keyring(
    proc: Proc, key: pathlib.Path, sig: pathlib.Path, target: pathlib.Path
) -> tuple[int, str]:
    """import the published key into a throwaway keyring and verify a detached
    signature through the Proc seam. returns (rc, stderr). the keyring env
    (os.environ.copy + GNUPGHOME=tmpdir, GPG_AGENT_INFO popped) is built here
    and passed as env=; the TemporaryDirectory is an ephemeral, self-cleaning
    side effect. rc -1 marks the import step failing."""
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env["GNUPGHOME"] = tmp
        env.pop("GPG_AGENT_INFO", None)
        imp = proc.run(
            ["gpg", "--batch", "--quiet", "--import", str(key)],
            env=env,
        )
        if imp.returncode != 0:
            return -1, imp.stderr
        v = proc.run(
            ["gpg", "--batch", "--quiet", "--verify", str(sig), str(target)],
            env=env,
        )
        return v.returncode, v.stderr


def check_redistributable_signature(repo: Repo, proc: Proc) -> tuple[int, list[str]]:
    root = repo.root / PUBLIC_REL
    rel_dir = _find_release_dir(repo)
    if rel_dir is None:
        return 0, ["  OK: no release directory — nothing to verify"]
    m = rel_dir / "integrity-redistributable.json"
    s = rel_dir / "integrity-redistributable.json.sig"
    if not (m.is_file() and s.is_file()):
        return 1, [f"  FAIL: missing {m.name} or {s.name}"]
    # use a temporary keyring seeded only with the published public key.
    key = _public_path(repo, ".well-known/pgp-key.asc")
    if not key.is_file():
        return 1, [f"  FAIL: published public key {key.relative_to(root)} missing"]
    rc, err = _verify_with_keyring(proc, key, s, m)
    if rc == -1:
        return 1, ["  FAIL: could not import published key", err]
    if rc != 0:
        return 1, [
            "  FAIL: integrity-redistributable.json.sig does not verify",
            err.strip()[:400],
        ]
    return 0, ["  OK: integrity-redistributable.json.sig verifies against published key"]


def _verify_detached_sig(repo: Repo, proc: Proc, target_path, sig_path) -> tuple[bool, str]:
    """Verify a detached gpg signature against the published key.
    Returns (ok, stderr_excerpt). uses a throwaway keyring seeded only
    with /.well-known/pgp-key.asc, so the host gpg keychain is not
    involved."""
    root = repo.root / PUBLIC_REL
    key = _public_path(repo, ".well-known/pgp-key.asc")
    if not key.is_file():
        return False, f"published public key {key.relative_to(root)} missing"
    if not (target_path.is_file() and sig_path.is_file()):
        return False, (
            f"missing {target_path.name} or {sig_path.name} in "
            f"{target_path.parent.relative_to(root)}"
        )
    rc, err = _verify_with_keyring(proc, key, sig_path, target_path)
    if rc == -1:
        return False, "could not import published key"
    if rc != 0:
        return False, err.strip()[:400]
    return True, ""


def check_release_json_signature(repo: Repo, proc: Proc) -> tuple[int, list[str]]:
    """R4: verify release.json.sig against the published public key.

    release.json is the single trust anchor that ties every other
    manifest in the release together by sha256 or live url. its
    signature is therefore the most efficient first verification step
    a downstream tool can perform."""
    rel_dir = _find_release_dir(repo)
    if rel_dir is None:
        return 0, ["  OK: no release directory — nothing to verify"]
    release_path = rel_dir / "release.json"
    release_sig = rel_dir / "release.json.sig"
    if not release_path.is_file():
        return 0, ["  OK: release.json not present — release predates phase 2 trust anchor"]
    ok, err = _verify_detached_sig(repo, proc, release_path, release_sig)
    if not ok:
        return 1, [f"  FAIL: release.json.sig does not verify ({err})"]
    return 0, ["  OK: release.json.sig verifies against published key"]


def check_exclusion_manifest_signature(repo: Repo, proc: Proc) -> tuple[int, list[str]]:
    """R5: verify EXCLUDED_FILES.json.sig against the published public
    key. ensures the per-edition exclusion taxonomy a verifier sees
    has not been tampered with."""
    rel_dir = _find_release_dir(repo)
    if rel_dir is None:
        return 0, ["  OK: no release directory — nothing to verify"]
    excl_path = _current_exclusion_manifest(rel_dir)
    if excl_path is None:
        return 0, [
            "  OK: EXCLUDED_FILES.json not present — release predates phase 1 exclusion manifest"
        ]
    excl_sig = excl_path.with_suffix(".json.sig")
    ok, err = _verify_detached_sig(repo, proc, excl_path, excl_sig)
    if not ok:
        return 1, [f"  FAIL: {excl_sig.name} does not verify ({err})"]
    return 0, [f"  OK: {excl_sig.name} verifies against published key"]


def check_exclusion_live_sha256_cross(repo: Repo) -> tuple[int, list[str]]:
    """R6: every exclusion entry that carries a live_sha256 field must
    match the value signed in public/integrity.json on disk. catches a
    classic tampering vector — adjusting the exclusion manifest to
    claim a benign hash for a substituted live file."""
    rel_dir = _find_release_dir(repo)
    if rel_dir is None:
        return 0, ["  OK: no release directory — nothing to verify"]
    excl_path = _current_exclusion_manifest(rel_dir)
    integ_rel = f"{PUBLIC_REL}/integrity.json"
    if not (excl_path is not None and repo.is_file(integ_rel)):
        return 0, [
            "  OK: exclusion manifest or live integrity manifest missing — nothing to cross-check"
        ]
    try:
        excl = json.loads(excl_path.read_text(encoding="utf-8"))
        live = json.loads(repo.read(integ_rel))
    except json.JSONDecodeError as e:
        return 1, [f"  FAIL: cannot parse manifest ({e})"]

    live_files = {
        (k.lstrip("/") if isinstance(k, str) else k): v for k, v in live.get("files", {}).items()
    }
    fails: list[str] = []
    checked = 0
    for entry in excl.get("exclusions", []):
        live_sha = entry.get("live_sha256")
        if not live_sha:
            continue
        path = entry.get("path", "")
        if path not in live_files:
            fails.append(
                f"{path}: exclusion manifest claims live_sha256 "
                f"but path is not present in live /integrity.json"
            )
            continue
        if live_files[path] != live_sha:
            fails.append(
                f"{path}: exclusion claims {live_sha[:24]}…, "
                f"live integrity says {live_files[path][:24]}…"
            )
        checked += 1

    if fails:
        lines = [f"  FAIL: {len(fails)} exclusion-cross-check issue(s):"]
        for f in fails[:12]:
            lines.append(f"    {f}")
        if len(fails) > 12:
            lines.append(f"    ... ({len(fails) - 12} more)")
        return 1, lines
    return 0, [f"  OK: {checked} exclusion live_sha256 entries match live integrity.json"]


# the six release checks, in fail-fast order, each tagged with its step label.
# a one-arg check ignores proc; a two-arg check needs the subprocess seam.
_RELEASE_CHECKS = [
    ("security.txt Expires within window", check_security_txt_expires),
    ("redistributable manifest matches archive contents", check_redistributable_manifest),
    ("redistributable manifest signature verifies", check_redistributable_signature),
    ("release.json trust anchor signature verifies", check_release_json_signature),
    ("exclusion manifest signature verifies", check_exclusion_manifest_signature),
    (
        "exclusion live_sha256 cross-checks against live integrity.json",
        check_exclusion_live_sha256_cross,
    ),
]


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo + Proc. runs the blocking gate first (short-circuits on non-zero), then
# the six release checks fail-fast. this is the test surface.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo, proc: Proc) -> Result:
    r = Result()
    gate_rc, gate_stdout, missing = run_predeploy(repo, proc)
    r.gate_rc = gate_rc
    r.gate_missing_line = missing
    r.gate_stdout = gate_stdout
    if missing is not None or gate_rc != 0:
        r.fails.append(f"gate.py returned {gate_rc}")
        return r

    for i, (label, check) in enumerate(_RELEASE_CHECKS, start=1):
        # two-arg checks take the Proc seam; one-arg checks don't.
        if check.__code__.co_argcount == 2:
            rc, lines = check(repo, proc)
        else:
            rc, lines = check(repo)
        r.steps.append((i, label, lines, rc))
        if rc != 0:
            r.fails.append(f"R{i} {label}: failed")
            return r
    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. builds the seams, evaluates, renders,
# returns exit code. the only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: pathlib.Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    proc = Proc()

    r = evaluate(repo, proc)

    if r.gate_missing_line is not None:
        print(r.gate_missing_line)
        return r.gate_rc

    # emit gate.py's captured output, THEN the banner — the order the original
    # produced via stdout buffering (see run_predeploy). end="" because the
    # captured stream already carries its own trailing newline.
    print(r.gate_stdout, end="")
    print("=" * 70)
    print("Running gate.py (deploy-blocking security + correctness gate)")
    print("=" * 70)
    if r.gate_rc != 0:
        return r.gate_rc

    total = len(_RELEASE_CHECKS)
    print()
    print("=" * 70)
    print("Release-specific gates")
    print("=" * 70)

    for step_no, label, lines, rc in r.steps:
        print(f"\n[{step_no}/{total}] {label}")
        for line in lines:
            print(line)
        if rc != 0:
            return 1

    print()
    print("OK: validate_release green — gate (blocking) + release 6/6")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
