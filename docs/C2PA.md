# Content Credentials (C2PA)

How this site uses C2PA, what it is for, and — just as important — what it is
**not** for.

## The one-sentence version

The site already proves the publication. C2PA helps individual media files carry
their own provenance **when they leave the site**.

The publication tree is proven at the site level by a PGP-signed integrity
manifest, SHA-256 hashes, source mirrors, page provenance, release archives, and
build attestations. C2PA does not replace any of that. It adds a **second,
portable layer** so a file — a downloaded diagram, say — still carries a signed
statement of where it came from after it has been copied somewhere this site's
proof cannot reach.

## What C2PA is

C2PA (Coalition for Content Provenance and Authenticity) is an open standard for
attaching a signed **manifest** to a media file. The manifest records assertions
— who published it, a canonical URL, the tool that made it — and is bound to the
file's bytes by a cryptographic signature. Compatible tools (for example the
Content Authenticity _Verify_ page) can read it back and show the provenance.

## How it relates to the existing trust model

| Layer                                | Scope                         | Proof                     |
| ------------------------------------ | ----------------------------- | ------------------------- |
| PGP-signed `integrity.json`          | the whole publication tree    | site-level, canonical     |
| SHA-256 in `integrity.json`          | every public file             | site-level                |
| Release archives, attestations, SBOM | each edition                  | site-level                |
| **C2PA Content Credentials**         | **selected individual files** | **portable, asset-level** |

C2PA is the only layer that survives a file being downloaded and re-shared. It is
**weaker** than the signed manifest in one sense — any platform can strip it —
and **more portable** in another. The two are complements, not competitors. A
C2PA-signed asset is **still listed in the signed integrity manifest**; the
portable layer never leaves the canonical one behind.

## What is in scope

The asset policy is declared as data in
[`../policy-data/c2pa-assets.yml`](../policy-data/c2pa-assets.yml) and checked by
`tools/quality/validate_c2pa_assets.py`. Each asset carries a `status`:

- `required` — must be signed, listed in the manifest, and carry a credential.
- `optional` — signed where practical.
- `future` — declared and intended, **not yet signed**.
- `excluded` — deliberately out of scope, with a recorded reason.

The first intended asset class is **authored diagrams** (the architecture SVGs),
which embed cleanly. The flagship document (`README.pdf`) is **excluded**: the
current C2PA tooling cannot embed a manifest into a PDF (see the spike, below).
Open-graph / social-preview images are excluded because platforms strip the
metadata on upload.

## How AI involvement is declared

Every in-scope asset declares one value from a controlled vocabulary
(`ai_vocabulary` in the policy): `none`, `drafting-assisted`, `editing-assisted`,
`image-generated`, `image-edited`, `unknown`, `not-applicable`, or the
repo-specific `no-ai-in-release-path`.

`no-ai-in-release-path` means: AI may assist drafting or development, but **no AI
system participates in the build, signing, verification, or deployment** of the
asset. It is a claim about the _release path_, not a claim that no AI was ever
involved in the underlying work.

## What C2PA here proves

- The asset was **published by trentpower.fr** under the declared certificate.
- The asset matches a **declared canonical URL**.
- The asset's **declared AI-involvement** value, as recorded in the manifest.
- The asset is **listed in the site's signed integrity manifest**.

## What C2PA here does **not** prove

- It does **not** prove the content is true, real, or unmanipulated.
- It does **not** prove human authorship.
- It does **not** prove AI was never used.
- It does **not**, on its own, prove a **third-party-verified identity**. The
  signing certificate is self-asserted unless and until it is issued under a
  trust-listed certificate authority. Public verifiers will show the signer as
  _untrusted_ in that case. The site's **PGP key remains the identity anchor**;
  the C2PA certificate fingerprint is published alongside it so the two
  cross-reference.

## How to verify a C2PA asset

1. Download the asset.
2. Open a C2PA inspector (e.g. the Content Authenticity _Verify_ page) and load
   the file, **or** run `c2patool <file>` locally.
3. Read the manifest: publisher, canonical URL, AI-involvement.
4. Confirm the same file is listed, by hash, in the site's `integrity.json`.

## If the Content Credentials are missing or stripped

This is expected on some paths — many platforms remove C2PA on upload, and some
editing tools drop it. **The site-level proof is canonical.** If a file you have
lost its credentials, re-download it from the site and verify it against
`integrity.json`. A stripped credential means the portable layer was removed; it
does **not** weaken the signed manifest.

## Reproducibility note

C2PA signing embeds a fresh random manifest identifier each time, so a signed
asset is **not byte-reproducible** across rebuilds. Signed assets are therefore
treated like licensed fonts: signed once, committed, and **verified by hash**
rather than re-generated by the build. See the carve-out in
[REPRODUCIBILITY.md](REPRODUCIBILITY.md).

## Background

The feasibility investigation that set these decisions — tooling, formats,
determinism, identity — is recorded in [C2PA-SPIKE.md](C2PA-SPIKE.md).
