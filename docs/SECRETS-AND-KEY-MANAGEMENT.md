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

There are no application secrets: the published site is static and has no runtime,
no database and no server-side code that holds a credential.

## Storing

- Private keys are generated and kept locally, passphrase-protected. They are not
  committed, not synced, and not uploaded to CI. The `secret-scan` job
  ([pr-checks.yml](../.github/workflows/pr-checks.yml)) walks the whole git history
  and the working tree to enforce this; `.gitignore` is the first line of defence.
- Deploy credentials live only as GitHub Actions **environment** secrets, scoped to
  the `production` and `preproduction` environments
  ([github-environments.md](github-environments.md)). They are never repository-level
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
