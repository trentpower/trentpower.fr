# GitHub rulesets

How the branches that carry the public record are protected. Rulesets
are GitHub UI state (Settings → Rules → Rulesets) — they cannot be
expressed in repository files, so this document is the reference for
applying or restoring them. The companion document is
[GITHUB-ENVIRONMENTS.md](GITHUB-ENVIRONMENTS.md).

## `protect-main-as-public-record`

`main` is the public production record. Nothing rewrites it — not the
maintainer, not automation.

| Rule                                           | Setting                                                                 |
| ---------------------------------------------- | ----------------------------------------------------------------------- |
| Target                                         | `main`                                                                  |
| Require a pull request before merging          | On (approvals: 0 — see note below; stale approvals dismissed on push)   |
| Require status checks to pass                  | On — `release-gate`, `secret-scan`, `release-readiness`, `sca`, `reuse` |
| Require signed commits                         | On                                                                      |
| Require linear history                         | On                                                                      |
| Require conversation resolution before merging | On                                                                      |
| Block force pushes                             | On                                                                      |
| Restrict deletions                             | On                                                                      |

**`release-readiness` is the single readiness gate.** It is one
aggregation job in `publication-check.yml` that `needs:` the three
blocking publication jobs (`release-gate-main`, `build-check`,
`signature-verify`) and emits `Release readiness: PASS` / `FAIL`. Those
three are therefore required **transitively** — they no longer need to be
listed individually, and are not. The production deploy mirrors this gate:
`deploy.yml`'s `readiness` job re-runs the same `validate_release.py` on
the merge commit and the `deploy` job `needs: [guard, readiness]`, so a
FAIL fails the deploy closed before any secret is released. A release is
"ready" iff `release-readiness` is green.

`sca` (osv-scanner) and `reuse` are also required: a real CVE or a
licensing-metadata gap must block a promotion, not merely warn.

**Order matters** when adding new required checks: merge the workflow to
`main` first, let the job run green once on a promotion PR, make it
required afterwards — requiring a check that does not exist yet would
deadlock the very PR that introduces it. The job-id strings above are
load-bearing: renaming a job silently drops its protection until the
ruleset is updated to match.

Required code-owner review stays **off**: this is a single-maintainer
repository and GitHub does not count self-approval, so enabling it would
deadlock every PR. [`CODEOWNERS`](../.github/CODEOWNERS) remains in
place as a routing and audit record of the trust surfaces.

**Required approvals stay at 0, deliberately.** The same single-maintainer
deadlock applies: requiring one approval would force every merge through
the admin bypass, which makes the configuration _look_ stricter while
every actual merge skips it — the appearance of review without the
substance. The Scorecard readings below follow from this and are
accepted. Revisit if a second trusted reviewer ever joins the project.

## `protect-preprod-as-release-candidate`

| Rule                                           | Setting                            |
| ---------------------------------------------- | ---------------------------------- |
| Target                                         | `preprod`                          |
| Require a pull request before merging          | On (approvals: 0)                  |
| Require status checks to pass                  | On — `release-gate`, `secret-scan` |
| Require signed commits                         | On                                 |
| Require conversation resolution before merging | On                                 |
| Block force pushes                             | On                                 |
| Restrict deletions                             | On                                 |

This ruleset carries a repository-role bypass set to **always** so the
maintainer can push integrations and promotions straight to `preprod`
without a PR.

`preprod` is **disposable by design.** The repository setting
"Automatically delete head branches" stays **on**, so merging the
`preprod → main` promotion PR (whose head is `preprod`) deletes the
branch — exactly as it cleans up every merged `feature/*` branch. The
branch is then resurrected automatically: the
[`recreate-preprod.yml`](../.github/workflows/recreate-preprod.yml)
workflow runs on every push to `main` and, **only if `preprod` is
missing**, recreates it at the current `main` commit. It never resets an
existing `preprod`, so a hotfix or any other push to `main` can never
wipe unpromoted work. Net: autodelete keeps the branch list clean, and
`preprod` reappears after each promotion with no manual step.

## `protect-release-tags`

Edition tags are part of the publication model: a signed `edition/YYYY-MM-DD`
tag triggers [`release.yml`](../.github/workflows/release.yml), which builds
the archive, generates and validates the CycloneDX SBOM, attests build
provenance (SLSA/Sigstore/Rekor) and publishes the GitHub Release. This
ruleset keeps those tags admin-only and immutable.

| Rule               | Setting                    |
| ------------------ | -------------------------- |
| Target             | Tags matching `edition/*`  |
| Restrict creations | On — repository admin only |
| Restrict updates   | On                         |
| Restrict deletions | On                         |

## GitHub Releases are secondary pointers

The trust source for any edition is the signed record in the
repository and on the live site: `public/integrity.json` +
`public/integrity.json.sig`, verified against
`public/.well-known/pgp-key.asc`, and the frozen per-edition archives
under `public/integrity/releases/<edition>/` with their own
redistributable manifests and signatures.

A GitHub Release, if one is ever published for an edition, is a
convenience pointer **to** that record — it may link to the archive,
the manifest and the signature, but it is never the canonical artefact.
Never attach rebuilt binaries to a Release; never treat Release assets
as a verification source. If a Release and the signed record ever
disagree, the signed record wins.

## Commit attribution

History is **not** rewritten to fix attribution — the public record
stays byte-stable, and the signed `build.json` pins the commit hash of
the sealing build. The development history that preceded the public
opening was never pushed and is not part of the public record.

Attribution is fixed forward instead:

- Commits are authored `Trent Power <trent@trentpower.fr>` — in every
  clone: `git config user.name "Trent Power"` and
  `git config user.email trent@trentpower.fr`.
- That address is added and verified on the @trentpower GitHub account
  (Settings → Emails), which links all commits — past and future — to
  the profile.
- The SSH signing key (`git_signing_ed25519.pub`) is registered on the
  account as a **signing key** (Settings → SSH and GPG keys → New SSH
  key → key type "Signing Key") so signed commits display as Verified.

## Security automation

The repository's security stack is deliberately small and GitHub-native:

| Tool                              | Status                                                                | Role                                                                                                                                                                                                                                                                                                                                        |
| --------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CodeQL (default setup)            | On                                                                    | Static analysis on PRs; its check blocks merges on its own                                                                                                                                                                                                                                                                                  |
| Secret scanning + push protection | On                                                                    | Blocks committed credentials at push time                                                                                                                                                                                                                                                                                                   |
| Private vulnerability reporting   | On (manual setting)                                                   | The private channel SECURITY.md and the issue forms point to                                                                                                                                                                                                                                                                                |
| Dependabot                        | On — weekly, npm 3 / pip 5 / actions 2                                | Update PRs for review; nothing merges automatically. The pip ecosystem also regenerates the hash-pinned CI sets in [`.github/requirements/`](../.github/requirements/README.md)                                                                                                                                                             |
| OpenSSF Scorecard                 | On — [`scorecard.yml`](../.github/workflows/scorecard.yml)            | Repository-posture checks (branch protection, pinned actions, token permissions) published to the Security tab. A check, not a badge                                                                                                                                                                                                        |
| osv-scanner (`sca` job)           | On — required — [`pr-checks.yml`](../.github/workflows/pr-checks.yml) | Dependency vulnerability scan (OSV.dev) over the pinned Python + Node manifests on every PR; fail-closed and a **required** check on `main`. False positives are not silenced ad hoc: each suppression lives in `osv-scanner.toml`, tied to a statement in `security/openvex.json`, so a real CVE blocks while a triaged advisory does not. |
| REUSE (`reuse` job)               | On — required — [`pr-checks.yml`](../.github/workflows/pr-checks.yml) | `reuse lint` over [`REUSE.toml`](../REUSE.toml) + [`LICENSES/`](../LICENSES); a **required** check on `main`. Every file must carry a resolvable licence, so the public "REUSE: Compliant" claim stays earned.                                                                                                                              |

### Scorecard readings that are accepted, not fixed

The Scorecard badge is a maintenance dashboard, not a medal. Four checks read low
by structural fact rather than by gap, and the corresponding code-scanning alerts
are dismissed in the Security tab as "won't fix" citing this section. The score is
capped at roughly 7-8 for a single-maintainer project; that is expected and honest.

- **Maintained** — Scorecard scores any repository younger than 90
  days as 0 regardless of activity. This repository became public on
  2026-06-10; the check normalises on its own from September 2026 given
  the existing weekly cadence (Dependabot, Scorecard cron, editions).
- **Code-Review** — the check counts approving reviews on merged
  changesets, and a single maintainer cannot approve their own pull
  requests. See the approvals note under `protect-main-as-public-record`.
- **Branch-Protection** — the check is capped because required approvals
  are 0 (a single maintainer cannot require a non-author review without
  deadlocking every merge). The protections that do not need a second
  human are all on: required status checks, signed commits, linear
  history, no force-push, no deletion, no bypass actors. Same root cause
  as Code-Review.
- **Fuzzing** — the check recognises property-based testing for
  several languages but not Python's Hypothesis, which is what this
  repository uses ([FUZZING.md](FUZZING.md)). The property tests run on
  every PR regardless.

Code-Review and Branch-Protection both lift the day a second trusted reviewer
joins and required reviews are turned on — the same change that would satisfy
Baseline `OSPS-QA-07.01` and the Gold two-person-review criteria.

`protect-main` carries **no bypass actors**: even the repository admin
goes through the PR flow. Emergencies are handled by editing the ruleset
itself — a deliberate, auditable act rather than a standing exemption.
The preprod and tag rulesets keep the admin bypass: preprod must be
recreatable from `main` after each promotion, and `edition/*` tags must
be creatable by the admin at release time.

**Later, deliberately:** StepSecurity Harden-Runner — runtime monitoring
of Actions runners (network egress, file integrity, process activity).
Worth adding because the deploy workflow holds SFTP credentials, but
only once the deploy workflow is stable, and in **audit mode first**,
never blocking initially. Preconditions already met: actions SHA-pinned,
environments scoped, production deploy requires approval, SFTP
known_hosts pinned.

**Declined, on the record:** Renovate (duplicates Dependabot here),
stale bots (auto-closing issues has no place in a publication record),
All Contributors (authored publication, not a community package),
Mergify (no merge volume; GitHub has a native merge queue if ever
needed), Codecov (no coverage-worthy test suite), Snyk (another external
surface; GitHub-native tooling suffices).

## Manual settings checklist

All of the following live in the GitHub UI and must be applied by hand:

1. Settings → Rules → Rulesets: the three rulesets above. On
   `protect-main-as-public-record` the required status checks are
   `release-gate`, `secret-scan`, `release-readiness`, `sca`, `reuse`
   (apply each only after it has run green once on a promotion PR).
2. Settings → Environments: per [GITHUB-ENVIRONMENTS.md](GITHUB-ENVIRONMENTS.md).
3. Settings → Code security: enable **Private vulnerability reporting**
   (SECURITY.md and the issue templates point reporters at it).
4. Settings → Emails: verify `trent@trentpower.fr`.
5. Settings → SSH and GPG keys: add the signing key as a Signing Key.
6. Settings → General → Social preview: upload
   `metadata/social-preview/trentpower-fr-github-social.png`.
7. Settings → General: leave "Automatically delete head branches" **on**
   — merged `feature/*` PR branches auto-clean, and `preprod` is deleted
   on promotion then auto-recreated by
   [`recreate-preprod.yml`](../.github/workflows/recreate-preprod.yml)
   (no manual step). Confirm Settings → Actions → General → Workflow
   permissions allows that workflow to create the branch (it requests
   `contents: write` at the job level).
