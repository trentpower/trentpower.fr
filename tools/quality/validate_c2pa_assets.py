#!/usr/bin/env python3
"""tools/quality/validate_c2pa_assets.py — C2PA Content-Credentials policy gate.

C2PA is a SECOND, PORTABLE provenance layer: it lets individual media files
carry their own provenance once they leave the site. It does not replace the
PGP-signed integrity manifest, which remains the site-level proof. This gate
keeps the C2PA *declaration* honest — it never inspects truth, authorship, or
AI-use claims, only that what the policy says lines up with what is on disk and
in the signed manifest.

POLICY AS DATA, ENFORCEMENT AS CODE. The asset list, statuses, AI vocabulary and
publisher identity are declared in policy-data/c2pa-assets.yml (validated against
schemas/c2pa-assets.schema.json). The coherence logic — does the asset exist, is
it in integrity.json, does it actually carry an embedded credential — stays here.

Staging (see docs/C2PA.md). This validator starts ADVISORY in checks.py: it
reports but never blocks deploy, while the signing workflow stabilises. It is
promoted to BLOCKING only after an edition cycle, and only the `required`-asset
conditions block then.

shape (deep module, small interface). The external interface is `main() -> int`
plus the YAML data contract. The compute path is `evaluate(repo, data, inspect)
-> Result` over the injected `Repo` seam, with the C2PA inspector as a second
injected seam — so the whole gate runs over a fixture repo with a fake inspector,
no real signing keys and no monkeypatching. `evaluate` returns a Result and never
prints; `main` is the only side-effecting adapter.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover (dependency-missing fallback)
    print("error: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover (dependency-missing fallback)
    print("error: jsonschema>=4.18 required. Install with: pip install jsonschema", file=sys.stderr)
    sys.exit(2)

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

POLICY_REL = "policy-data/c2pa-assets.yml"
SCHEMA_REL = "schemas/c2pa-assets.schema.json"
IDENTITY_REL = "tools/config/identity_canonical.json"
INTEGRITY_REL = "public/integrity.json"

# the in-scope statuses — assets meant to carry (or come to carry) credentials.
_IN_SCOPE = ("required", "optional", "future")

# C2PA inspector result: a manifest is present (True), provably absent (False),
# or could-not-check (None — tooling unavailable). The third state is what keeps
# the advisory stage honest on a host without the c2pa library.
InspectResult = tuple  # (bool | None, str)
Inspector = Callable[["Repo", str], InspectResult]

_MIME = {
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".pdf": "application/pdf",
}


def default_inspector(repo: Repo, asset_rel: str) -> InspectResult:
    """Production C2PA inspector. Returns (None, reason) when the c2pa library is
    not importable on this host — the advisory stage treats that as a skip, not a
    failure (the build host is aarch64, where no c2patool binary ships; see
    docs/C2PA-SPIKE.md). When the library is present, reports whether the file
    carries an embedded manifest."""
    try:
        import c2pa  # noqa: PLC0415
    except ImportError:
        return None, "c2pa tooling unavailable on this host"
    return _read_embedded_manifest(c2pa, repo.root / asset_rel)  # pragma: no cover


def _read_embedded_manifest(c2pa, abs):  # pragma: no cover
    # Production C2PA adapter: needs the c2pa library + a real (signed) asset on
    # disk. The unit tests inject a fake inspector into evaluate() instead, so
    # this path is exercised by the live validate run, not the unit suite.
    if not abs.is_file():
        return None, "asset file absent"
    mime = _MIME.get(abs.suffix.lower())
    if mime is None:
        return None, f"no known mime for {abs.suffix}"
    try:
        with open(abs, "rb") as fh:
            reader = c2pa.Reader(mime, fh)
            data = json.loads(reader.json())
    except Exception as exc:  # noqa: BLE001  (no manifest reads as an error here)
        return False, f"no readable C2PA manifest ({type(exc).__name__})"
    return (bool(data.get("active_manifest")), "")


# ---------------------------------------------------------------------------
# Result — the value `evaluate` returns. The interface is this struct, not
# stdout: tests assert on it; `main` renders it. `ok` iff nothing failed.
# ---------------------------------------------------------------------------
@dataclass
class Result:
    meta_fails: list[str] = field(default_factory=list)
    asset_fails: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    declared: int = 0
    by_status: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.meta_fails and not self.asset_fails


# ---------------------------------------------------------------------------
# policy loading + schema validation
# ---------------------------------------------------------------------------
def load_policy(repo: Repo) -> tuple[dict | None, list[str]]:
    """load + schema-validate policy-data/c2pa-assets.yml. Returns (data, errors);
    never raises on a bad policy — the caller decides how to report."""
    raw = repo.read(POLICY_REL)
    if not raw:
        return None, [f"{POLICY_REL} is missing or empty"]
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        return None, [f"{POLICY_REL} is not valid YAML: {exc}"]
    schema_raw = repo.read(SCHEMA_REL)
    if not schema_raw:
        return None, [f"{SCHEMA_REL} is missing — cannot validate policy shape"]
    schema = json.loads(schema_raw)
    errors = [
        f"{'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}"
        for e in sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
    ]
    return (None if errors else data), errors


def _identity_url(repo: Repo) -> str | None:
    raw = repo.read(IDENTITY_REL)
    if not raw:
        return None
    try:
        return json.loads(raw).get("url")
    except json.JSONDecodeError:
        return None


def _integrity_files(repo: Repo) -> set[str]:
    """public-relative paths recorded in integrity.json (its `files` keys)."""
    raw = repo.read(INTEGRITY_REL)
    if not raw:
        return set()
    try:
        return set(json.loads(raw).get("files", {}))
    except json.JSONDecodeError:
        return set()


def _public_rel(asset_path: str) -> str:
    """map a repo-relative public/ path to its integrity.json key (public-relative)."""
    return asset_path[len("public/") :] if asset_path.startswith("public/") else asset_path


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo + Inspector seams. this is the test surface.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo, data: dict, inspect: Inspector = default_inspector) -> Result:
    result = Result()
    assets = data.get("assets", [])
    result.declared = len(assets)

    vocab = set(data.get("ai_vocabulary", []))
    pub_url = (data.get("publisher") or {}).get("url", "")

    # publisher identity must agree with the canonical identity file.
    ident = _identity_url(repo)
    if ident is not None and pub_url and pub_url != ident:
        result.meta_fails.append(
            f"publisher.url {pub_url!r} disagrees with identity_canonical.json url {ident!r}"
        )

    integrity = _integrity_files(repo)
    seen_paths: set[str] = set()

    for a in assets:
        status = a["status"]
        result.by_status[status] = result.by_status.get(status, 0) + 1
        path = a.get("path")
        pattern = a.get("pattern")
        label = path or pattern or "(unnamed)"

        # duplicate-target detection (path or pattern).
        key = path or f"glob:{pattern}"
        if key in seen_paths:
            result.meta_fails.append(f"duplicate asset entry: {label}")
        seen_paths.add(key)

        if status == "excluded":
            # stale-exclusion hygiene: an exclusion that matches nothing is a note,
            # not a failure (it may anticipate an asset class not yet present).
            if path and not repo.is_file(path):
                result.notes.append(f"excluded path no longer on disk (stale exclusion?): {path}")
            if pattern and not repo.glob(pattern):
                result.notes.append(f"excluded pattern matches no files (stale?): {pattern}")
            continue

        # in-scope: required / optional / future.
        ai = a.get("ai_involvement", "")
        if ai not in vocab:
            result.meta_fails.append(f"{label}: ai_involvement {ai!r} is not in ai_vocabulary")
        cu = a.get("canonical_url", "")
        if pub_url and not cu.startswith(pub_url):
            result.meta_fails.append(
                f"{label}: canonical_url {cu!r} is not under publisher url {pub_url!r}"
            )

        # the declared asset must exist on disk (a declaration pointing at nothing
        # is a policy error, even before signing).
        if not repo.is_file(path):
            result.asset_fails.append(f"{label}: declared asset not found on disk")
            continue

        if status == "future":
            result.notes.append(f"{label}: status future — declared, not yet signed")
            continue

        # required / optional: must be recorded in the signed integrity manifest.
        if _public_rel(path) not in integrity:
            msg = f"{label}: not listed in {INTEGRITY_REL}"
            (result.asset_fails if status == "required" else result.notes).append(msg)

        # required / optional: check for an embedded credential via the inspector.
        present, detail = inspect(repo, path)
        if present is None:
            result.notes.append(f"{label}: credential check skipped — {detail}")
        elif present is False:
            msg = f"{label}: no embedded C2PA credential ({detail})"
            (result.asset_fails if status == "required" else result.notes).append(msg)

    return result


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. loads, evaluates, renders, returns exit
# code. the only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:  # pragma: no cover (side-effecting adapter)
    repo = Repo(repo_root)
    data, errors = load_policy(repo)
    if errors:
        print(f"  FAIL: {POLICY_REL} does not satisfy {SCHEMA_REL}:")
        for e in errors[:12]:
            print(f"    {e}")
        return 1

    result = evaluate(repo, data)
    for note in result.notes:
        print(f"  NOTE: {note}")

    if result.meta_fails:
        print(f"  FAIL: {len(result.meta_fails)} C2PA policy integrity problem(s):")
        for f in result.meta_fails:
            print(f"    {f}")
    if result.asset_fails:
        print(f"  FAIL: {len(result.asset_fails)} C2PA asset problem(s):")
        for f in result.asset_fails:
            print(f"    {f}")
    if not result.ok:
        return 1

    summary = ", ".join(f"{n} {s}" for s, n in sorted(result.by_status.items()))
    print(
        f"  OK: C2PA policy coherent — {result.declared} asset(s) declared ({summary or 'none'})."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
