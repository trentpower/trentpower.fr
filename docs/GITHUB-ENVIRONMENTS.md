# GitHub environments

How the GitHub side of the publication pipeline is governed: which
branches exist, which environments hold which secrets, and where the
trust boundary sits. The companion document is
[GITHUB-RULESETS.md](GITHUB-RULESETS.md).

## The one-line trust boundary

**GitHub verifies and deploys. It never signs.** Signing happens locally
during the build ceremony; the runners hold only the committed public
key (`public/.well-known/pgp-key.asc`) and verify `integrity.json.sig`
in an isolated keyring before any byte is mirrored (see the
"Verify integrity.json signature" step in
[`deploy.yml`](../.github/workflows/deploy.yml)). The PGP private key,
and any other signing material, must never be stored in GitHub — not as
a secret, not as a variable, not in any branch.

## Branches

| Branch      | Role                                                                                            |
| ----------- | ----------------------------------------------------------------------------------------------- |
| `feature/*` | Working branches. Never deployed.                                                               |
| `preprod`   | Release candidate. Push triggers verification only; the staging mirror is a manual dispatch.    |
| `main`      | The public production record. Push triggers verification only; publishing is a manual dispatch. |

## Environments

Two GitHub environments, two strictly separated secret sets:

### `production`

| Setting            | Value                                                                                 |
| ------------------ | ------------------------------------------------------------------------------------- |
| Deployment branch  | `main` only                                                                           |
| Required reviewers | Trent (@trentpower) — approval gates every deploy                                     |
| Secrets            | `SFTP_HOST`, `SFTP_USERNAME`, `SFTP_PASSWORD`, `SFTP_REMOTE_PATH`, `SFTP_KNOWN_HOSTS` |
| Used by            | [`deploy.yml`](../.github/workflows/deploy.yml)                                       |

The job waits for the reviewer's approval before any environment secret
is released to the runner. Approve pending deployments under
Actions → the queued run → Review deployments.

### `preproduction`

| Setting            | Value                                                                                                                         |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| Deployment branch  | `preprod` only                                                                                                                |
| Required reviewers | Optional                                                                                                                      |
| Secrets            | `SFTP_PREPROD_HOST`, `SFTP_PREPROD_USERNAME`, `SFTP_PREPROD_PASSWORD`, `SFTP_PREPROD_REMOTE_PATH`, `SFTP_PREPROD_KNOWN_HOSTS` |
| Variables          | `PREPROD_BASE_URL` (staging smoke-test base)                                                                                  |
| Used by            | [`preprod-deploy.yml`](../.github/workflows/preprod-deploy.yml)                                                               |

Until staging credentials exist the preprod workflow verifies only and
skips the mirror — verification still proves the release candidate.

Production secrets belong only to the `production` environment;
preproduction secrets belong only to `preproduction`. Never use
repo-level secrets or variables for deploy credentials — environment
scoping is what keeps a feature-branch workflow from ever reading them.

## Process

```
feature/* ──pull request──▶ preprod ──push──▶ verify (CHECK only)
                               │                  └─ manual dispatch ──▶ staging mirror
                               │  review
                               ▼
                          pull request
                               │
                               ▼
                             main ──push──▶ verify (CHECK only)
                                              └─ manual dispatch + approval ──▶ production deploy
```

1. Work happens on a `feature/*` branch.
2. Pull request into `preprod`. The required checks
   (`release-gate`, `secret-scan` from
   [`pr-checks.yml`](../.github/workflows/pr-checks.yml)) must pass.
3. Merge **verifies** the candidate (the `verify` job). It does not
   mirror. To preview the candidate on staging, trigger the **Deploy
   preprod** workflow by hand (`workflow_dispatch`, `confirm=DEPLOY`)
   once staging credentials exist.
4. Pull request from `preprod` to `main` — the promotion. Same bytes,
   no rebase, no rebuild. The fuller
   [`publication-check.yml`](../.github/workflows/publication-check.yml)
   suite also runs on this PR.
5. Merge to `main` **verifies only — it does not publish.** To publish,
   trigger the **Deploy to Gandi SFTP** workflow by hand
   (`workflow_dispatch`, `confirm=DEPLOY`); the `production` environment
   then **waits for the required reviewer's approval** before any secret
   is released.
6. That manual deploy re-verifies the signed manifest, mirrors `public/`,
   and smoke-tests the live site.

## What is manual, what is in files

| Concern                                                       | Where it lives                                                                |
| ------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Workflow logic, triggers, permissions                         | `.github/workflows/*.yml` (in the repository)                                 |
| Environment existence, branch restriction, reviewers, secrets | GitHub UI — Settings → Environments (manual; not representable in repo files) |
| Branch protection                                             | Rulesets — see [GITHUB-RULESETS.md](GITHUB-RULESETS.md) (manual)              |

When recreating the repository, apply the environment settings above by
hand; the workflows fail closed (no secrets → verification only) until
they are in place.
