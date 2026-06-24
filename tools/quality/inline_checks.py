"""inline_checks.py — the cross-cutting gate checks that do not (yet) fit the
ADR-0002 validator mould.

Library, not a script: each check here is a small function that tools/lib/checks.py
registers into the blocking tier; gate.py runs them. Eight former inline checks
were split into ADR-0002 `validate_*.py` modules (Repo seam, pure `evaluate`,
thin `main`, fixture-tested); the two below stayed because each needs more than
the filesystem seam:

  check_gpg — shells out to `gpg` to verify integrity.json.sig against the
      *published* key in a throwaway keyring. Needs a process seam (a future
      `Proc` adapter), not just `Repo`, to be tested without a real gpg.

  check_frozen_archives_immutable — compares every frozen-release file against
      metadata/archive-baseline.json AND *writes* the baseline on first-emit
      (auto-seal). The write side effect is not a pure `evaluate`; splitting it
      needs a write-policy seam decision first.

Each function prints its own OK/FAIL lines and returns 0 (pass) or 1 (fail).
"""

import json
import os
import re
import subprocess
import sys

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
from paths import ARCHIVE_BASELINE  # noqa: E402
from paths import PUBLIC_DIR as ROOT  # noqa: E402


def check_gpg() -> int:
    """Verify integrity.json.sig against the *published* key only.

    Uses a throwaway GNUPGHOME seeded solely from
    public/.well-known/pgp-key.asc, so verification is deterministic on
    clean machines / CI and never depends on the operator's ambient
    keyring or trustdb. (validate_release.py:_verify_detached_sig uses
    the same pattern for the release-artefact signatures.)"""
    import tempfile

    sig = ROOT / "integrity.json.sig"
    man = ROOT / "integrity.json"
    key = ROOT / ".well-known" / "pgp-key.asc"
    if not (sig.exists() and man.exists()):
        print("  FAIL: integrity.json or integrity.json.sig missing")
        return 1
    if not key.is_file():
        print(f"  FAIL: published key {key.relative_to(ROOT)} missing")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env["GNUPGHOME"] = tmp
        env.pop("GPG_AGENT_INFO", None)
        imp = subprocess.run(
            ["gpg", "--batch", "--quiet", "--import", str(key)],
            env=env,
            capture_output=True,
            text=True,
        )
        if imp.returncode != 0:
            print("  FAIL: could not import published key into temp keyring")
            for line in (imp.stdout + imp.stderr).splitlines():
                print(f"    {line}")
            return 1
        r = subprocess.run(
            ["gpg", "--batch", "--quiet", "--verify", str(sig), str(man)],
            env=env,
            capture_output=True,
            text=True,
        )
    out = r.stdout + r.stderr
    if r.returncode != 0 or "Good signature" not in out:
        print("  FAIL: gpg verification failed (against published key)")
        for line in out.splitlines():
            print(f"    {line}")
        return 1
    # print the key fingerprint line for the build log.
    for line in out.splitlines():
        if "Good signature" in line or "fingerprint" in line.lower():
            print(f"  {line.strip()}")
    return 0


def _hash_archive_tree() -> dict:
    """Walk every frozen-release directory and hash files that must
    be byte-stable. Returns {relative_path: sha256_b64_sri}.

    Two directory shapes:

      YYYY-MM     legacy editions (e.g. 2026-02). entire directory is
                  frozen and every file is included in the baseline.

      YYYY-MM-DD  full-date editions (2026-05-09, 2026-05-17, …). only
                  the canonical archive bytes and canonical companion
                  manifests are locked. dated rebuild artefacts
                  (trentpower-fr-<build_date>.zip with build_date !=
                  edition) are not baseline-locked — they are tracked
                  by the per-edition builds.json signature instead.

    in both shapes, .sig files are EXCLUDED from the baseline because
    gpg detached signatures carry random salt and are not bitwise
    deterministic across runs. SHA256SUMS is excluded because it
    aggregates over both archives and changes as rebuilds are added.
    builds.json is excluded because its `rebuilds[]` grows on each
    across-day drift.
    """
    rel_root = ROOT / "integrity" / "releases"
    out: dict[str, str] = {}
    if not rel_root.is_dir():
        return out

    def _hash(fp):
        return sri_sha256(fp.read_bytes())

    for child in sorted(rel_root.iterdir()):
        if not child.is_dir():
            continue
        if re.fullmatch(r"\d{4}-\d{2}", child.name):
            # legacy edition — lock the whole tree.
            for fp in sorted(child.rglob("*")):
                if not fp.is_file():
                    continue
                rel = fp.relative_to(ROOT).as_posix()
                out[rel] = _hash(fp)
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", child.name):
            # full-date edition — lock canonical bytes + companion
            # manifests only. byte-stable; .sig / SHA256SUMS /
            # builds.json excluded for the reasons in the docstring.
            canonical_basename = f"trentpower-fr-{child.name}"
            # The .zip / .tar.gz binaries themselves are server-canonical and
            # are NOT committed to git (see public/integrity/releases/README.md).
            # Their immutability is sealed by the committed .sha256 sidecars
            # below — the checksum is the editorial seal; the bytes are verified
            # remotely against it. So only the sidecars + manifests are locked.
            byte_stable = [
                f"{canonical_basename}.zip.sha256",
                f"{canonical_basename}.tar.gz.sha256",
                "integrity-redistributable.json",
                "EXCLUDED_FILES.json",
                "EXCLUDED_FILES.txt",
                "release.json",
                # legacy 2026-02 shape kept its own integrity.json
                # inside; other full-date editions don't have one but
                # the lookup tolerates absence.
                "integrity.json",
            ]
            for fn in byte_stable:
                fp = child / fn
                if fp.is_file():
                    rel = fp.relative_to(ROOT).as_posix()
                    out[rel] = _hash(fp)
    return out


def check_frozen_archives_immutable() -> int:
    """Compare every file under /integrity/releases/YYYY-MM/ against a
    locally-managed baseline at metadata/archive-baseline.json.

    Frozen archives must be immutable going forward; this is the gate
    that catches a generator (or a manual edit) accidentally rewriting
    historical bytes. Pre-existing drift in the per-release integrity.json
    files is intentionally NOT consulted — those are historical snapshots
    and have known drift from earlier non-hardened pipeline runs.

    First run: writes the baseline from the current tree and exits OK
    (no prior baseline to compare against). Subsequent runs: any byte
    drift = FAIL. Reseal explicitly with `--reseal-archives` (or by
    deleting the baseline file) when an archive intentionally changes.
    """
    current = _hash_archive_tree()
    if not current:
        print("  OK: no frozen archives present — nothing to check")
        return 0
    if not ARCHIVE_BASELINE.exists():
        ARCHIVE_BASELINE.write_text(
            json.dumps(current, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"  OK: sealed initial baseline of {len(current)} archive file(s)")
        print(f"       (baseline written to {ARCHIVE_BASELINE.name};")
        print("        future drift will fail this gate)")
        return 0
    try:
        baseline = json.loads(ARCHIVE_BASELINE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  FAIL: {ARCHIVE_BASELINE.name} invalid JSON ({e}); delete to reseal")
        return 1

    # drift detection: any baseline file that disagrees with disk OR
    # has gone missing is a hard fail. existing baseline entries are
    # the editorial seal.
    drift_fails: list[str] = []
    for rel, expected in baseline.items():
        got = current.get(rel)
        if got is None:
            drift_fails.append(f"{rel}: in baseline but missing on disk")
        elif got != expected:
            drift_fails.append(f"{rel}: drift (expected {expected[:24]}, got {got[:24]})")
    if drift_fails:
        print(f"  FAIL: {len(drift_fails)} frozen-archive drift(s):")
        for f in drift_fails:
            print(f"    {f}")
        print("       to reseal an edition intentionally:")
        print("       python3 tools/seal_edition.py --reseal-canonical <edition>")
        return 1

    # new canonicals on disk that aren't in baseline yet: auto-seal.
    # this is the seal-on-first-emit path — a newly emitted canonical
    # archive for a fresh edition (or a freshly-introduced companion
    # manifest for a previously-shipped edition) enters the baseline
    # the first time predeploy observes it. subsequent drift then
    # trips the check above.
    new_entries = {rel: current[rel] for rel in current if rel not in baseline}
    if new_entries:
        baseline.update(new_entries)
        ARCHIVE_BASELINE.write_text(
            json.dumps(baseline, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"  OK: auto-sealed {len(new_entries)} new canonical file(s) into baseline")
        for rel in sorted(new_entries):
            print(f"      + {rel}")
        print(f"      commit {ARCHIVE_BASELINE.name} to record the seal in git history")

    print(f"  OK: frozen archives immutable ({len(current)} files match baseline)")
    return 0
