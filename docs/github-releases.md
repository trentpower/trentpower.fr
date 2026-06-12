# GitHub Releases

Operational guide for cutting a GitHub Release. The trust model is
defined in [github-rulesets.md](github-rulesets.md) § "GitHub Releases
are secondary pointers" and is not repeated here beyond its one rule:
**a Release points to the signed record; it is never the record.**

## When a Release is cut

One Release per public edition, after the promotion merge to `main` has
deployed and the edition's frozen archive exists under
`public/integrity/releases/<edition>/`. Releases are not cut for
maintenance merges that do not produce a new edition.

## Tag

Annotated, SSH-signed locally (the signing key never leaves the local
machine), named `edition/<YYYY-MM-DD>`, pointing at the promotion merge
commit on `main`:

```sh
git tag -s edition/<YYYY-MM-DD> -m "Edition <YYYY-MM-DD>" <merge-commit>
git push origin edition/<YYYY-MM-DD>
```

The `protect-release-tags` ruleset (see github-rulesets.md) restricts
creation, update and deletion of `edition/*` tags to the repository
admin.

## Assets

Attach copies of the canonical artefacts — never rebuilt ones:

| Asset                                | Source                                                                                                         |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| `trentpower.fr-<edition>.tar.gz`     | the frozen archive from `public/integrity/releases/<edition>/`                                                 |
| `trentpower.fr-<edition>.tar.gz.sig` | its detached PGP signature from the same directory                                                             |
| `integrity.json`                     | `public/integrity.json` at the tagged commit                                                                   |
| `integrity.json.sig`                 | `public/integrity.json.sig` at the tagged commit                                                               |
| `VERIFY.md`                          | short verification instructions pointing at the in-archive `verify.sh` and https://trentpower.fr/en-au/verify/ |

## Release body

States, in this order: what the edition is; that the Release is a
secondary pointer; where the canonical record lives (signed manifest,
source mirrors, release archives, public key at
`/.well-known/pgp-key.asc`); and that the signed record wins on any
disagreement.

## Settings

Enable **immutable releases** (Settings → General → Releases) so
published Release assets cannot be silently replaced. This is a
supplementary guard — the PGP signatures are the real tamper evidence.
