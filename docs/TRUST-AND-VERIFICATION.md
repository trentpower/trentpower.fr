# Trust and verification — trentpower.fr

trentpower.fr is a static, signed publication. Every publishable byte the
live site serves is cryptographically attested and independently
verifiable, without trusting the host, the CDN, or the transport.

This document explains the trust artefacts, how to verify them in a clean
keyring, how the frozen-release archives work, and — explicitly — what the
trust model does and does **not** prove.

> Deploy is automated. A push to the default branch triggers a GitHub
> Actions workflow that transfers `public/` to the host. There is no
> manual SFTP step. The verification procedures below run against the
> **live** site and prove the deployed bytes match what was signed.

---

## Trust artefacts at a glance

| Artefact                | Path                                                                | What it is                                                       |
| ----------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Site-wide manifest      | `/integrity.json`                                                   | SHA-256 of every publishable file                                |
| Manifest signature      | `/integrity.json.sig`                                               | Detached, ASCII-armoured PGP signature over the manifest         |
| Published public key    | `/.well-known/pgp-key.asc`                                          | The signing key, served inline for import                        |
| Source mirrors          | `/source/<live-path>.txt` (and `.base64.txt` for binaries)          | Plain-text copy of every served byte                             |
| Frozen release archives | `/integrity/releases/<YYYY-MM-DD>/`                                 | Immutable per-edition snapshots with their own sums + signatures |
| Verify pages            | `/verify/`, `/source/`, `/integrity/`, `/integrity/verify-locally/` | Human-facing verification surfaces                               |

Key fingerprint: `A729 591B 450D 3F59 3694 98BD 8299 1F25 04AE 0263`
(also recorded in `/.well-known/publication.json` and each release's
`release.json`).

---

## What `integrity.json` + `.sig` prove

`integrity.json` is a JSON manifest mapping every publishable URL path to a
`sha256-<base64>` digest of its bytes. `integrity.json.sig` is a detached
PGP signature over that manifest, produced offline against the published
key.

Together they prove:

- The manifest was produced by the holder of the signing key (authenticity).
- Each served file matches the digest recorded in the manifest (integrity).
- No file was altered in transit or at rest after signing.

The signature is valid only for the **exact** bytes recorded. If any
publicly served file changes, the manifest must be regenerated and
re-signed; a stale manifest fails verification.

---

## Verify the live site in a clean keyring

The procedure below imports the published key into a throwaway keyring so
verification does not depend on any key already trusted on your machine.
A cache-busting `?ts=` query bypasses any CDN/edge cache.

```bash
tmpdir="$(mktemp -d)"
chmod 700 "$tmpdir"
export GNUPGHOME="$tmpdir"

ts=$(date +%s)
curl -fsS "https://trentpower.fr/.well-known/pgp-key.asc?ts=$ts" | gpg --import
curl -fsS "https://trentpower.fr/integrity.json?ts=$ts"     -o integrity.json
curl -fsS "https://trentpower.fr/integrity.json.sig?ts=$ts" -o integrity.json.sig
gpg --verify integrity.json.sig integrity.json

unset GNUPGHOME
rm -rf "$tmpdir" integrity.json integrity.json.sig
```

Expected:

```
Good signature from "Trent POWER <trent@trentpower.fr>"
```

If verification fails, do not trust the bytes you fetched.

> Never sign or verify a production manifest while `GNUPGHOME` is left
> pointing at a temporary directory you intend to reuse — always unset it
> afterward.

---

## Source-mirror comparison

Every publishable byte is mirrored at `/source/` as plain text so the
exact bytes the live site serves can be read and diffed without any
tooling:

- Text files: `/source/<live-path>.txt`
- Binary files: `/source/<live-path>.<ext>.base64.txt`
- Manifest of mirrors: `/source/source-manifest.json`

The completeness rule: **every public file is either mirrored at
`/source/` or excluded with an explicit per-file reason.** This lets a
reader confirm that what they see at `/source/` is the same content
attested by `/integrity.json`, by hashing the mirror and comparing it to
the manifest entry for the live path.

The `/source/` page is the human-facing entry point to these mirrors.

---

## Release-archive trust model

A **release** is a complete, frozen snapshot of the site at a specific
edition. Each edition lives under `/integrity/releases/<YYYY-MM-DD>/` and
carries its own checksums and signatures, independent of the live
site-wide manifest.

### Immutability baseline

Releases are permanent. Once a release directory is signed it must never
be modified. The site-wide `/integrity.json` at the root covers everything
including the release archives, so any post-hoc edit to a frozen release
would break the site-wide signature as well as the per-release one.

If a deterministic rebuild on a later day produces drifting bytes, that is
recorded as a **parallel today-dated rebuild** rather than a mutation of
the canonical archive. `builds.json` indexes the canonical build and any
rebuilds:

```json
{
  "schema": "trentpower.edition-builds.v1",
  "edition": "2026-05-17",
  "canonical":  { "build_date": "2026-05-17", "zip_sha256": "…", "tar_gz_sha256": "…" },
  "rebuilds": [ { "build_date": "2026-05-18", "zip_sha256": "…", "tar_gz_sha256": "…" }, … ]
}
```

### Per-release artefacts

Inside `/integrity/releases/<YYYY-MM-DD>/`:

- `trentpower-fr-<edition>.zip` / `.tar.gz` — the archive bundles, each
  with a `.sha256` and a detached `.sig`.
- `SHA256SUMS` + `SHA256SUMS.sig` — checksums of the archive bundles, signed.
- `release.json` + `release.json.sig` — the trust anchor for the edition
  (schema `trentpower.release.v1`): signing-key fingerprint, manifest
  pointers, reproducibility metadata (`build_command: bash tools/build/build.sh`,
  deterministic byte-for-byte), and an audience map (README / QUICK_VERIFY
  / VERIFY / RELEASE / REPRODUCIBILITY).
- `EXCLUDED_FILES.json` / `.txt` (+ `.sig`) — the per-edition exclusions
  manifest: every public file is either in the archive or excluded with an
  explicit reason.
- `integrity-redistributable.json` (+ `.sig`) — an offline-usable manifest.
  Note: its signature carries random GPG salt, so it is not inlined into
  the archive (that would force the archive bytes to drift on every sign);
  fetch it from its live URL for offline use.
- `verify.sh` — a dependency-free bash script (no python, no jq) that walks
  the extracted archive, compares each file against the exclusions
  manifest, and prints a verification summary.

### Verify a specific release

```bash
EDITION="2026-05-17"
tmpdir="$(mktemp -d)"; chmod 700 "$tmpdir"; export GNUPGHOME="$tmpdir"

ts=$(date +%s)
curl -fsS "https://trentpower.fr/.well-known/pgp-key.asc?ts=$ts" | gpg --import
curl -fsS "https://trentpower.fr/integrity/releases/$EDITION/SHA256SUMS?ts=$ts"     -o SHA256SUMS
curl -fsS "https://trentpower.fr/integrity/releases/$EDITION/SHA256SUMS.sig?ts=$ts" -o SHA256SUMS.sig
gpg --verify SHA256SUMS.sig SHA256SUMS

unset GNUPGHOME
rm -rf "$tmpdir" SHA256SUMS SHA256SUMS.sig
```

You can then download a bundle and confirm its SHA-256 against the entry in
`SHA256SUMS`, and verify the bundle's own detached `.sig` the same way.

The releases listing at `/integrity/releases/` indexes every edition.

---

## Verify / source / integrity pages

- `/verify/` — the verification surface; drives the live, clean-keyring
  check described above for visitors.
- `/source/` — entry point to the plain-text source mirrors.
- `/integrity/` and `/integrity/releases/` — the integrity manifest and the
  frozen-release index.
- `/integrity/verify-locally/` — step-by-step "get to the terminal" guide
  for reproducing verification by hand.

These pages mean the same thing with JavaScript disabled; JS only enhances
the experience.

---

## Subresource Integrity (SRI)

First-party scripts and stylesheets are loaded with SRI hashes so the
browser refuses any asset whose bytes don't match. SRI covers `app.js`,
`cite.js`, and `styles.css`. `print.css` is intentionally SRI-exempt (a
deliberate `media="print"` activation fix). SRI is enforced in addition to
the manifest, giving the browser an independent integrity check at load
time.

---

## Service-worker constraints

A service worker (`/sw.js`) provides offline availability under strict
constraints:

- It is generated and signed; the file header records that it is covered by
  `/integrity.json`.
- The cache name is versioned per edition (e.g.
  `tp-2026-06-10.<hash>-edition-2026-05-17-…`). Bumping the cache name
  forces a fresh activation and discards prior precache state.
- A `CRITICAL_PRECACHE` list of pages and core CSS/JS/manifest/favicon must
  cache on install; failure to cache any of them aborts install, so an
  offline visit can never render an incoherent page.
- The SW runs under a per-file CSP override (`connect-src 'self'`) so its
  precache fetches are permitted, while normal pages keep
  `connect-src 'none'`. The SW never relaxes the page CSP.
- `/sw-reset/` exists to recover from a stale or misbehaving worker.

---

## What the trust model proves — and does NOT prove

**It proves:**

- The served bytes match a manifest signed by the holder of the published
  PGP key.
- No tampering occurred in transit or at rest after signing.
- The published site is cryptographically verifiable end-to-end, against a
  key you can import into a clean keyring.
- Every served byte is mirrored in readable form and accounted for
  (mirrored or explicitly excluded).
- Frozen editions are immutable and independently checkable, with
  reproducible, deterministic builds.

**It does NOT prove:**

- That the signing key belongs to the person you believe it does — that is
  a key-trust question (fingerprint verification out-of-band), not
  something a signature alone establishes.
- That the _content_ is true, accurate, or complete — integrity is about
  bytes, not editorial correctness.
- That the host or CDN cannot serve you a _different_ signed-but-older
  manifest; freshness is your responsibility (hence the cache-busting
  `?ts=` and live-verification step).
- That an attacker who compromised the signing key could not produce valid
  signatures — key custody is the root of trust.
- Anything about third-party behaviour: there are no third-party runtime
  assets to attest (see SECURITY-AND-PRIVACY.md).
