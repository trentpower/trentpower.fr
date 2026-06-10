# trentpower.fr

`trentpower.fr` is a static, bilingual, source-verifiable personal publication.

It is generated from local source, published as static files, and accompanied
by signed integrity records, source mirrors, and per-edition release archives so
that each edition can be independently checked.

**Live:** <https://trentpower.fr>
**Source:** <https://github.com/trentpower/trentpower.fr>

> **Why this repository is public:** the site claims to be verifiable — signed
> manifests, source mirrors, release archives. Those claims only mean something
> if the source that produces them can be inspected. The repository is the
> deployment source too: what is deployed is exactly what is committed under
> `public/`. (`public/` history makes the clone heavy — a few GiB — by design.)

> **Reading the docs:** a print-ready editorial edition of the whole
> documentation, readable by technical and non-technical readers alike, is at
> [`README.pdf`](README.pdf). Its source lives in [`docs/pdf/`](docs/pdf/).

---

## Principles

- **Static by default.** HTML, CSS, and vanilla JavaScript. No frameworks,
  bundlers, transpilers, or runtime dependencies.
- **Privacy-first.** No analytics, cookies, advertising identifiers,
  cross-site tracking, or third-party requests on page load. Browser storage
  stays same-origin and is limited to visitor-controlled preferences and the
  offline cache; the storage itself is never sent anywhere.
- **Verifiable.** Every public byte is captured in a SHA-256 manifest, signed
  with PGP, and exposed per-page at `/verify/`.
- **Bilingual authored editions.** `/en-au/` (English) and `/fr/` (French);
  English is the authored record and French is curated by hand. `/` is a
  lightweight language gate.
- **Deterministic build.** `bash tools/build/build.sh` produces byte-identical output
  across consecutive runs on the same machine (modulo PGP signature timestamps);
  independent off-machine reproduction is a stated goal, not yet a claim.
- **No LLM in the release path.** Language models may assist drafting and
  development, but the build → sign → verify → deploy pipeline runs with no AI,
  model, or external API dependency.

## Architecture

The site is built as two static authored trees plus a root language gate:

- `/en-au/`: English authored edition
- `/fr/`: French authored edition
- `/`: lightweight language gate

Content is authored in YAML and rendered through templates into static files;
trust surfaces (integrity manifest, source mirrors, release archives, verify /
integrity / source pages) are regenerated on every build. There is no runtime
CMS, no database, and no analytics.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Repository structure

```text
content/              Authored content (YAML) and the route registry
templates/            JS build inputs (app.template.js, cite.template.js)
styles/               Authored design source CSS (styles.src.css, print.src.css)
tools/                The pipeline, split into responsibility pillars:
  ├── build/          Creates the site (generators, renderers, build.sh, copy/)
  ├── quality/        Stops a bad release (gate.py, lint.py, validate_*)
  ├── verify/         Proves the release is genuine (read-only checks)
  ├── release/        Makes it public (archives, seal, deploy.sh)
  ├── config/         Declared facts (identity, public-exposure, overrides)
  ├── lib/            Shared across pillars (paths.py, checks.py)
  ├── score-ledger/   Local-only live-site audit tool (not a deploy gate)
  └── _retired/       Superseded one-offs, out of the release path
public/               Generated public output, the live web root (tracked)
docs/                 Project documentation
.github/workflows/    Deployment workflow
```

`public/` is intentionally tracked: the deployed bytes are part of the trust
story (they are what the signed `integrity.json` attests to).

## Requirements

- Python 3 and Bash for the build pipeline.
- GnuPG for signing and verification.
- Optional dev tooling (Ruff, ShellCheck, Prettier, Stylelint) for the advisory
  quality checks. Missing local tools skip cleanly; CI installs the full set.

## Build

```sh
python3 tools/build/fetch_licensed_fonts.py   # fresh clone only: restore the
                                              # licensed fonts from the live host,
                                              # verified against integrity.json
bash tools/build/build.sh --check    # build + run the deploy gate, no re-signing
bash tools/build/build.sh            # full signed release build
```

The pipeline sweeps identity / edition / asset-version / CSP values, emits the
bilingual trees and the language gate, generates the service worker, hashes the
tree into `integrity.json`, mirrors source under `/source/`, signs the manifest,
builds per-edition release archives, then runs the gate.

See [docs/BUILD-AND-DEPLOYMENT.md](docs/BUILD-AND-DEPLOYMENT.md).

## Checks

```sh
python3 tools/quality/gate.py --all    # blocking, deploy-gating checks
python3 tools/quality/lint.py          # advisory quality checks
```

The gate is two-tier: `gate.py` runs the **blocking** security and correctness
checks (a failure blocks deploy); `lint.py` runs **advisory** quality checks.
Both draw from the registry in `tools/lib/checks.py`, which combines the
`validate_*` scripts with the inline checks in `tools/quality/inline_checks.py`.

See [docs/GATES-CHECKS-AND-QUALITY.md](docs/GATES-CHECKS-AND-QUALITY.md).

## Editing content

```sh
# Edit authored content (YAML); English regenerates, French is hand-edited
$EDITOR content/en/...           # source for the English edition
$EDITOR content/fr/...           # hand-edited French edition

# Edit JS behaviour: NEVER edit the generated public/*.js directly
$EDITOR templates/app.template.js
$EDITOR templates/cite.template.js

bash tools/build/build.sh        # rebuild; every derived surface updates in lockstep
```

See [docs/CONTENT-MODEL.md](docs/CONTENT-MODEL.md).

## Trust model

Each public edition is backed by:

- `integrity.json`: SHA-256 of every public file
- `integrity.json.sig`: detached PGP signature of the manifest
- a published public key at `/.well-known/pgp-key.asc`
- byte-equal source mirrors under `/source/`
- per-edition signed release archives under `/integrity/releases/<YYYY-MM-DD>/`
- per-page verification records at `/verify/`

Anyone can verify the live manifest in an isolated keyring:

```sh
tmpdir="$(mktemp -d)"; chmod 700 "$tmpdir"; export GNUPGHOME="$tmpdir"
ts=$(date +%s)
curl -fsS "https://trentpower.fr/.well-known/pgp-key.asc?ts=$ts" | gpg --import
curl -fsS "https://trentpower.fr/integrity.json?ts=$ts"     -o integrity.json
curl -fsS "https://trentpower.fr/integrity.json.sig?ts=$ts" -o integrity.json.sig
gpg --verify integrity.json.sig integrity.json
unset GNUPGHOME; rm -rf "$tmpdir" integrity.json integrity.json.sig
```

Expected: `Good signature from "Trent POWER <trent@trentpower.fr>"`, fingerprint
`A729 591B 450D 3F59 3694 98BD 8299 1F25 04AE 0263`.

See [docs/TRUST-AND-VERIFICATION.md](docs/TRUST-AND-VERIFICATION.md).

## Privacy

No cookies, no advertising identifiers, no cross-site tracking, no third-party
requests on page load, no analytics or tracking pixels. Browser storage stays
within the same origin and is limited to visitor-controlled preferences
(language, appearance), first-visit markers, and the service-worker offline
cache; none of it is ever transmitted, and `/local/` enumerates every key the
visitor can clear. A strict Content Security Policy (`default-src 'none'`,
hashed inline JSON-LD only), cross-origin isolation, and HSTS back the posture;
`/.well-known/security.txt` and `/privacy/` make it machine-checkable.

See [docs/SECURITY-AND-PRIVACY.md](docs/SECURITY-AND-PRIVACY.md).

## Deployment

Deployment is static and SFTP-based via GitHub Actions. The runner does **not**
rebuild and **does not hold the PGP key**: it re-verifies `integrity.json.sig`
against the committed public key, uploads exactly the bytes already in `public/`
(a non-deleting two-pass mirror), then runs a post-deploy smoke test.

Secrets are configured in the repository, never committed:
`SFTP_HOST`, `SFTP_USERNAME`, `SFTP_PASSWORD`, `SFTP_REMOTE_PATH`, and (optional)
`SFTP_KNOWN_HOSTS` for SSH host-key pinning.

See [docs/BUILD-AND-DEPLOYMENT.md](docs/BUILD-AND-DEPLOYMENT.md).

## Documentation

Full documentation lives in [`docs/`](docs/README.md):

- [ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [BUILD-AND-DEPLOYMENT.md](docs/BUILD-AND-DEPLOYMENT.md)
- [GATES-CHECKS-AND-QUALITY.md](docs/GATES-CHECKS-AND-QUALITY.md)
- [TRUST-AND-VERIFICATION.md](docs/TRUST-AND-VERIFICATION.md)
- [SECURITY-AND-PRIVACY.md](docs/SECURITY-AND-PRIVACY.md)
- [CONTENT-MODEL.md](docs/CONTENT-MODEL.md)
- [OPERATIONS.md](docs/OPERATIONS.md)
- [INCIDENT-RESPONSE.md](docs/INCIDENT-RESPONSE.md)
- [SCORE-LEDGER.md](docs/SCORE-LEDGER.md)
- [PUBLIC-READINESS.md](docs/PUBLIC-READINESS.md)

## What is intentionally not included

- No frameworks, bundlers, transpilers, or runtime dependencies.
- No analytics, tracking, cookies, or advertising identifiers. (Browser storage
  is limited to visitor-controlled preferences and the offline cache; see
  Privacy.)
- No third-party scripts, fonts, or CDN resources; all assets are same-origin.
- No inline JavaScript or CSS.
- No build-time non-determinism.
- No LLM, AI API, or model dependency anywhere in the release pipeline.

## What is excluded from the repository, and why

- **Licensed typefaces.** The Klim Type Foundry fonts are served live under a
  commercial licence that prohibits redistribution, so they are not in the
  tree. `metadata/repo-exclusions.json` declares each one with the SRI digest
  of the live binary; `tools/build/fetch_licensed_fonts.py` restores them on a
  fresh checkout, verified against the signed `integrity.json`.
- **Private operational surfaces.** Keys, credentials, server configuration,
  and operator working notes never enter git; the policy and its enforcement
  are documented in [docs/PUBLIC-READINESS.md](docs/PUBLIC-READINESS.md).
- **Dependency trees.** `node_modules/` and Python virtualenvs are
  regenerated from the committed manifests, never committed.

## Authorship

Content and code are reviewed manually before publication; no automated
publishing occurs. Full statement: [docs/authorship-statement.md](docs/authorship-statement.md).

## License

Two licences, by kind of material — [NOTICE.md](NOTICE.md) is the map:

- **Code** (tooling, templates, stylesheets, schemas, workflows) — the
  [MIT License](LICENSE).
- **Authored content** (editorial source, published page prose, documentation
  prose) — [CC BY-SA 4.0](LICENSE-CONTENT.md), matching the licence the
  published pages declare. Attribution: Trent Power, trentpower.fr, plus the
  canonical URL of the reused page.

The Klim typefaces are licensed to neither — they are commercially licensed
for serving on trentpower.fr only and are excluded from the tree; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
