# tools/c2pa — Content Credentials signing toolkit

Local-only tooling to sign selected media with C2PA Content Credentials and read
them back. C2PA is the **portable** provenance layer; the PGP-signed
`integrity.json` remains the canonical site-level proof. See
[docs/C2PA.md](../../docs/C2PA.md) for the policy and
[docs/C2PA-SPIKE.md](../../docs/C2PA-SPIKE.md) for why the design is shaped this way.

## Model

- **Signing is local-only.** The build host is `aarch64`, where no `c2patool`
  binary ships, so signing uses the `c2pa-python` binding, not the CLI.
- **Private material lives outside the repo** under `$TRENTPOWER_C2PA_DIR`
  (default `~/.config/trentpower/c2pa`): a self-signed ES256 `chain.pem` and a
  PKCS#8 `signer.key`. Never committed, never in CI
  ([docs/SECRETS-AND-KEY-MANAGEMENT.md](../../docs/SECRETS-AND-KEY-MANAGEMENT.md)).
- **Self-signed identity.** Credentials bind a *consistent claimed* identity, not a
  trust-listed one; public verifiers show the signer as untrusted. The certificate
  fingerprint is published beside the PGP fingerprint.
- **Not a per-build stage.** Signing is a deliberate, occasional, committed act.
  Signed assets are hash-verified through `integrity.json`, not rebuilt by the
  fixpoint (a fresh random manifest UUID per signing makes them non-reproducible).

## Files

- `build_manifest.py` — build the manifest JSON for a declared asset from
  `policy-data/c2pa-assets.yml` + `tools/config/identity_canonical.json`. Pure; no
  c2pa dependency.
- `sign_asset.py` — sign one asset with the local credential (c2pa-python).
- `inspect_asset.py` — read a signed asset's manifest (`--json` or human summary).

## Setup (once, on the build host)

```sh
# 1. signing venv (c2pa-python has an aarch64 wheel; pyyaml for the manifest builder)
python3 -m venv ~/.local/share/trentpower/c2pa-venv
~/.local/share/trentpower/c2pa-venv/bin/pip install c2pa-python pyyaml

# 2. self-signed signing certificate, outside the repo (mode 0700 / key 0600)
#    ES256 chain.pem (leaf+root) + PKCS#8 signer.key in ~/.config/trentpower/c2pa
```

## Use

```sh
VENV=~/.local/share/trentpower/c2pa-venv/bin/python

# inspect the planned manifest (no signing, no c2pa needed)
python3 tools/c2pa/build_manifest.py public/images/architecture/architecture.en.svg

# sign to a scratch path (default writes <name>.signed<ext> beside the source)
$VENV tools/c2pa/sign_asset.py public/images/architecture/architecture.en.svg --out /tmp/arch.signed.svg

# read it back
$VENV tools/c2pa/inspect_asset.py /tmp/arch.signed.svg
```

Promoting a signed file into `public/` (and into `integrity.json`) is a separate,
deliberate publication step — it is not done by these tools.
