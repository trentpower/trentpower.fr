# Governance

trentpower.fr is an authored publication with one maintainer. This
document says plainly how decisions are made, who holds which role, and
what happens if the maintainer is suddenly unavailable.

## Decision model

The maintainer decides. There is no committee, no voting, and no
pretence of either. What keeps this honest is that every decision that
matters is enforced by machinery anyone can inspect: the blocking
release gate, the branch rulesets, the signed integrity record. The
repository's documentation records not just what was decided but what
was deliberately declined (see docs/github-rulesets.md).

## Roles

| Role         | Holder                                                     | Responsibilities                                                                                                                                                                         |
| ------------ | ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Maintainer   | Trent Power ([@trentpower](https://github.com/trentpower)) | Writes and signs everything: content, tooling, releases. Triages issues, responds to security reports (14-day window, SECURITY.md), approves production deploys, holds the signing keys. |
| Contributors | Readers                                                    | Issues for factual errors, broken verification and documentation problems are welcome. Pull requests are generally declined — CONTRIBUTING.md explains why.                              |

[CODEOWNERS](.github/CODEOWNERS) records which surfaces are
trust-critical; it is an audit map, not an approval gate.

## Continuity

If the maintainer dies or is incapacitated:

- Account credentials and the signing key passphrases are stored in a
  password manager with emergency access configured for next of kin,
  alongside instructions referencing this document.
- The published record needs no maintenance to stay verifiable: the
  site's archives, signed manifests and public key are mirrored in the
  public repository, and the frozen release archives are explicitly
  redistributable.
- The licenses guarantee continuation rights to everyone: code is MIT,
  content is CC-BY-SA-4.0. Anyone may fork, republish and verify the
  record without permission.
- Issues and the repository remain operable by next of kin through the
  emergency access above; the domain is on auto-renewal with the same
  access arrangement.

What stops, stops honestly: no new editions will appear, and the signed
record makes that legible — the last edition stays the last edition.
