# C2PA technical spike

A throwaway investigation to answer two gate-zero questions before any C2PA
work is planned at scale:

1. Can the publication's flagship asset (`README.pdf`) carry an **embedded**
   C2PA manifest?
2. Is C2PA signing **byte-deterministic** enough to survive this repo's
   reproducibility model?

Both answers turned out to be **no**. This document records what was tested,
the evidence, and what it means for the plan.

> Status: spike complete. Findings below supersede the asset choices in the
> original C2PA plan. Nothing here is wired into the build.

## Environment

| Item | Value |
| --- | --- |
| Host | Raspberry Pi 5 (BCM2712), `aarch64` Linux — the publication build host |
| Tool | `c2pa-python` 0.36.0 (PyPI wheel), native `c2pa-rs` SDK 0.89.0 |
| `c2patool` CLI | **No `aarch64-linux` prebuilt binary is published** (see below) |
| Test certs | Locally generated ES256 (P-256) and Ed25519 chains, self-signed root |
| Signing | Local, no timestamp authority (`ta_url = NULL`) |

The spike ran in a throwaway venv at `/tmp/c2pa-spike`. No signing material,
no tooling, and no signed asset from the spike were committed.

## Finding 1 — no `c2patool` binary for this host

The GitHub releases for `contentauth/c2pa-rs` ship `c2patool` prebuilt only for:

- `universal-apple-darwin`
- `x86_64-pc-windows-msvc`
- `x86_64-unknown-linux-gnu`

There is **no `aarch64-unknown-linux-gnu` `c2patool`**. The `aarch64` Linux asset
in those releases is the `c2pa` *library*, not the CLI.

Consequences for the plan, which assumes `c2patool` everywhere:

- On this Pi, `c2patool` means either **build from source** (Rust toolchain, not
  currently installed) or **sign in x86_64 CI** (where the prebuilt exists).
- The `c2pa-python` wheel **does** install and run natively on `aarch64`, so the
  Python binding is the path of least resistance for local signing/inspection.

This is an operational fork that belongs to Phase 2 (identity & signing model),
surfaced early: **a `sign_asset.sh` shell wrapper around `c2patool` is not a
given on the build host.** A Python-based signer is the realistic local option.

## Finding 2 — PDF cannot be embedded (flagship asset is not viable)

`README.pdf` was the proposed flagship. The Builder refuses it:

```
PDF  es256 : WRITE-FAIL: Error signing file: Builder does not support application/pdf
```

Note the asymmetry: `application/pdf` **is** in
`Reader.get_supported_mime_types()` (63 types) — c2pa-rs can *read* a C2PA
manifest from a PDF, but the Builder **cannot write/embed one**. So with this
toolchain:

- Embedded C2PA in `README.pdf`: **not possible.**
- A **sidecar / external manifest** for the PDF: **also not viable** with this
  toolchain (re-tested with c2pa-python 0.36.0 / c2pa-rs 0.89.0 when promoting the
  Content Credentials to production). `application/pdf` is absent from the
  Builder's 57 *writable* mime types entirely, so `set_no_embed()` fails the same
  way (`_C2paNotSupported`), and a format-agnostic attempt
  (`application/octet-stream`) is rejected too. There is no PDF write path —
  embedded or detached — until a c2pa-rs release adds a PDF handler.

`README.pdf` stays **excluded**; its provenance is the site-level proof
(hashed + PGP-signed in `integrity.json`). Acceptance criterion "at least
`README.pdf` is signed" is **not achievable** with C2PA on this toolchain — this
is that explanation.

## Finding 2b — an explicit `c2pa.actions` assertion is mandatory under 0.89

When promoting the signed SVGs, validation showed `assertion.action.malformed`
(state `Invalid`) even on a freshly-signed asset. c2pa-rs 0.89 validates the
`c2pa.actions` assertion strictly: if the manifest omits one, the Builder's
auto-generated default is rejected as malformed. `build_manifest.py` now emits an
explicit `c2pa.actions.v2` assertion (`c2pa.created` + an IPTC `digitalSourceType`
derived honestly from the asset's AI posture). After the fix the SVGs validate
`Valid`, with the only remaining status `signingCredential.untrusted` — the
expected self-signed caveat.

### What *can* be embedded

| Format | Embed result | Size (orig → signed) |
| --- | --- | --- |
| PNG (`home-og.png`) | OK | 34,989 → 93,472 (+58 KB) |
| SVG (`architecture.en.svg`) | OK | 6,522 → 24,276 (+18 KB) |
| PDF (`README.pdf`) | **WRITE-FAIL** | — |

Two implications:

- **SVG embeds work** — the authored architecture diagrams
  (`public/images/architecture/*.svg`) are genuine candidates and are more
  defensible than social images.
- **Manifest overhead is large in absolute terms** (~18–58 KB). For tiny
  `og` images (35 KB → 93 KB, +167%) the bloat is significant relative to file
  size, and social platforms strip C2PA on upload anyway — so `og`/social-preview
  images are a poor first target despite the plan listing them.

## Finding 3 — signing is not byte-deterministic (the decisive one)

Signing the **same input twice** never produced identical bytes:

```
PNG  es256  : byte-deterministic=False
SVG  es256  : byte-deterministic=False
PNG  ed25519: byte-deterministic=False   # deterministic-signature algorithm — still differs
```

Switching from ECDSA (random-`k`, expected to differ) to **Ed25519**
(deterministic signatures) did **not** fix it. Root cause, confirmed by
inspecting two signings of the same file:

```
sign #1: active_manifest = urn:c2pa:dfc8effc-...  instance_id = xmp:iid:b0655374-...
sign #2: active_manifest = urn:c2pa:9bfdecc3-...  instance_id = xmp:iid:effb7373-...
```

Every signing **mints a fresh random `urn:c2pa:<uuid>` manifest label and a fresh
`xmp:iid:<uuid>` instance id**. Those bytes are inside the claim that gets
signed, so the signature differs too. This is **structural** — independent of
signature algorithm, and independent of timestamp (we signed with no TSA, and
`signature_info.time` came back `None`). Byte-for-byte reproduction of a C2PA
asset is **not attainable** with this tooling.

### Why this matters here specifically

This repo's reproducibility model (`docs/REPRODUCIBILITY.md`) is a **byte
fixpoint that fails closed**: `build.sh --check` re-renders `public/` from
`content/` and **stops the build** if any committed generated byte does not
rebuild from source. A C2PA-signed asset placed in the reproduced tree would
fail that drift gate on **every** build, because the random UUID can never be
reproduced.

**Therefore C2PA assets cannot be treated as build-reproduced output.** They must
be handled like the assets the repo already excludes from the fixpoint — licensed
fonts (fetched + hash-verified, not rebuilt) and the frozen `index.html`:

- signed **once**, **offline/manual**, committed as opaque blobs;
- **hash-verified** via `integrity.json` (the trust anchor stays intact);
- **registered in a drift-gate / mirror exclusion** so `--check` verifies their
  hash instead of trying to regenerate their bytes;
- `docs/REPRODUCIBILITY.md` gains an explicit carve-out: "C2PA-signed assets are
  verified by hash, not byte-reproduced, because the C2PA manifest embeds a
  per-signing random identifier."

This is the single most important integration constraint and it reshapes the
build-order discussion in the plan: C2PA signing is **not** a build stage that
runs on every `build.sh`. It is an occasional, deliberate, committed act.

## Finding 4 — self-signed identity reads as untrusted

Every signed asset inspected as:

```
validation = Invalid
```

because the spike's self-signed root is in no trust list. Expected, but it
confirms the honesty constraint: a self-signed C2PA credential proves a
**consistent claimed identity bound to our certificate** — not a third-party
**verified** identity. Public verifiers (Content Authenticity Verify) will show
the signer as untrusted unless the certificate is issued under a trust-listed CA.

The site's **PGP key remains the identity anchor.** Recommended honest framing:
publish the C2PA signing certificate fingerprint next to the PGP fingerprint so
the two cross-reference, and never claim "verified identity" the trust list does
not back.

## Public-verifier recognition

Not tested end-to-end in this offline spike. Local `validation = Invalid` (from a
self-signed chain) predicts that public tools will recognise the manifest
structure but mark the **signer untrusted** until a trust-listed certificate is
used. To be confirmed once a real certificate strategy exists (Phase 2).

## Recommendation for Phase 1

1. **Drop `README.pdf` as the flagship.** Embedded PDF is impossible with
   c2pa-rs 0.89. Lead with an **authored SVG diagram**
   (`public/images/architecture/*.svg`) — it embeds cleanly and is a defensible
   "authored asset" claim. Keep PDF as a `future` status pending a proven sidecar
   path.
2. **Tooling = `c2pa-python`, not `c2patool`,** on this `aarch64` host. Any future
   C2PA tool wrappers should call the Python binding. Document the
   build-from-source / CI-x86_64 alternatives in Phase 2 but do not depend on a
   `c2patool` binary that this host cannot install.
3. **Treat C2PA assets as fixpoint-excluded, hash-verified artefacts** (fonts /
   frozen-index pattern). Add them to `integrity.json` and the drift-gate +
   source-mirror exclusions. Add the carve-out paragraph to
   `docs/REPRODUCIBILITY.md`. Signing is a deliberate offline step, **not** a
   per-build stage.
4. **De-scope social/`og` images** from the first asset classes — platforms strip
   the metadata and the relative overhead is high.
5. **Identity is self-signed = "consistent claimed identity," not "verified."**
   Cross-reference the cert fingerprint with the published PGP fingerprint. No
   trust-list claims without a trust-listed certificate.
6. **Validator stays advisory first** (`Tier.ADVISORY` in
   `tools/lib/checks.py`), promote to `Tier.BLOCKING` only after an edition cycle,
   exactly as the plan stages it.

## Reproduce the spike

```sh
python3 -m venv /tmp/c2pa-spike/venv
/tmp/c2pa-spike/venv/bin/pip install c2pa-python      # 0.36.0, aarch64 wheel
# ES256 + Ed25519 self-signed chains (KU=digitalSignature, EKU=emailProtection,
#   leaf CA:FALSE, key in PKCS#8 "PRIVATE KEY" form — SEC1 "EC PRIVATE KEY" is rejected)
# sign the same file twice via c2pa.Builder(...).sign_file(); compare sha256
# inspect via c2pa.Reader(mime, stream).json()
```

Gotchas hit during the spike, recorded so they are not rediscovered:

- `C2paSignerInfo.ta_url` is a `c_char_p`; the Python wrapper rejects `None`, so
  construct with a placeholder then set `si.ta_url = None` to sign **without** a
  timestamp authority. Passing `b""` fails at sign time with `Signature: empty
  string`.
- The signing key must be **PKCS#8** (the `BEGIN PRIVATE KEY` PEM label).
  OpenSSL's default EC output is SEC1 (the `BEGIN EC PRIVATE KEY` label) and is
  rejected; convert with `openssl pkcs8 -topk8 -nocrypt`.
- `Reader` has no `from_file`; use `Reader(mime_type, open(path, "rb"))`.
  `is_valid` is a **property**, not a method.
