#!/usr/bin/env python3
"""tools/verify/validate_claims_parity.py — claim-to-control honesty gate.

the public site makes specific supply-chain claims: SLSA build-track
provenance, keyless Sigstore signing, a Rekor transparency record, a
CycloneDX SBOM, and a PGP-signed integrity manifest. this validator
refuses to ship when any of those words is published as a claim but the
automated control that would make the claim true is not present.

it is the prose counterpart to validate_signing_status.py: that gate
checks each public *file* against its declared signing class; this gate
checks each public *claim* against the pipeline control that backs it.

discipline (mirrors validate_signing_status.py): only what is claimed is
enforced. a token absent from the claim surface requires nothing — the
gate never speculates about controls the site does not advertise.
"""

import re
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
from paths import CONTENT_DIR, DOCS_DIR, PUBLIC_DIR, REPO_ROOT  # noqa: E402

# the public claim surface. content/ sources are scanned (not rendered
# public/) so the gate is stable and runs before render. files that do
# not exist are skipped — the surface is allowed to grow or shrink.
CLAIM_SURFACE = [
    CONTENT_DIR / "en" / "pages" / "security.yml",
    CONTENT_DIR / "fr" / "pages" / "security.yml",
    CONTENT_DIR / "en" / "pages" / "verify.yml",
    CONTENT_DIR / "fr" / "pages" / "verify.yml",
    DOCS_DIR / "PROVENANCE.md",
    REPO_ROOT / "README.md",
]

WORKFLOWS = REPO_ROOT / ".github" / "workflows"
RELEASE_WORKFLOW = WORKFLOWS / "release.yml"
PRCHECKS_WORKFLOW = WORKFLOWS / "pr-checks.yml"
SCORECARD_WORKFLOW = WORKFLOWS / "scorecard.yml"
CHECKS_REGISTRY = REPO_ROOT / "tools" / "lib" / "checks.py"
BUILD_SH = REPO_ROOT / "tools" / "build" / "build.sh"
REUSE_TOML = REPO_ROOT / "REUSE.toml"
PGP_KEY = PUBLIC_DIR / ".well-known" / "pgp-key.asc"


def _read(path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _release_yml() -> str:
    return _read(RELEASE_WORKFLOW)


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
    # the gpg check must be registered as blocking (_B). match the
    # Check("gpg", ..., _B, ...) entry tolerant of whitespace/wrapping.
    registered = re.search(r'Check\(\s*"gpg"\s*,.*?,\s*_B\s*,', src, re.DOTALL) is not None
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


# token (as it appears, case-sensitive) -> backing control. several tokens
# share one control because one pipeline step earns several claims at once.
# only tokens with a verifiable committed control are bound: CodeQL is GitHub
# default-setup with no repo artefact to check, so it is deliberately absent —
# binding it would make a future honest CodeQL claim impossible to back.
CONTROLS = {
    "SLSA": control_attestation,
    "Sigstore": control_attestation,
    "Rekor": control_attestation,
    "attest": control_attestation,  # matches attest / attested / attestation
    "CycloneDX": control_sbom,
    "SBOM": control_sbom,
    "PGP": control_pgp,
    "OpenSSF": control_scorecard,
    "Scorecard": control_scorecard,
    "OSV": control_osv,
    "REUSE": control_reuse,
    "deterministic": control_deterministic,
    "reproducib": control_reproducible,  # matches reproducible / reproducibility
}


def _quote_first_line(text: str, token: str) -> str:
    for line in text.splitlines():
        if token in line:
            return line.strip()
    return ""


def main() -> int:
    sources = [(p, p.read_text(encoding="utf-8")) for p in CLAIM_SURFACE if p.is_file()]

    # which tokens are actually claimed anywhere on the surface.
    claimed: dict[str, list] = {}
    for path, text in sources:
        for token in CONTROLS:
            if token in text:
                claimed.setdefault(token, []).append((path, text))

    if not claimed:
        print("  OK: no supply-chain claims on the public surface to back.")
        return 0

    fails: list[str] = []
    backed = 0
    # evaluate each backing control once, then attribute to every token it covers.
    control_cache: dict = {}
    for token, occurrences in claimed.items():
        control = CONTROLS[token]
        if control not in control_cache:
            control_cache[control] = control()
        ok, detail = control_cache[control]
        if ok:
            backed += 1
            continue
        for path, text in occurrences:
            quoted = _quote_first_line(text, token)
            rel = path.relative_to(REPO_ROOT)
            fails.append(f'{rel}: claims "{token}" but {detail}\n        > {quoted}')

    if fails:
        print(f"  FAIL: {len(fails)} unbacked supply-chain claim(s):")
        for f in fails:
            print(f"    {f}")
        return 1

    print(f"  OK: {backed} supply-chain claim type(s) each map to a passing automated control.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
