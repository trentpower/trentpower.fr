# Secrets and key management

The project's policy for storing, accessing and rotating the few secrets it uses.
The guiding rule: no secret ever enters the repository, and the one signing key
never enters CI.

## What secrets exist

| Secret                  | Where it lives                                                    | Who can access it                               |
| ----------------------- | ----------------------------------------------------------------- | ----------------------------------------------- |
| PGP signing key         | The maintainer's local machine only, passphrase-protected         | Maintainer; next of kin via emergency access    |
| SSH commit-signing key  | The maintainer's local machine only                               | Maintainer                                      |
| SFTP deploy credentials | GitHub Actions environment secrets (`production`/`preproduction`) | The deploy job, only after environment approval |
| GitHub account / token  | Password manager; account protected by hardware 2FA               | Maintainer; next of kin via emergency access    |
| C2PA signing cert + key | The maintainer's local machine only, outside the repo (`$TRENTPOWER_C2PA_DIR`) | Maintainer                       |

There are no application secrets: the published site is static and has no runtime,
no database and no server-side code that holds a credential.

## Storing

- Private keys are generated and kept locally, passphrase-protected. They are not
  committed, not synced, and not uploaded to CI. The `secret-scan` job
  ([pr-checks.yml](../.github/workflows/pr-checks.yml)) walks the whole git history
  and the working tree to enforce this; `.gitignore` is the first line of defence.
- Deploy credentials live only as GitHub Actions **environment** secrets, scoped to
  the `production` and `preproduction` environments
  ([GITHUB-ENVIRONMENTS.md](GITHUB-ENVIRONMENTS.md)). They are never repository-level
  secrets and never appear in workflow files.
- The account recovery material and key passphrases live in a password manager with
  next-of-kin emergency access configured (see [../GOVERNANCE.md](../GOVERNANCE.md),
  Continuity).

## Accessing

- The signing keys are used interactively by the maintainer at build time. GitHub
  verifies signatures against the committed public key but never holds the private
  key (see [ASSURANCE-CASE.md](ASSURANCE-CASE.md): the build service verifies, it
  never signs).
- Environment secrets are released to a job only after the environment's required
  reviewer approves the deployment.

## C2PA signing material

The C2PA Content-Credentials layer ([C2PA.md](C2PA.md)) signs selected media with a
**self-signed** certificate. It is operationally separate from the PGP key.

- **Where it lives.** A self-signed ES256 certificate chain (`chain.pem`) and its
  PKCS#8 private key (`signer.key`) under `$TRENTPOWER_C2PA_DIR` (default
  `~/.config/trentpower/c2pa`, directory mode `0700`, key mode `0600`). It is **never
  committed and never enters CI** — signing happens only on the maintainer's local
  machine, like the PGP key. `.gitignore` and the `secret-scan` history walk are the
  enforcement.
- **Who can access it.** The maintainer only.
- **Backup.** The key is backed up with the other private material in the password
  manager / offline store. Because it is self-signed, a lost key is **not** a
  catastrophe: a new certificate can be generated and assets re-signed (the
  integrity manifest, not C2PA, is the canonical proof).
- **Rotation.** Generate a fresh chain, publish the new certificate fingerprint
  beside the PGP fingerprint, and re-sign assets at the next edition. The old
  fingerprint is recorded so prior credentials stay attributable.
- **If compromised.** A stolen C2PA key can forge a Content Credential, but **not**
  the site-level proof — it cannot alter the PGP-signed `integrity.json`. Response:
  stop signing with it, rotate to a new certificate, and note the change. The
  portable layer degrades to "untrusted"; the canonical layer is unaffected.
- **How it differs from the PGP key.** The PGP key signs the whole publication and
  is the identity anchor; its compromise is severe. The C2PA key signs individual
  files as a *portable convenience* and is self-signed (already "untrusted" to
  verifiers without a trust-listed CA), so its blast radius is much smaller.

## Rotating, revoking, re-keying

- **Routine rotation.** SFTP credentials are rotated on the hosting provider and the
  matching environment secret updated; no repository change is required. The GitHub
  token is rotated from the account and re-stored in the password manager.
- **Key compromise.** A stolen signing key can forge the record, so revocation is
  the priority. The procedure is stated in [ASSURANCE-CASE.md](ASSURANCE-CASE.md),
  Residual risks: revocation and re-keying are announced on the site and in the
  repository, a new key is published at `/.well-known/pgp-key.asc`, and a fresh
  signed edition re-establishes the trust anchor. Superseded keys are recorded so
  prior signatures remain attributable.
- **Cadence.** Keys are rotated on suspicion of compromise and otherwise reviewed at
  least annually; deploy credentials are rotated on any access change.
