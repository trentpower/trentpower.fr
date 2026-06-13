# Changelog

The canonical, per-edition log of functional and security-relevant changes is
kept as plain text and published with the site:

- In the repository: [`public/changelog.txt`](public/changelog.txt)
- Live: https://trentpower.fr/changelog.txt

It is newest-first, hand-reviewed before publication, and gated: an edition cannot
ship ahead of its changelog entry (the `changelog_freshness` blocking check). Each
edition is also cut as a signed [GitHub Release](https://github.com/trentpower/trentpower.fr/releases)
with a build-provenance attestation (see [docs/provenance.md](docs/provenance.md)).

Security-relevant modifications are noted in that log and, when a vulnerability is
involved, disclosed through the process in [SECURITY.md](SECURITY.md). This file is
a pointer so there is a single source of truth, not two.
