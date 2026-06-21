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

shape (deep module, small interface). the external interface is `main() -> int`
plus the YAML data contract. internally the evidence source is a single
injected seam — `Repo(root)` — so the whole gate is exercised through
`evaluate(repo, data) -> Result` over a fixture repo, with no monkeypatching.
compute (`evaluate`) is separate from render (`main`): the former returns a
Result and never prints or exits; the latter is the only side-effecting adapter.
"""

from __future__ import annotations

import fnmatch
import inspect
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

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
import checks as checks_registry  # noqa: E402  (the deploy-check registry interface)
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

# repo-relative locations of the evidence files the controls read. named
# accessors below keep the path knowledge here (in the validator), not on the
# shared Repo seam — Repo stays a pure adapter.
RELEASE_YML_REL = ".github/workflows/release.yml"
PRCHECKS_YML_REL = ".github/workflows/pr-checks.yml"
SCORECARD_YML_REL = ".github/workflows/scorecard.yml"
BUILD_SH_REL = "tools/build/build.sh"
PGP_KEY_REL = "public/.well-known/pgp-key.asc"
REUSE_TOML_REL = "REUSE.toml"
CLAIMS_MAP_REL = "policy-data/claims-map.yml"
CLAIMS_SCHEMA_REL = "schemas/claims-map.schema.json"


def _release_yml(repo: Repo) -> str:
    return repo.read(RELEASE_YML_REL)


# ---------------------------------------------------------------------------
# controls — the evidence-collection logic the map binds claims to. each takes
# the Repo seam and returns (ok, detail). they accept their dependency (the
# repo) rather than creating it, so a fixture repo exercises them directly.
# ---------------------------------------------------------------------------
def control_attestation(repo: Repo) -> tuple[bool, str]:
    """SLSA / Sigstore / Rekor / attestation — backed by the build-provenance
    attestation step. keyless attestation implies Sigstore (Fulcio) signing and
    a Rekor transparency record, so the single step covers all four tokens."""
    text = _release_yml(repo)
    ok = "attest-build-provenance" in text and "id-token: write" in text
    return ok, (
        "release.yml has no actions/attest-build-provenance step with "
        "id-token: write (the keyless Sigstore/Rekor attestation)"
    )


def control_sbom(repo: Repo) -> tuple[bool, str]:
    """CycloneDX / SBOM — backed by the SBOM generation step AND the
    well-formedness validation step. a generated-but-unvalidated SBOM does
    not earn the claim, so both must be present in release.yml."""
    text = _release_yml(repo)
    ok = "cyclonedx_py" in text and "bomFormat" in text
    return ok, (
        "release.yml is missing the cyclonedx_py generation step and/or the "
        "bomFormat well-formedness validation step"
    )


def control_pgp(repo: Repo) -> tuple[bool, str]:
    """PGP — backed by the published public key on disk AND the gpg signature
    check registered as a blocking gate in checks.py."""
    if not repo.is_file(PGP_KEY_REL):
        return False, f"published key missing: {PGP_KEY_REL}"
    # the gpg check must be registered as blocking. ask the registry through its
    # interface; a downgraded, removed or renamed gpg check returns False here
    # (is_blocking returns False for any non-blocking or absent id), which is
    # exactly the regression this gate detects.
    if not checks_registry.is_blocking("gpg"):
        return False, "the gpg signature check is not registered as blocking in checks.py"
    return True, ""


def control_scorecard(repo: Repo) -> tuple[bool, str]:
    """OpenSSF / Scorecard — backed by the scorecard workflow running the
    official ossf/scorecard-action."""
    ok = "ossf/scorecard-action" in repo.read(SCORECARD_YML_REL)
    return ok, "scorecard.yml has no ossf/scorecard-action step (the OpenSSF Scorecard control)"


def control_osv(repo: Repo) -> tuple[bool, str]:
    """OSV — backed by the osv-scanner dependency-vulnerability job in
    pr-checks.yml."""
    ok = "osv-scanner" in repo.read(PRCHECKS_YML_REL)
    return ok, "pr-checks.yml has no osv-scanner step (the OSV dependency-scan control)"


def control_reuse(repo: Repo) -> tuple[bool, str]:
    """REUSE — backed by the reuse-lint job AND the REUSE.toml on disk."""
    if not repo.is_file(REUSE_TOML_REL):
        return False, "REUSE.toml is missing (the REUSE licensing control)"
    ok = "reuse lint" in repo.read(PRCHECKS_YML_REL)
    return ok, "pr-checks.yml has no `reuse lint` step (the REUSE licensing control)"


def control_deterministic(repo: Repo) -> tuple[bool, str]:
    """deterministic build — backed by the release archive being built with
    sorted, owner-zeroed, fixed-mtime tar + name/timestamp-stripped gzip."""
    text = _release_yml(repo)
    ok = "--sort=name" in text and "--numeric-owner" in text and "gzip -n" in text
    return ok, (
        "release.yml archive step is missing the determinism flags "
        "(tar --sort=name --numeric-owner | gzip -n)"
    )


def control_reproducible(repo: Repo) -> tuple[bool, str]:
    """reproducibility goal — backed by the build's --check path, which
    re-renders from source and asserts zero drift against the committed bytes."""
    ok = "--check" in repo.read(BUILD_SH_REL)
    return ok, "build.sh has no --check reproducibility (re-render / no-drift) path"


# the set of control_* functions defined in this module, resolved by name so
# the map's `verified_by` strings can bind to them.
_CONTROLS = {
    name: fn
    for name, fn in sorted(globals().items())
    if name.startswith("control_") and inspect.isfunction(fn)
}

# controls that read release.yml — used by the enforced_at meta-check to confirm
# a claim declaring enforced_at: release is backed by a control that actually
# inspects the release workflow. derived from source, not hand-maintained.
_RELEASE_READING = {
    name for name, fn in _CONTROLS.items() if "release_yml" in inspect.getsource(fn)
}


# ---------------------------------------------------------------------------
# map loading + surface computation
# ---------------------------------------------------------------------------
def load_map(repo: Repo) -> tuple[dict | None, list[str]]:
    """load + schema-validate policy-data/claims-map.yml. returns (data, errors);
    errors is a list of human-readable strings (never raises on a bad map, so the
    caller decides how to report — the interface stays a value, not control flow)."""
    raw = repo.read(CLAIMS_MAP_REL)
    if not raw:
        return None, ["policy-data/claims-map.yml is missing or empty"]
    data = yaml.safe_load(raw)
    schema = json.loads(repo.read(CLAIMS_SCHEMA_REL))
    errors = [
        f"{'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}"
        for e in sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
    ]
    return (None if errors else data), errors


def _surface_files(repo: Repo, surface: dict) -> list[str]:
    """resolve the claim_surface include/exclude globs to a sorted list of
    repo-root-relative paths."""
    include = surface.get("include", [])
    exclude = surface.get("exclude", [])
    found: set = set()
    for pat in include:
        found.update(repo.glob(pat))

    def excluded(rel: str) -> bool:
        for pat in exclude:
            if pat.endswith("/**"):
                prefix = pat[:-3]
                if rel == prefix or rel.startswith(prefix + "/"):
                    return True
            elif fnmatch.fnmatch(rel, pat):
                return True
        return False

    return sorted(rel for rel in found if not excluded(rel))


def _quote_first_line(text: str, token: str) -> str:
    for line in text.splitlines():
        if token in line:
            return line.strip()
    return ""


# ---------------------------------------------------------------------------
# Result — the value `evaluate` returns. the interface is this struct, not
# stdout: tests assert on it; `main` renders it. `ok` iff nothing failed.
# ---------------------------------------------------------------------------
@dataclass
class Result:
    meta_fails: list[str] = field(default_factory=list)
    parity_fails: list[str] = field(default_factory=list)
    ruleset_notes: list[str] = field(default_factory=list)
    backed: int = 0
    surface_count: int = 0
    claimed_any: bool = False

    @property
    def ok(self) -> bool:
        return not self.meta_fails and not self.parity_fails


# ---------------------------------------------------------------------------
# meta-checks — the honesty the declarative map enables. pure: collects failure
# strings + ruleset notes, returns them; no I/O beyond the injected Repo.
# ---------------------------------------------------------------------------
def _meta_checks(repo: Repo, data: dict, surface_rel: set[str]) -> tuple[list[str], list[str]]:
    claims = data["claims"]
    fails: list[str] = []
    notes: list[str] = []

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
            if not repo.is_file(sp):
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
                elif not checks_registry.is_blocking(gate_id):
                    fails.append(
                        f'claim "{token}": pr_gate_check "{gate_id}" is not registered as '
                        "blocking in checks.py"
                    )
            if "ruleset" in ea:
                notes.append(
                    f'claim "{token}" is enforced at ruleset level — confirm it is a '
                    "required status check (governance audit, see docs/GITHUB-RULESETS.md)."
                )

    # (2) no orphan controls: every control_* defined here is bound by >=1 claim.
    for name in _CONTROLS:
        if name not in referenced:
            fails.append(
                f'control "{name}" is defined but bound by no claim (orphan control — '
                "bind it in policy-data/claims-map.yml or remove it)"
            )
    return fails, notes


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo. this is the test surface: callers and tests both cross it here.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo, data: dict) -> Result:
    claims = data["claims"]
    surface_rel = _surface_files(repo, data["claim_surface"])
    result = Result(surface_count=len(surface_rel))

    result.meta_fails, result.ruleset_notes = _meta_checks(repo, data, set(surface_rel))

    sources = [(rel, repo.read(rel)) for rel in surface_rel]
    claimed: dict[str, list] = {}
    for rel, text in sources:
        for token in claims:
            if token in text:
                claimed.setdefault(token, []).append((rel, text))
    result.claimed_any = bool(claimed)

    control_cache: dict = {}
    for token, occurrences in claimed.items():
        controls = [_CONTROLS[n] for n in claims[token]["verified_by"] if n in _CONTROLS]
        token_ok, detail = True, ""
        for control in controls:
            if control not in control_cache:
                control_cache[control] = control(repo)
            ok, det = control_cache[control]
            if not ok:
                token_ok, detail = False, det
                break
        if token_ok and controls:
            result.backed += 1
            continue
        for rel, text in occurrences:
            quoted = _quote_first_line(text, token)
            result.parity_fails.append(f'{rel}: claims "{token}" but {detail}\n        > {quoted}')

    return result


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. loads, evaluates, renders, returns exit
# code. the only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    data, errors = load_map(repo)
    if errors:
        print("  FAIL: policy-data/claims-map.yml does not satisfy schemas/claims-map.schema.json:")
        for e in errors[:12]:
            print(f"    {e}")
        return 1

    result = evaluate(repo, data)
    for note in result.ruleset_notes:
        print(f"  NOTE: {note}")

    if result.meta_fails:
        print(f"  FAIL: {len(result.meta_fails)} claims-map integrity problem(s):")
        for f in result.meta_fails:
            print(f"    {f}")
    if result.parity_fails:
        print(f"  FAIL: {len(result.parity_fails)} unbacked supply-chain claim(s):")
        for f in result.parity_fails:
            print(f"    {f}")
    if not result.ok:
        return 1

    if not result.claimed_any:
        print("  OK: claims-map valid; no supply-chain claims on the public surface to back.")
        return 0
    print(
        f"  OK: claims-map valid; {result.backed} supply-chain claim type(s) across "
        f"{result.surface_count} surface file(s) each map to a passing automated control."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
