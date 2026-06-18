<!-- GENERATED FILE — do not edit by hand. -->
<!-- Source: policy-data/claims-map.yml · Generator: tools/build/generate_claims_md.py · Drift gate: claims_map_drift (blocking). -->

# Public claims ledger

Every public supply-chain promise this project makes, and the executable control that backs it. This page is generated from `policy-data/claims-map.yml` and held in lock-step with it by the blocking `claims_map_drift` gate — the human view cannot drift from the policy data.

**Policy as data, enforcement as code.** The map declares *what* is claimed and *which* control backs it; `tools/verify/validate_claims_parity.py` decides *whether* each control passes by collecting real evidence — running gpg, parsing `release.yml`, checking files on disk.

## Why no OPA / Conftest / rego / Node

A policy engine evaluates data someone has already collected. Here the hard work *is* the collection — there is little neat JSON to reason over and a great deal of evidence to gather. Rego could not run gpg or parse a workflow file, so it would add a layer without removing any work. The bindings are data (this ledger); the evaluation stays executable Python. See `docs/SECURITY-PIPELINE.md`.

## Claims

| Claim | Public wording | Severity | Stated in | Verified by | Enforced at | Status | Release-blocking | Owner | Last reviewed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `PGP` | The integrity manifest is PGP-signed; the published key and a blocking signature check let anyone verify it. | critical | `README.md`<br>`content/en/pages/security.yml`<br>`content/en/pages/integrity.yml`<br>`content/fr/pages/security.yml`<br>`content/fr/pages/integrity.yml`<br>`docs/PROVENANCE.md` | `control_pgp` | pr-gate | enforced | yes | maintainer | 2026-06-18 |
| `Rekor` | Each signed release is recorded in the Rekor public transparency log. | critical | `README.md`<br>`content/en/pages/security.yml`<br>`content/fr/pages/security.yml`<br>`docs/PROVENANCE.md` | `control_attestation` | release | enforced | yes | maintainer | 2026-06-18 |
| `SLSA` | Releases carry SLSA build-track provenance, keyless-signed via Sigstore with a Rekor transparency record. | critical | `README.md`<br>`content/en/pages/security.yml`<br>`content/fr/pages/security.yml`<br>`docs/PROVENANCE.md` | `control_attestation` | release | enforced | yes | maintainer | 2026-06-18 |
| `Sigstore` | Release artefacts are signed keylessly through Sigstore (Fulcio), no long-lived signing key. | critical | `README.md`<br>`content/en/pages/security.yml`<br>`content/fr/pages/security.yml`<br>`docs/PROVENANCE.md` | `control_attestation` | release | enforced | yes | maintainer | 2026-06-18 |
| `attest` | A build-provenance attestation binds every release artefact to the workflow that produced it. | critical | `README.md`<br>`content/en/pages/security.yml`<br>`content/fr/pages/security.yml`<br>`docs/PROVENANCE.md`<br>`docs/TRUST-AND-VERIFICATION.md` | `control_attestation` | release | enforced | yes | maintainer | 2026-06-18 |
| `CycloneDX` | A CycloneDX SBOM of the build toolchain is generated and validated for well-formedness. | high | `README.md`<br>`content/en/pages/security.yml`<br>`content/fr/pages/security.yml`<br>`docs/SECURITY-PIPELINE.md` | `control_sbom` | release | enforced | yes | maintainer | 2026-06-18 |
| `SBOM` | A software bill of materials accompanies the build and is checked for valid structure before release. | high | `README.md`<br>`content/en/pages/security.yml`<br>`content/fr/pages/security.yml`<br>`docs/SECURITY-PIPELINE.md` | `control_sbom` | release | enforced | yes | maintainer | 2026-06-18 |
| `deterministic` | Release archives are built deterministically — sorted, owner-zeroed tar with name/timestamp-stripped gzip. | high | `README.md`<br>`content/en/pages/integrity.yml`<br>`docs/PROVENANCE.md`<br>`docs/REPRODUCIBILITY.md` | `control_deterministic` | release | enforced | yes | maintainer | 2026-06-18 |
| `OSV` | Dependencies are scanned for known vulnerabilities with osv-scanner on every pull request. | medium | `docs/SECURITY-PIPELINE.md`<br>`docs/ASSURANCE-CASE.md` | `control_osv` | ruleset | enforced | yes | maintainer | 2026-06-18 |
| `OpenSSF` | The project participates in the OpenSSF Scorecard programme and publishes its results. | medium | `README.md`<br>`docs/SECURITY-PIPELINE.md`<br>`docs/PUBLIC-READINESS.md` | `control_scorecard` | pr-gate | enforced | no | maintainer | 2026-06-18 |
| `REUSE` | Licensing follows the REUSE specification, linted on every pull request. | medium | `README.md`<br>`docs/SECURITY-PIPELINE.md` | `control_reuse` | ruleset | enforced | yes | maintainer | 2026-06-18 |
| `Scorecard` | OpenSSF Scorecard runs via the official action and its score is reported, not chased. | medium | `README.md`<br>`docs/SECURITY-PIPELINE.md`<br>`docs/PUBLIC-READINESS.md` | `control_scorecard` | pr-gate | enforced | no | maintainer | 2026-06-18 |
| `reproducib` | Independent, off-machine reproduction of the published bytes is a documented target; the build proves zero on-host drift via --check. | low | `content/en/pages/integrity.yml`<br>`content/en/pages/security.yml`<br>`docs/REPRODUCIBILITY.md`<br>`docs/PROVENANCE.md` | `control_reproducible` | pr-gate | goal | no | maintainer | 2026-06-18 |

## Claim surface

Where the gate looks for claims. The map *describes* claims; it does not decide where the repo may state them — the scanner walks this wider surface, so a claim added to an unlisted public page is still seen and still must be backed.

**Included:**

- `README.md`
- `docs/**/*.md`
- `content/en/pages/**/*.yml`
- `content/fr/pages/**/*.yml`
- `public/en-au/**/*.html`
- `public/fr/**/*.html`
- `docs/pdf/readme.html`

**Excluded:**

- `docs/CLAIMS.md`
- `docs/audits/**`
- `reports/**`
- `_archives/**`

## Manual boundaries

The limits no automated control can close, recorded beside the automated ones so the trust story is honest about its edges.

- **PGP key custody.** The signing key's secrecy is a human responsibility. The gate proves a published key exists and that signatures are checked; it cannot prove the private key has never left trusted custody.
- **GitHub platform trust.** Attestation, Scorecard, OSV and REUSE controls run on GitHub-hosted infrastructure. The claims inherit trust in GitHub's runners and OIDC.
- **SBOM completeness.** The CycloneDX SBOM covers the declared build toolchain. It is validated for well-formedness, not asserted to enumerate every transitive input.
- **Static-analysis limits.** CodeQL runs as GitHub default-setup with no committed repo artefact to check, so it is deliberately NOT bound to a claim token here — binding it would make a future honest CodeQL claim impossible to back. No control promises that static analysis finds every class of defect.
- **OSV / REUSE required-status enforcement.** OSV (sca) and REUSE (reuse) are required status checks on both the protect-main and protect-preprod rulesets, so a pull request cannot merge while either is red. They are enforced at ruleset level (not as a checks.py blocking gate), which is why their enforced_at is `ruleset`.
- **Independent reproducibility.** Off-machine, independent bit-for-bit reproduction is a documented target, not an achieved guarantee. The build proves zero drift on the build host via --check; it does not yet prove a third party reproduces the bytes.

