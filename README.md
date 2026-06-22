# trentpower.fr

[![Signed: PGP](metadata/badges/signed-pgp.svg)](https://trentpower.fr/en-au/verify/)
[![Integrity: SHA-256](metadata/badges/integrity-sha256.svg)](https://trentpower.fr/integrity.json)
[![SLSA: Build L3](metadata/badges/slsa-build-l3.svg)](docs/PROVENANCE.md)
[![OpenSSF: Best Practices](metadata/badges/openssf-best-practices.svg)](https://www.bestpractices.dev/en/projects/13182/gold)
[![OpenSSF Baseline](metadata/badges/openssf-baseline.svg)](https://www.bestpractices.dev/en/projects/13182/baseline-3)
[![Test Coverage: 96%](metadata/badges/coverage.svg)](docs/COVERAGE.md)
[![REUSE: Compliant](metadata/badges/reuse-compliant.svg)](https://api.reuse.software/info/github.com/trentpower/trentpower.fr)

`trentpower.fr` is a static, bilingual, source-verifiable personal publication

It treats a website as a public record: generated from local source, published as static files, signed, archived and made independently checkable

**Live:** [https://trentpower.fr](https://trentpower.fr)
**Source:** [https://github.com/trentpower/trentpower.fr](https://github.com/trentpower/trentpower.fr)

## What this is

This repository contains the source, generated public output, verification records and release machinery for `trentpower.fr`

It is:

- A static personal publication, not a framework app
- Bilingual, with `/en-au/` and `/fr/` authored editions
- Privacy-first, with no analytics, cookies, trackers or third-party page-load requests
- Source-verifiable, with public source mirrors and per-page provenance
- Signed, with a PGP signature over the public integrity manifest
- Editioned, with frozen release archives for each public edition
- Tested, with quality and verification tooling covered by source-derived unit-test metrics

The repository is deliberately public because the site makes verifiability claims. Those claims only mean something if the source, generated files, manifest, signatures, release archives and checks can be inspected

## Why this repository is public

The site does not ask the reader to trust the surface alone

It publishes the record underneath:

- The source used to generate the site
- The generated public files under `public/`
- The SHA-256 manifest for those files
- The detached PGP signature for the manifest
- The source mirrors exposed on the live site
- The release archives attached to each edition
- The checks that guard privacy, integrity, provenance and public claims

`public/` is tracked intentionally. It is the deployed web root and part of the audit trail

This also makes the clone heavier than a normal static-site repository. That is a trade-off made deliberately so the published bytes remain visible in Git history

## What can be verified

Every item below is intended to be checkable, not taken on faith

| Claim                               | How to check                                                         |
| ----------------------------------- | -------------------------------------------------------------------- |
| Published files are recorded        | `public/integrity.json` hashes every public file                     |
| Manifest is signed                  | `public/integrity.json.sig` verifies against the published PGP key   |
| Pages expose their source           | Per-page records and source mirrors are generated during build       |
| Releases are archived               | Frozen edition archives live under `public/integrity/releases/`      |
| Build provenance is available       | Release artefacts include SLSA build-track provenance                |
| SBOM is published                   | Release assets include CycloneDX build-toolchain SBOMs               |
| Licensing is machine-readable       | REUSE 3.3, `REUSE.toml`, `LICENSES/`, `NOTICE.md`                    |
| Privacy claims are checked          | No analytics, cookies, trackers or third-party page-load assets      |
| Public claims are controlled        | `policy-data/claims-map.yml` maps claims to passing controls         |
| Documentation freshness is checked  | Stale paths, stale figures and broken internal links are gated       |
| Coverage figures are source-derived | `sync_coverage.py` keeps badges and docs aligned to measured results |

## Quick proof

Verify the live integrity manifest against the published public key:

```sh
curl -fsS https://trentpower.fr/integrity.json      -o integrity.json
curl -fsS https://trentpower.fr/integrity.json.sig  -o integrity.json.sig
curl -fsS https://trentpower.fr/.well-known/pgp-key.asc | gpg --import
gpg --verify integrity.json.sig integrity.json
```

Expected result:

```text
Good signature from "Trent POWER <trent@trentpower.fr>"
```

Published fingerprint:

```text
A729 591B 450D 3F59 3694 98BD 8299 1F25 04AE 0263
```

For an isolated-keyring verification flow, see [docs/TRUST-AND-VERIFICATION.md](docs/TRUST-AND-VERIFICATION.md)

## What is intentionally not included

The repository excludes anything that would weaken the public record, violate licensing or make the site dependent on opaque runtime services

- No analytics
- No cookies
- No advertising identifiers
- No third-party scripts
- No third-party fonts loaded at runtime
- No CDN page-load dependencies
- No CMS
- No database
- No framework runtime
- No bundled dependency trees
- No private keys
- No credentials
- No server secrets
- No LLM, AI API or model dependency in the release path

Language models may assist drafting or development, but no AI system participates in the build, signing, verification or deployment pipeline

## Licensed fonts

The repository intentionally excludes licensed font binaries

The Klim Type Foundry fonts are served live under a commercial licence that permits use on `trentpower.fr` but does not permit redistribution in this repository

A fresh clone must restore them before full release checks can pass:

```sh
python3 tools/build/fetch_licensed_fonts.py
```

The restore process verifies the downloaded files against the signed public integrity record. Missing fonts in a fresh clone or source archive are expected diagnostics, not corruption

## Check your local environment

Run this first after a fresh clone or extracted source archive:

```sh
make doctor
```

`make doctor` reports whether the local tree can run full, partial, archive-only or blocked checks

It checks:

- Git metadata
- Licensed font presence
- Python dependencies
- Hypothesis
- Node and npm
- `node_modules/`
- GPG
- Whether full release checks are available
- Whether archive-safe checks are available

Source archives do not contain `.git` metadata, so Git-dependent checks cannot prove their claims in archive mode. `make doctor` names those limits clearly instead of failing with stack traces

A future `make bootstrap` command is planned as a companion setup path

## Common commands

```sh
make doctor          # inspect local environment
make test            # run unit tests
make gate            # run blocking release gates
make lint            # run advisory quality checks
make verify          # verify release integrity and signatures
make policy          # check public claims against declared controls
make release-check   # rebuild and check for drift
```

Fresh clone setup:

```sh
python3 tools/build/fetch_licensed_fonts.py
npm install
python3 -m pip install --require-hashes -r .github/requirements/source-quality.txt
```

Build and check:

```sh
bash tools/build/build.sh --check
bash tools/build/build.sh
```

## Build model

The site is generated locally from authored source into `public/`

The pipeline:

1. Reads content, route data and identity configuration
2. Renders the English and French static trees
3. Generates the root language gate
4. Generates source mirrors and per-page provenance records
5. Builds the service worker and static assets
6. Hashes the public tree into `integrity.json`
7. Signs the manifest with PGP
8. Builds per-edition release archives
9. Runs the blocking quality gate

The build is deterministic on the same machine, excluding expected PGP signature timestamp variation. Independent off-machine reproduction is a goal and is documented with its current limits

See [docs/BUILD-AND-DEPLOYMENT.md](docs/BUILD-AND-DEPLOYMENT.md)

## Repository structure

```text
content/              Authored content and route data
templates/            HTML and JavaScript templates
styles/               Authored CSS sources
tools/                Build, quality, verification, release and shared tooling
tools/build/          Site generation, rendering, copying and build ceremony
tools/quality/        Blocking gates, validators, linting and diagnostics
tools/verify/         Read-only verification checks
tools/release/        Release archive and deployment helpers
tools/config/         Declared identity, exposure and policy facts
tools/lib/            Shared primitives, paths, repository and process seams
tools/score-ledger/   Local live-site audit ledger, not a deploy gate
tools/visual/         Visual QA and repository presentation tooling
public/               Generated public output, tracked deliberately
docs/                 Architecture, trust, operations and policy documentation
.github/              Workflows, issue forms, ownership and CI configuration
metadata/             Badges, exclusions and publication metadata
security/             Security artefacts, VEX and related records
```

## Architecture

The site is built as three static surfaces:

- `/en-au/`, English authored edition
- `/fr/`, French authored edition
- `/`, lightweight language gate

Content is authored in YAML and rendered through templates into static HTML. Trust surfaces are regenerated on every build: integrity manifest, source mirrors, release archives, verify pages, source pages and documentation indexes

There is no runtime CMS, no database and no analytics layer

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Editing content

Edit authored content, not generated public output:

```sh
$EDITOR content/en/...
$EDITOR content/fr/...
bash tools/build/build.sh
```

Edit templates and source assets, not generated files:

```sh
$EDITOR templates/...
$EDITOR styles/...
bash tools/build/build.sh
```

Do not hand-edit generated files under `public/` unless the documentation for that surface explicitly says so

See [docs/CONTENT-MODEL.md](docs/CONTENT-MODEL.md)

## Quality and coverage

The quality system is split into blocking and advisory layers

```sh
python3 tools/quality/gate.py --all
python3 tools/quality/lint.py
```

`gate.py` runs deploy-blocking checks for security, integrity, provenance, routes, source mirrors, public exposure and documentation freshness

`lint.py` runs advisory quality checks

The unit-test suite is source-derived and synchronised into badges and documentation. The suite is **1,169** unit-test functions across **77** files — both counts are source-derived and kept in lock-step with the measurement by `sync_coverage.py`. Coverage figures are updated by tooling, not hand-edited

See:

- [docs/GATES-CHECKS-AND-QUALITY.md](docs/GATES-CHECKS-AND-QUALITY.md)
- [docs/COVERAGE.md](docs/COVERAGE.md)

## Trust model

Each public edition is backed by:

- `integrity.json`, SHA-256 record of public files
- `integrity.json.sig`, detached PGP signature
- Published public key at `/.well-known/pgp-key.asc`
- Per-page provenance records
- Byte-equal source mirrors under `/source/`
- Frozen release archives under `/integrity/releases/<edition>/`
- Release provenance and SBOM artefacts
- Claims ledger binding public claims to checks

The system is designed to make public claims inspectable. It does not claim that trust is magic or absolute

It proves:

- The signed manifest verifies against the published public key
- Public files match their recorded hashes
- Generated source mirrors correspond to public pages
- Public claims are tied to declared controls
- Release artefacts have documented provenance where present
- The current edition can be checked through the documented process

It does not prove:

- That a private key has never been compromised
- That GitHub or hosting infrastructure is infallible
- That every historical third-party claim remains true forever
- That independent off-machine bit-for-bit reproduction is fully solved
- That coverage alone proves correctness

See [docs/TRUST-AND-VERIFICATION.md](docs/TRUST-AND-VERIFICATION.md)

## Page provenance

Each generated page includes a quiet provenance record in `<head>`

The record identifies:

- Canonical URL
- Source repository
- Source path
- Source URL
- Edition
- Template path
- Whether the page was generated

The record is injected during build, never hand-pasted. The blocking gate verifies that active pages carry one coherent record, that canonical URLs match real routes, that French pages point to French sources and that no local or private path appears in public bytes

Frozen release snapshots keep their provenance in release metadata rather than being rewritten

## Privacy

The site makes a narrow privacy promise:

- No analytics
- No cookies
- No advertising identifiers
- No cross-site tracking
- No third-party page-load requests
- No tracking pixels
- No data collection form
- No external runtime dependency

Browser storage is same-origin only and limited to visitor-controlled preferences, first-visit markers and the offline cache. `/local/` enumerates the keys a visitor can clear

A strict Content Security Policy, HSTS and security headers support this posture

See [docs/SECURITY-AND-PRIVACY.md](docs/SECURITY-AND-PRIVACY.md)

## Deployment

Production deployment is manual and static

The GitHub Actions runner does not rebuild the site and does not hold the PGP private key. It re-verifies the committed `integrity.json.sig`, uploads the already-committed bytes in `public/`, then runs a post-deploy smoke test

Deployment currently uses SFTP with repository secrets:

```text
SFTP_HOST
SFTP_USERNAME
SFTP_PASSWORD
SFTP_REMOTE_PATH
SFTP_KNOWN_HOSTS
```

`SFTP_KNOWN_HOSTS` is recommended for SSH host-key pinning. Moving production deployment from password-based SFTP to SSH key authentication is a hardening roadmap item. Production should remain manually promoted, not auto-deployed on every push to `main`

See:

- [docs/BUILD-AND-DEPLOYMENT.md](docs/BUILD-AND-DEPLOYMENT.md)
- [docs/SECRETS-AND-KEY-MANAGEMENT.md](docs/SECRETS-AND-KEY-MANAGEMENT.md)

## Documentation

Start with:

- [docs/README.md](docs/README.md), documentation map
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), how the system is shaped
- [docs/TRUST-AND-VERIFICATION.md](docs/TRUST-AND-VERIFICATION.md), how verification works
- [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md), what can be reproduced and how
- [docs/PROVENANCE.md](docs/PROVENANCE.md), release provenance and attestations
- [docs/GATES-CHECKS-AND-QUALITY.md](docs/GATES-CHECKS-AND-QUALITY.md), checks and gates
- [docs/SECURITY-AND-PRIVACY.md](docs/SECURITY-AND-PRIVACY.md), privacy and security posture
- [docs/OPERATIONS.md](docs/OPERATIONS.md), maintainer operations
- [docs/CLAIMS.md](docs/CLAIMS.md), public claims and controls
- [docs/COVERAGE.md](docs/COVERAGE.md), measured test surface

A print-ready editorial documentation edition is available at [README.pdf](README.pdf). Its source lives in [docs/pdf/](docs/pdf/)

## Support and security

The current edition is the supported edition. Earlier editions remain published as frozen archives so the record stays verifiable, but they are not patched

Security-relevant corrections ship as new editions and are noted in the changelog

Report security issues through:

- [SECURITY.md](SECURITY.md)
- `/.well-known/security.txt`

The project commits to coordinated disclosure and a documented response timeframe

## Authorship

This is a single-author publication by Trent Power

Content and code are reviewed manually before publication. No automated publishing occurs, and no AI system participates in the build, signing, verification or deployment path

See [docs/AUTHORSHIP-STATEMENT.md](docs/AUTHORSHIP-STATEMENT.md)

## Citing

The repository is citable as a publication system through [CITATION.cff](CITATION.cff). GitHub's "Cite this repository" button reads it directly

Versions are edition dates and align with the `edition` field of the signed `integrity.json`

## Licensing

Code is licensed under the MIT License. See [LICENSE](LICENSE)

Editorial content, documentation, images and publication text are licensed under CC BY-SA 4.0. See [CONTENT-RIGHTS.md](CONTENT-RIGHTS.md)

Third-party notices are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). [NOTICE.md](NOTICE.md) maps which materials fall under which licence

The Klim typefaces are commercially licensed for serving on `trentpower.fr` only and are excluded from the repository
