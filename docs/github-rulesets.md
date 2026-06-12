# GitHub rulesets

How the branches that carry the public record are protected. Rulesets
are GitHub UI state (Settings → Rules → Rulesets) — they cannot be
expressed in repository files, so this document is the reference for
applying or restoring them. The companion document is
[github-environments.md](github-environments.md).

## `protect-main-as-public-record`

`main` is the public production record. Nothing rewrites it — not the
maintainer, not automation.

| Rule | Setting |
| --- | --- |
| Target | `main` |
| Require a pull request before merging | On (approvals: 0 — see note below) |
| Require status checks to pass | On — `release-gate`, `secret-scan` (job names from `pr-checks.yml`) |
| Require signed commits | On |
| Require linear history | On |
| Require conversation resolution before merging | On |
| Block force pushes | On |
| Restrict deletions | On |

Once `publication-check.yml` has run green on a promotion PR, its
blocking jobs (`release-gate-main`, `secret-scan`, `build-check`,
`signature-verify`) can be added to the required checks. **Order
matters:** merge the workflow to `main` first, make its jobs required
afterwards — requiring a check that does not exist yet would deadlock
the very PR that introduces it.

Required code-owner review stays **off**: this is a single-maintainer
repository and GitHub does not count self-approval, so enabling it would
deadlock every PR. [`CODEOWNERS`](../.github/CODEOWNERS) remains in
place as a routing and audit record of the trust surfaces.

## `protect-preprod-as-release-candidate`

| Rule | Setting |
| --- | --- |
| Target | `preprod` |
| Require status checks to pass | On — `release-gate`, `secret-scan` |
| Require signed commits | On |
| Block force pushes | On |
| Restrict deletions | On |
| Require a pull request | Optional (recommended once the cadence settles) |

Note: the repository setting "Automatically delete head branches"
deletes `preprod` after a promotion merge — recreate it from `main`
after each promotion (`git checkout -b preprod main && git push -u
origin preprod`).

## `protect-release-tags`

Apply only if edition tags or GitHub Releases enter the publication
model (they have not yet).

| Rule | Setting |
| --- | --- |
| Target | Tags matching `edition/*` |
| Restrict creations | On — repository admin only |
| Restrict updates | On |
| Restrict deletions | On |

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

## Manual settings checklist

All of the following live in the GitHub UI and must be applied by hand:

1. Settings → Rules → Rulesets: the three rulesets above.
2. Settings → Environments: per [github-environments.md](github-environments.md).
3. Settings → Code security: enable **Private vulnerability reporting**
   (SECURITY.md and the issue templates point reporters at it).
4. Settings → Emails: verify `trent@trentpower.fr`.
5. Settings → SSH and GPG keys: add the signing key as a Signing Key.
6. Settings → General → Social preview: upload
   `metadata/social-preview/trentpower-fr-github-social.png`.
7. Settings → General: leave "Automatically delete head branches" as
   configured, remembering the preprod-recreation note above.
