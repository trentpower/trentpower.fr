#!/usr/bin/env python3
"""tools/verify/validate_claims_parity.py — claim-to-control honesty gate.

the public site makes specific supply-chain claims: SLSA build-track
provenance, keyless Sigstore signing, a Rekor transparency record, a
CycloneDX SBOM, and a PGP-signed integrity manifest. this validator
refuses to ship when any of those words is published as a claim but the
automated control that would make the claim true is not present.

POLICY AS DATA, ENFORCEMENT AS CODE. the claim->control bindings, public
wording, claim surface and human boundaries are declared in
policy-data/claims-map.yml (validated against schemas/claims-map.schema.json).
the CONTROL LOGIC — running gpg, parsing release.yml, checking files on
disk — stays here in Python, because that work is evidence collection a
rule engine cannot do. the map only says *what* is claimed and *which*
control backs it; this file decides *whether* the control passes.

discipline (mirrors validate_signing_status.py): only what is claimed is
enforced. a token absent from the claim surface requires nothing — the
gate never speculates about controls the site does not advertise. but the
surface is WIDE (glob-driven, not the union of stated_in), so a claim added
to a page the map did not anticipate is still seen and still must be backed.
"""

from __future__ import annotations

import fnmatch
import inspect
import re
import sys

try:
    import yaml
except ImportError:
    print("error: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

try:
    from jsonschema import Draft202012Validator
except ImportError:
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
import json  # noqa: E402

from paths import REPO_ROOT  # noqa: E402

CLAIMS_MAP = REPO_ROOT / "policy-data" / "claims-map.yml"
CLAIMS_SCHEMA = REPO_ROOT / "schemas" / "claims-map.schema.json"

WORKFLOWS = REPO_ROOT / ".github" / "workflows"
RELEASE_WORKFLOW = WORKFLOWS / "release.yml"
PRCHECKS_WORKFLOW = WORKFLOWS / "pr-checks.yml"
SCORECARD_WORKFLOW = WORKFLOWS / "scorecard.yml"
CHECKS_REGISTRY = REPO_ROOT / "tools" / "lib" / "checks.py"
BUILD_SH = REPO_ROOT / "tools" / "build" / "build.sh"
REUSE_TOML = REPO_ROOT / "REUSE.toml"
PGP_KEY = REPO_ROOT / "public" / ".well-known" / "pgp-key.asc"


def _read(path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _release_yml() -> str:
    return _read(RELEASE_WORKFLOW)


# ---------------------------------------------------------------------------
# controls — the evidence-collection logic the map binds claims to. each
# returns (ok, detail). control logic lives HERE, not in the data file.
# ---------------------------------------------------------------------------
def control_attestation() -> tuple[bool, str]:
    """SLSA / Sigstore / Rekor / attestation — backed by the build-provenance
    attestation step. keyless attestation implies Sigstore (Fulcio) signing and
    a Rekor transparency record, so the single step covers all four tokens."""
    text = _release_yml()
    ok = "attest-build-provenance" in text and "id-token: write" in text
    return ok, (
        "release.yml has no actions/attest-build-provenance step with "
        "id-token: write (the keyless Sigstore/Rekor attestation)"
    )


def control_sbom() -> tuple[bool, str]:
    """CycloneDX / SBOM — backed by the SBOM generation step AND the
    well-formedness validation step. a generated-but-unvalidated SBOM does
    not earn the claim, so both must be present in release.yml."""
    text = _release_yml()
    ok = "cyclonedx_py" in text and "bomFormat" in text
    return ok, (
        "release.yml is missing the cyclonedx_py generation step and/or the "
        "bomFormat well-formedness validation step"
    )


def control_pgp() -> tuple[bool, str]:
    """PGP — backed by the published public key on disk AND the gpg signature
    check registered as a blocking gate in checks.py."""
    if not PGP_KEY.is_file():
        return False, f"published key missing: {PGP_KEY.relative_to(REPO_ROOT)}"
    src = CHECKS_REGISTRY.read_text(encoding="utf-8") if CHECKS_REGISTRY.is_file() else ""
    # the gpg check must be registered as blocking (_B). bind to gpg's OWN
    # Check entry: name, then its single description string, then the tier as
    # the next positional arg. anchoring on that string (not a DOTALL `.*?`)
    # stops the match from sliding past a downgraded gpg entry into a later
    # check's _B — which would mask exactly the regression this gate detects.
    registered = re.search(r'Check\(\s*"gpg"\s*,\s*"(?:[^"\\]|\\.)*"\s*,\s*_B\b', src) is not None
    if not registered:
        return False, "the gpg signature check is not registered as blocking (_B) in checks.py"
    return True, ""


def control_scorecard() -> tuple[bool, str]:
    """OpenSSF / Scorecard — backed by the scorecard workflow running the
    official ossf/scorecard-action."""
    ok = "ossf/scorecard-action" in _read(SCORECARD_WORKFLOW)
    return ok, "scorecard.yml has no ossf/scorecard-action step (the OpenSSF Scorecard control)"


def control_osv() -> tuple[bool, str]:
    """OSV — backed by the osv-scanner dependency-vulnerability job in
    pr-checks.yml."""
    ok = "osv-scanner" in _read(PRCHECKS_WORKFLOW)
    return ok, "pr-checks.yml has no osv-scanner step (the OSV dependency-scan control)"


def control_reuse() -> tuple[bool, str]:
    """REUSE — backed by the reuse-lint job AND the REUSE.toml on disk."""
    if not REUSE_TOML.is_file():
        return False, "REUSE.toml is missing (the REUSE licensing control)"
    ok = "reuse lint" in _read(PRCHECKS_WORKFLOW)
    return ok, "pr-checks.yml has no `reuse lint` step (the REUSE licensing control)"


def control_deterministic() -> tuple[bool, str]:
    """deterministic build — backed by the release archive being built with
    sorted, owner-zeroed, fixed-mtime tar + name/timestamp-stripped gzip."""
    text = _release_yml()
    ok = "--sort=name" in text and "--numeric-owner" in text and "gzip -n" in text
    return ok, (
        "release.yml archive step is missing the determinism flags "
        "(tar --sort=name --numeric-owner | gzip -n)"
    )


def control_reproducible() -> tuple[bool, str]:
    """reproducibility goal — backed by the build's --check path, which
    re-renders from source and asserts zero drift against the committed bytes."""
    ok = "--check" in _read(BUILD_SH)
    return ok, "build.sh has no --check reproducibility (re-render / no-drift) path"


# the set of control_* functions defined in this module, resolved by name so
# the map's `verified_by` strings can bind to them.
_CONTROLS = {
    name: fn
    for name, fn in sorted(globals().items())
    if name.startswith("control_") and inspect.isfunction(fn)
}

# controls that read release.yml — used by meta-check (5) to confirm a claim
# declaring enforced_at: release is backed by a control that actually inspects
# the release workflow. derived from source, not hand-maintained.
_RELEASE_READING = {
    name for name, fn in _CONTROLS.items() if "_release_yml" in inspect.getsource(fn)
}


# ---------------------------------------------------------------------------
# map loading + surface computation
# ---------------------------------------------------------------------------
def load_map() -> dict:
    """load + schema-validate policy-data/claims-map.yml. fail loud on any
    structural problem before parity logic runs."""
    data = yaml.safe_load(CLAIMS_MAP.read_text(encoding="utf-8"))
    schema = json.loads(CLAIMS_SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path)
    )
    if errors:
        lines = [
            f"  {'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}" for e in errors[:12]
        ]
        raise SystemExit(
            "FAIL: policy-data/claims-map.yml does not satisfy "
            "schemas/claims-map.schema.json:\n" + "\n".join(lines)
        )
    return data


def _surface_files(surface: dict) -> list:
    """resolve the claim_surface include/exclude globs to a sorted file list."""
    include = surface.get("include", [])
    exclude = surface.get("exclude", [])
    found: set = set()
    for pat in include:
        found.update(p for p in REPO_ROOT.glob(pat) if p.is_file())

    def excluded(rel: str) -> bool:
        for pat in exclude:
            if pat.endswith("/**"):
                prefix = pat[:-3]
                if rel == prefix or rel.startswith(prefix + "/"):
                    return True
            elif fnmatch.fnmatch(rel, pat):
                return True
        return False

    return sorted(p for p in found if not excluded(str(p.relative_to(REPO_ROOT))))


def _quote_first_line(text: str, token: str) -> str:
    for line in text.splitlines():
        if token in line:
            return line.strip()
    return ""


# ---------------------------------------------------------------------------
# meta-checks — the honesty the declarative map enables. each appends to a
# failure list; any failure fails the gate loudly.
# ---------------------------------------------------------------------------
def _meta_checks(data: dict, surface_paths: list) -> list[str]:
    claims = data["claims"]
    fails: list[str] = []
    surface_rel = {str(p.relative_to(REPO_ROOT)) for p in surface_paths}

    referenced: set = set()
    for token, c in claims.items():
        vb = c["verified_by"]
        # (1) every verified_by name resolves to a real control_* function.
        for name in vb:
            if name not in _CONTROLS:
                fails.append(f'claim "{token}": verified_by "{name}" is not a control_* function')
            else:
                referenced.add(name)
        # (3) every stated_in path exists AND is inside the scanned surface
        #     (a claim cannot declare a location the scanner does not walk).
        for sp in c["stated_in"]:
            if not (REPO_ROOT / sp).is_file():
                fails.append(f'claim "{token}": stated_in path does not exist: {sp}')
            elif sp not in surface_rel:
                fails.append(
                    f'claim "{token}": stated_in path "{sp}" is outside the scanned '
                    "claim_surface (widen claim_surface.include or fix the path)"
                )
        # (6) goal/manual may have empty controls; enforced must not. goal must
        #     not be release-blocking, nor worded as achieved.
        if c["status"] == "enforced" and not vb:
            fails.append(f'claim "{token}": status enforced but verified_by is empty')
        if c["status"] == "goal" and c["release_blocking"]:
            fails.append(f'claim "{token}": status goal must not be release_blocking')
        # (5) release_blocking claims must be wired where enforced_at says.
        if c["release_blocking"]:
            ea = c["enforced_at"]
            if "release" in ea and not (set(vb) & _RELEASE_READING):
                fails.append(
                    f'claim "{token}": enforced_at lists "release" but no bound control '
                    "reads release.yml"
                )
            if "pr-gate" in ea:
                gate_id = c.get("pr_gate_check")
                if not gate_id:
                    fails.append(
                        f'claim "{token}": release_blocking + enforced_at pr-gate requires a '
                        "pr_gate_check naming the blocking checks.py id"
                    )
                else:
                    src = _read(CHECKS_REGISTRY)
                    pat = rf'Check\(\s*"{re.escape(gate_id)}"\s*,\s*"(?:[^"\\]|\\.)*"\s*,\s*_B\b'
                    if not re.search(pat, src):
                        fails.append(
                            f'claim "{token}": pr_gate_check "{gate_id}" is not registered as '
                            "blocking (_B) in checks.py"
                        )
            if "ruleset" in ea:
                print(
                    f'  NOTE: claim "{token}" is enforced at ruleset level — confirm it is a '
                    "required status check (governance audit, see docs/GITHUB-RULESETS.md)."
                )

    # (2) no orphan controls: every control_* defined here is bound by >=1 claim.
    for name in _CONTROLS:
        if name not in referenced:
            fails.append(
                f'control "{name}" is defined but bound by no claim (orphan control — '
                "bind it in policy-data/claims-map.yml or remove it)"
            )
    return fails


def main() -> int:
    data = load_map()
    claims = data["claims"]
    surface_paths = _surface_files(data["claim_surface"])

    meta_fails = _meta_checks(data, surface_paths)

    sources = [(p, p.read_text(encoding="utf-8")) for p in surface_paths]

    # which tokens are actually claimed anywhere on the surface.
    claimed: dict[str, list] = {}
    for path, text in sources:
        for token in claims:
            if token in text:
                claimed.setdefault(token, []).append((path, text))

    parity_fails: list[str] = []
    backed = 0
    control_cache: dict = {}
    for token, occurrences in claimed.items():
        controls = [_CONTROLS[n] for n in claims[token]["verified_by"] if n in _CONTROLS]
        token_ok = True
        detail = ""
        for control in controls:
            if control not in control_cache:
                control_cache[control] = control()
            ok, det = control_cache[control]
            if not ok:
                token_ok = False
                detail = det
                break
        if token_ok and controls:
            backed += 1
            continue
        for path, text in occurrences:
            quoted = _quote_first_line(text, token)
            rel = path.relative_to(REPO_ROOT)
            parity_fails.append(f'{rel}: claims "{token}" but {detail}\n        > {quoted}')

    rc = 0
    if meta_fails:
        print(f"  FAIL: {len(meta_fails)} claims-map integrity problem(s):")
        for f in meta_fails:
            print(f"    {f}")
        rc = 1
    if parity_fails:
        print(f"  FAIL: {len(parity_fails)} unbacked supply-chain claim(s):")
        for f in parity_fails:
            print(f"    {f}")
        rc = 1
    if rc:
        return rc

    if not claimed:
        print("  OK: claims-map valid; no supply-chain claims on the public surface to back.")
        return 0
    print(
        f"  OK: claims-map valid; {backed} supply-chain claim type(s) across "
        f"{len(surface_paths)} surface file(s) each map to a passing automated control."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
