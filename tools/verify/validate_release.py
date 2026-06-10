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

Usage:
    python3 tools/validate_release.py
"""

import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
import zipfile

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
from hashing import sri_sha256
from paths import PUBLIC_DIR as ROOT
from paths import TOOLS_DIR as SCRIPTS

# the deploy-blocking gate (security + correctness). advisory quality lint
# lives in tools/lint.py and is run non-blocking in CI, not here.
GATE = SCRIPTS / "quality" / "gate.py"

EXPIRES_WINDOW_DAYS = 60


def _step(n_total, n, label):
    print(f"\n[{n}/{n_total}] {label}")


def run_predeploy() -> int:
    if not GATE.exists():
        print(f"  FAIL: {GATE} not found")
        return 1
    print("=" * 70)
    print("Running gate.py (deploy-blocking security + correctness gate)")
    print("=" * 70)
    return subprocess.run([sys.executable, str(GATE)]).returncode


def check_security_txt_expires() -> int:
    """RFC 9116 §2.5.5 — Expires must be a future date. We require a
    60-day cushion so the certificate of currency does not lapse
    silently between releases."""
    sec = ROOT / ".well-known" / "security.txt"
    if not sec.is_file():
        print(f"  FAIL: {sec.relative_to(ROOT)} missing")
        return 1
    text = sec.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^Expires:\s*(\S+)\s*$", text, re.MULTILINE)
    if not m:
        print("  FAIL: security.txt has no Expires: line")
        return 1
    raw = m.group(1)
    # accept either "2027-02-10T00:00:00.000Z" or "2027-02-10T00:00:00Z"
    try:
        # python 3.11+ understands trailing z directly; older needs munging.
        normalised = raw.replace("Z", "+00:00")
        # trim sub-second precision python's fromisoformat doesn't accept on <3.11.
        normalised = re.sub(r"\.\d+", "", normalised)
        expires = dt.datetime.fromisoformat(normalised)
    except ValueError:
        print(f"  FAIL: security.txt Expires: '{raw}' is not parseable ISO 8601")
        return 1
    now = dt.datetime.now(dt.UTC)
    delta_days = (expires - now).days
    if delta_days < EXPIRES_WINDOW_DAYS:
        print(f"  FAIL: security.txt Expires {raw} is only {delta_days} day(s)")
        print(f"        away (window is {EXPIRES_WINDOW_DAYS} days). Update")
        print("        the Expires line and re-sign attribution.sig.")
        return 1
    print(f"  OK: security.txt Expires {raw} ({delta_days} days from now)")
    return 0


def _find_release_dir() -> pathlib.Path | None:
    rel = ROOT / "integrity" / "releases"
    if not rel.is_dir():
        return None
    for child in sorted(rel.iterdir(), reverse=True):
        if child.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", child.name):
            return child
    return None


def check_redistributable_manifest() -> int:
    rel_dir = _find_release_dir()
    if rel_dir is None:
        print("  OK: no date-precision release directory present — nothing to check")
        return 0
    manifest_path = rel_dir / "integrity-redistributable.json"
    if not manifest_path.is_file():
        print(f"  FAIL: {manifest_path.relative_to(ROOT)} missing — run build_release_archives.py")
        return 1
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  FAIL: {manifest_path.name} invalid JSON ({e})")
        return 1
    declared = manifest.get("files", {})
    if not isinstance(declared, dict) or not declared:
        print(f"  FAIL: {manifest_path.name} missing 'files' map")
        return 1

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
            print(f"  FAIL: no trentpower-fr-*.zip in {rel_dir.relative_to(ROOT)}")
            return 1
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
        print(f"  FAIL: {len(fails)} redistributable-manifest issue(s):")
        for f in fails[:12]:
            print(f"    {f}")
        if len(fails) > 12:
            print(f"    ... ({len(fails) - 12} more)")
        return 1
    print(f"  OK: {len(declared)} declared files match {zip_path.name} byte-for-byte")
    return 0


def check_redistributable_signature() -> int:
    rel_dir = _find_release_dir()
    if rel_dir is None:
        print("  OK: no release directory — nothing to verify")
        return 0
    m = rel_dir / "integrity-redistributable.json"
    s = rel_dir / "integrity-redistributable.json.sig"
    if not (m.is_file() and s.is_file()):
        print(f"  FAIL: missing {m.name} or {s.name}")
        return 1
    # use a temporary keyring seeded only with the published public key.
    key = ROOT / ".well-known" / "pgp-key.asc"
    if not key.is_file():
        print(f"  FAIL: published public key {key.relative_to(ROOT)} missing")
        return 1
    import os as _os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        env = _os.environ.copy()
        env["GNUPGHOME"] = tmp
        env.pop("GPG_AGENT_INFO", None)
        imp = subprocess.run(
            ["gpg", "--batch", "--quiet", "--import", str(key)],
            env=env,
            capture_output=True,
            text=True,
        )
        if imp.returncode != 0:
            print("  FAIL: could not import published key")
            print(imp.stderr)
            return 1
        v = subprocess.run(
            ["gpg", "--batch", "--quiet", "--verify", str(s), str(m)],
            env=env,
            capture_output=True,
            text=True,
        )
        if v.returncode != 0:
            print("  FAIL: integrity-redistributable.json.sig does not verify")
            print(v.stderr.strip()[:400])
            return 1
    print("  OK: integrity-redistributable.json.sig verifies against published key")
    return 0


def _verify_detached_sig(target_path, sig_path) -> tuple[bool, str]:
    """Verify a detached gpg signature against the published key.
    Returns (ok, stderr_excerpt). uses a throwaway keyring seeded only
    with /.well-known/pgp-key.asc, so the host gpg keychain is not
    involved."""
    import os as _os
    import tempfile

    key = ROOT / ".well-known" / "pgp-key.asc"
    if not key.is_file():
        return False, f"published public key {key.relative_to(ROOT)} missing"
    if not (target_path.is_file() and sig_path.is_file()):
        return False, (
            f"missing {target_path.name} or {sig_path.name} in "
            f"{target_path.parent.relative_to(ROOT)}"
        )
    with tempfile.TemporaryDirectory() as tmp:
        env = _os.environ.copy()
        env["GNUPGHOME"] = tmp
        env.pop("GPG_AGENT_INFO", None)
        imp = subprocess.run(
            ["gpg", "--batch", "--quiet", "--import", str(key)],
            env=env,
            capture_output=True,
            text=True,
        )
        if imp.returncode != 0:
            return False, "could not import published key"
        v = subprocess.run(
            ["gpg", "--batch", "--quiet", "--verify", str(sig_path), str(target_path)],
            env=env,
            capture_output=True,
            text=True,
        )
        if v.returncode != 0:
            return False, v.stderr.strip()[:400]
    return True, ""


def check_release_json_signature() -> int:
    """R4: verify release.json.sig against the published public key.

    release.json is the single trust anchor that ties every other
    manifest in the release together by sha256 or live url. its
    signature is therefore the most efficient first verification step
    a downstream tool can perform."""
    rel_dir = _find_release_dir()
    if rel_dir is None:
        print("  OK: no release directory — nothing to verify")
        return 0
    release_path = rel_dir / "release.json"
    release_sig = rel_dir / "release.json.sig"
    if not release_path.is_file():
        print("  OK: release.json not present — release predates phase 2 trust anchor")
        return 0
    ok, err = _verify_detached_sig(release_path, release_sig)
    if not ok:
        print(f"  FAIL: release.json.sig does not verify ({err})")
        return 1
    print("  OK: release.json.sig verifies against published key")
    return 0


def check_exclusion_manifest_signature() -> int:
    """R5: verify EXCLUDED_FILES.json.sig against the published public
    key. ensures the per-edition exclusion taxonomy a verifier sees
    has not been tampered with."""
    rel_dir = _find_release_dir()
    if rel_dir is None:
        print("  OK: no release directory — nothing to verify")
        return 0
    excl_path = rel_dir / "EXCLUDED_FILES.json"
    excl_sig = rel_dir / "EXCLUDED_FILES.json.sig"
    if not excl_path.is_file():
        print("  OK: EXCLUDED_FILES.json not present — release predates phase 1 exclusion manifest")
        return 0
    ok, err = _verify_detached_sig(excl_path, excl_sig)
    if not ok:
        print(f"  FAIL: EXCLUDED_FILES.json.sig does not verify ({err})")
        return 1
    print("  OK: EXCLUDED_FILES.json.sig verifies against published key")
    return 0


def check_exclusion_live_sha256_cross() -> int:
    """R6: every exclusion entry that carries a live_sha256 field must
    match the value signed in public/integrity.json on disk. catches a
    classic tampering vector — adjusting the exclusion manifest to
    claim a benign hash for a substituted live file."""
    rel_dir = _find_release_dir()
    if rel_dir is None:
        print("  OK: no release directory — nothing to verify")
        return 0
    excl_path = rel_dir / "EXCLUDED_FILES.json"
    integ_path = ROOT / "integrity.json"
    if not (excl_path.is_file() and integ_path.is_file()):
        print(
            "  OK: exclusion manifest or live integrity manifest missing — nothing to cross-check"
        )
        return 0
    try:
        excl = json.loads(excl_path.read_text(encoding="utf-8"))
        live = json.loads(integ_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  FAIL: cannot parse manifest ({e})")
        return 1

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
        print(f"  FAIL: {len(fails)} exclusion-cross-check issue(s):")
        for f in fails[:12]:
            print(f"    {f}")
        if len(fails) > 12:
            print(f"    ... ({len(fails) - 12} more)")
        return 1
    print(f"  OK: {checked} exclusion live_sha256 entries match live integrity.json")
    return 0


def main() -> int:
    rc = run_predeploy()
    if rc != 0:
        return rc

    total = 6
    print()
    print("=" * 70)
    print("Release-specific gates")
    print("=" * 70)

    _step(total, 1, "security.txt Expires within window")
    if check_security_txt_expires() != 0:
        return 1

    _step(total, 2, "redistributable manifest matches archive contents")
    if check_redistributable_manifest() != 0:
        return 1

    _step(total, 3, "redistributable manifest signature verifies")
    if check_redistributable_signature() != 0:
        return 1

    _step(total, 4, "release.json trust anchor signature verifies")
    if check_release_json_signature() != 0:
        return 1

    _step(total, 5, "exclusion manifest signature verifies")
    if check_exclusion_manifest_signature() != 0:
        return 1

    _step(total, 6, "exclusion live_sha256 cross-checks against live integrity.json")
    if check_exclusion_live_sha256_cross() != 0:
        return 1

    print()
    print("OK: validate_release green — gate (blocking) + release 6/6")
    return 0


if __name__ == "__main__":
    sys.exit(main())
