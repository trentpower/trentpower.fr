# Security pipeline

How the build, gate, and release machinery keeps a public deployment honest.
This is a map of the controls; each links to its authoritative document.

## Controls

| Control                       | What it enforces                                                              | Where                                                  |
| ----------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------ |
| Two-tier gate                 | Blocking security + correctness checks; advisory quality lint never blocks.    | [GATES-CHECKS-AND-QUALITY.md](GATES-CHECKS-AND-QUALITY.md) |
| Release readiness             | One PASS/FAIL gate aggregating the blocking checks; production deploy depends on it. | [GITHUB-RULESETS.md](GITHUB-RULESETS.md)         |
| Privacy / storage keys        | No analytics/cookies/third-party runtime; only allowlisted browser-storage keys ship. | [SECURITY-AND-PRIVACY.md](SECURITY-AND-PRIVACY.md) |
| Integrity manifest            | SHA-256 of every published file; freshness gated against the live tree.        | [TRUST-AND-VERIFICATION.md](TRUST-AND-VERIFICATION.md) |
| PGP signature                 | Author signature over `integrity.json`; verified in a clean keyring in CI.     | [PROVENANCE.md](PROVENANCE.md)                         |
| SLSA L3 provenance            | Runner-built archive attested keyless via Sigstore, recorded in Rekor.         | [PROVENANCE.md](PROVENANCE.md)                         |
| CycloneDX SBOM                | Per-release SBOM of the build toolchain; generated, validated, attested.        | `.github/workflows/release.yml`                        |
| Branch / tag protection       | Linear history, signed commits, required checks, admin-only edition tags.      | [GITHUB-RULESETS.md](GITHUB-RULESETS.md)              |
| Environment approval          | Production deploy waits on a manual reviewer before the push reaches the host.  | [GITHUB-ENVIRONMENTS.md](GITHUB-ENVIRONMENTS.md)     |
| Reproducibility               | Edition re-renders byte-for-byte from source on a clean runner.                | [REPRODUCIBILITY.md](REPRODUCIBILITY.md)             |

## The single readiness gate

Production deployment depends on one clear result, not on a scatter of checks.
`release-readiness` (a job in `publication-check.yml`) aggregates the blocking
publication checks — `release-gate-main`, `secret-scan`, `build-check`,
`signature-verify` — and emits `Release readiness: PASS` or `FAIL`. It is the
single required status check on `main`, and `deploy.yml` mirrors it: a `readiness`
job re-runs `validate_release.py` on the merge commit and the `deploy` job
`needs: [guard, readiness]`, so a FAIL stops the deploy before any secret is
released. A release is "ready" iff this is green. See
[GITHUB-RULESETS.md](GITHUB-RULESETS.md).

## The honesty keystone

The site publishes specific supply-chain claims — SLSA, Sigstore, Rekor, PGP,
SBOM/CycloneDX, OpenSSF Scorecard, OSV, REUSE, deterministic/reproducible build.
The `claims_parity` gate (`tools/verify/validate_claims_parity.py`, registered
blocking in `tools/lib/checks.py`) refuses to ship if any of those words appears
on the public claim surface — the security and verify pages,
[PROVENANCE.md](PROVENANCE.md), and the root `README.md` — without the automated
control that makes it true. (CodeQL is deliberately *not* bound: it runs as
GitHub default setup with no committed artefact to verify, so binding it would
make an honest future claim impossible to back.) It is the prose counterpart to
`validate_signing_status.py`, which checks each public *file* against its
declared signing class. Together they keep the website, repository,
documentation, and pipeline saying the same thing.

## What these controls do and do not prove

They prove **release integrity and provenance**: that a published edition is the
one the author signed, built from the tagged source, with a recorded toolchain.
They do **not** prove the site is impossible to compromise — registrar, hosting,
client-device, and private-key compromise remain out of scope. See the residual
risk section of the security page and [INCIDENT-RESPONSE.md](INCIDENT-RESPONSE.md).

### Known limitations (honest)

- **Reproducibility is same-machine deterministic, not independently proven.** The
  build re-renders byte-for-byte on a clean runner and the archive is byte-stable,
  but no third party has independently reproduced an edition off-machine. Public
  copy says "reproducible build" / "byte-deterministic archives" — a reproducibility
  *goal*, scoped in [REPRODUCIBILITY.md](REPRODUCIBILITY.md), not a claim of
  independent reproduction.
- **PGP key custody is a maintainer responsibility.** The signing key never enters
  CI; its safety is outside the pipeline's reach.
- **Build provenance depends on GitHub's platform guarantees** (OIDC, Sigstore,
  Rekor). It survives without trusting the maintainer's machine, but not without
  trusting the build platform.
- **SBOM completeness depends on the generator and package metadata.** It covers
  the pinned build toolchain (a build-toolchain SBOM), not a runtime dependency
  tree — the static site ships none.
- **Storage-key and contamination gates are static.** They prove no *resolvable*
  undeclared key or third-party marker ships; genuinely dynamic, computed keys
  cannot be statically proven and are skipped (the live score-ledger runtime pass
  is the complementary observed check).
