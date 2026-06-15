# Release

Cutting and publishing an edition. This is a map, not a second copy of the
procedure — the authoritative documents are linked inline.

## The path

| Stage           | What happens                                                                  | Authoritative doc                                      |
| --------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------ |
| Build & sign    | The numbered publication ceremony renders, seals, and PGP-signs the edition.  | [BUILD-AND-DEPLOYMENT.md](BUILD-AND-DEPLOYMENT.md)     |
| Gate            | Blocking security + correctness checks must pass before anything ships.        | [GATES-CHECKS-AND-QUALITY.md](GATES-CHECKS-AND-QUALITY.md) |
| Promote         | `feature/* → preprod → main`, protected branches, required checks.             | [GITHUB-RULESETS.md](GITHUB-RULESETS.md), [GITHUB-ENVIRONMENTS.md](GITHUB-ENVIRONMENTS.md) |
| Tag & attest    | A signed `edition/YYYY-MM-DD` tag triggers SLSA L3 provenance + SBOM.          | [PROVENANCE.md](PROVENANCE.md), [GITHUB-RELEASES.md](GITHUB-RELEASES.md) |
| Deploy          | Push to `main`: the `readiness` gate re-checks, then mirrors to the host after a manual environment approval. | [OPERATIONS.md](OPERATIONS.md) |

## Local commands

Run these before pushing — each is the same command CI runs (see the
[`Makefile`](../Makefile)):

```
make test             # unit + property tests
make gate             # deploy-blocking security + correctness checks
make verify           # full release gate + signature verification
make release-check    # re-render from source and assert no drift
make privacy-check    # storage-key + runtime-contamination + trusted-types gates
make provenance-check # every public supply-chain claim maps to a passing control
make integrity        # regenerate the public integrity manifest
make sbom             # generate a CycloneDX SBOM of the build toolchain
```

`make verify` is the one-shot pre-tag gate: it runs the full blocking gate
(including `make gate`'s checks) plus signature and release-artefact
verification. If it is green locally, the `release-readiness` gate will be green
in CI — they run the same `validate_release.py`.

## What proves what

A reader does not have to trust the host. See
[TRUST-AND-VERIFICATION.md](TRUST-AND-VERIFICATION.md) for the full surface; in
short: `integrity.json` lists the SHA-256 of every published file,
`integrity.json.sig` is the author's PGP signature over that manifest, the SBOM
records the build toolchain, and the GitHub attestation proves which commit and
workflow produced the runner-built archive. Every one of those claims is backed
by an automated check — see [SECURITY-PIPELINE.md](SECURITY-PIPELINE.md).

## Recovering from a failed release

Nothing is published until a gate passes, so a failure is safe — it stops the
pipeline, it does not half-ship.

- **`make verify` red locally** — fix the reported check and re-run; do not tag.
- **A promotion PR's `release-readiness` is red** — open the job's step summary;
  it names which blocking job failed (`release-gate-main`, `secret-scan`,
  `build-check`, `signature-verify`). Fix on the `feature/*` branch and push.
- **A push-to-main `readiness` job fails** — the `deploy` job is skipped and no
  SFTP secret is released; the live site is untouched. Fix and push a corrected
  commit (a non-edition commit leaves the site as-is; the edition guard only
  deploys when the edition advances).
- **The `release.yml` tag build fails** — delete the tag, fix, re-tag. The
  deploy path is separate and is unaffected by a failed attestation build.
