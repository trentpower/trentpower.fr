# Release provenance

How a published edition proves which commit and which workflow produced it,
in addition to who signed it.

## Two independent proofs, two questions

| Proof                               | Question it answers                                      | Where                                              |
| ----------------------------------- | -------------------------------------------------------- | -------------------------------------------------- |
| PGP signature over `integrity.json` | Did the author publish this record?                      | Local signing key; verified offline with `gpg`     |
| GitHub build-provenance attestation | Which commit and workflow produced these artefact bytes? | GitHub Actions; keyless Sigstore; public Rekor log |

They are independent. The PGP signature is the editorial trust anchor and
survives without GitHub. The attestation is the supply-chain anchor and survives
without trusting the maintainer's machine for the build-to-artefact link. Neither
replaces the other; the signed `integrity.json` on the site remains canonical.

## What is attested

The workflow [`.github/workflows/release.yml`](../.github/workflows/release.yml)
runs on a signed `edition/YYYY-MM-DD` tag. It does not rebuild the site. It runs
the full blocking gate (`tools/verify/validate_release.py`) against the committed,
already-signed release, then attests the exact published bytes:

- `public/integrity.json`
- `public/integrity/releases/<edition>/trentpower-fr-<edition>.tar.gz`
- `public/integrity/releases/<edition>/trentpower-fr-<edition>.zip`
- `public/integrity/releases/<edition>/SHA256SUMS`

`actions/attest-build-provenance` signs the attestation keyless via GitHub OIDC
(Sigstore Fulcio) and records it in the public Rekor transparency log. The
attestation is stored against the repository and a convenience copy of the
artefacts is attached to the GitHub Release.

## How a third party verifies

Using only the GitHub CLI and standard tools:

```sh
# 1) Build provenance: which commit + workflow produced this artefact
gh attestation verify trentpower-fr-<edition>.tar.gz \
  --repo trentpower/trentpower.fr

# 2) Every file matches the published checksums
sha256sum -c SHA256SUMS

# 3) The author's PGP signature over the manifest (offline, unchanged)
gpg --verify integrity.json.sig integrity.json
```

Step 1 is the new proof. Steps 2 and 3 already worked before provenance existed.

## Honest scope: this is publish provenance, not a hermetic rebuild

The edition is built and PGP-signed locally; GitHub verifies and conveys, it does
not build the canonical record (see [ASSURANCE-CASE.md](ASSURANCE-CASE.md)). The
attestation therefore binds tag, commit, workflow run and artefact digests; it
does not claim the artefacts were compiled inside the runner. That is the
deliberate trade-off of a local-build, local-sign model.

Moving the build into the runner would yield full SLSA build-track Level 3
provenance, but it conflicts with local signing and duplicates the frozen-archive
scheme. Because the build is deterministic and `build-check` already re-renders
byte-for-byte in CI, that upgrade is feasible later: rebuild with
`tools/build/build.sh` in the runner and attest the runner's own output. It is
documented as a future step, not done here, so no claim is made that the
implementation cannot prove.

## Manual prerequisites (one-off, by hand)

1. Merge `release.yml` to `main` first. Tag events run the workflow as it exists
   in the tagged commit, so the file must be on `main` before the first tag.
2. Apply the `protect-release-tags` ruleset: restrict `edition/*` tag creation to
   the repository admin, and restrict updates and deletions. See
   [github-rulesets.md](github-rulesets.md). This is what makes the tag trigger
   trustworthy: only the maintainer can mint a release tag.

## Cutting a release

```sh
git tag -s edition/2026-06-10 -m "Edition 2026-06-10" <commit-on-main>
git push origin edition/2026-06-10
```

The push triggers the workflow: gate, attest, publish Release. Deployment to the
host stays a separate, gated step ([deploy.yml](../.github/workflows/deploy.yml)).

## Optional later: cosign blob signature

`attest-build-provenance` already provides Sigstore + Rekor coverage, so a
separate `cosign sign-blob` over `SHA256SUMS` is optional. It would add an
offline `cosign verify-blob` path at the cost of one more dependency. Left out
on purpose to keep the supply chain small and GitHub-native.
