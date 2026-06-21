# Build and Deployment — trentpower.fr

This is the operator's reference for turning authored source into a
signed, deploy-ready artefact and publishing it to the live host. It contains no credentials — only template
placeholders.

Three concerns are kept strictly separate:

1. **Build** creates the artefact under `public/`. Runs locally on the
   operator's machine. PGP signing happens here. Entry point:
   `bash tools/build/build.sh` — a numbered publication ceremony
   (stages 01–13, plus stage 14 in `--public-release`).
2. **Validation** proves the artefact is safe and correct to ship. The
   deploy-blocking gate (`tools/quality/gate.py`) runs twice inside the
   build: at stage 05 with `--skip-signature`, before any signature
   exists, and in full at stage 08 after signing. Advisory quality lint
   (`tools/quality/lint.py`) runs alongside the stage 05 pass.
3. **Deployment** publishes the artefact. A push to `main` only _verifies_
   it (the workflow re-checks the signed bytes); the SFTP mirror runs ONLY
   when the maintainer triggers the GitHub Actions workflow by hand
   (`workflow_dispatch`) and types the `DEPLOY` confirmation. Stage 11 of
   the build pushes to `main` behind its own typed `DEPLOY` prompt, but that
   push verifies — it no longer ships; publishing is a separate, deliberate
   manual dispatch. Deployment never rebuilds and never signs.

```
┌──────────────┐  tools/build/build.sh   ┌──────────────┐   deploy   ┌──────────────┐
│  authored    │ ────────────────▶ │  artefact    │ ─────────▶ │  live host   │
│  inputs      │  generators +     │  public/     │  SFTP, no  │  Apache /    │
│  (YAML copy, │  gate.py +        │  + signed    │  --delete  │  Varnish     │
│  templates,  │  GPG signing      │  manifest    │            │              │
│  config)     │                   │              │            │              │
└──────────────┘                   └──────────────┘            └──────────────┘
```

---

## Entry point

```sh
bash tools/build/build.sh              # full ceremony: render, seal, verify, sign, archive, gate, ship
bash tools/build/build.sh --check      # stages 01–05 only; no signing, no archives — fast inner loop
bash tools/build/build.sh --no-sign    # full build + verify, but skip signing/archives/deploy (CI without key)
bash tools/build/build.sh --editorial  # also regenerate editorial review exports (md/html/docx/pdf)
bash tools/build/build.sh --public-check    # --check plus the public-readiness gate (secret scan + posture)
bash tools/build/build.sh --public-release  # full ceremony, then stage 14: flip the GitHub repo public
bash tools/build/build.sh --yes-public      # pre-approve stage 14 (or env PUBLIC_RELEASE_APPROVED=1)
bash tools/build/build.sh --no-push    # in the ship ritual, commit only — never push or deploy
bash tools/build/build.sh --plain      # force the plain transcript even on a TTY
bash tools/build/build.sh --ascii      # ascii markers ([ok]/[x]) instead of glyphs
bash tools/build/build.sh --verbose    # echo each underlying command beneath its activity
bash tools/build/build.sh --help       # usage
```

The pipeline exits non-zero on any failure. Every script resolves its
own absolute paths (via `tools/lib/paths.py`) so the build runs from any
cwd. `tools/` is never deployed: it is 403'd at the Apache layer and the
SFTP mirror only ever uploads `public/`.

On a TTY with no mode flag, the build opens with the stage 01 intent
menu (create / rebuild / check / exit) and pauses at the review,
approval, ship and `DEPLOY`-confirmation prompts. Off a TTY every
prompt resolves to its safe default: the build proceeds unattended
through render, seal, verify, sign and the full gate, but stages 10–13
never run — nothing is committed, pushed or deployed automatically.
`tools/build/term.sh` supplies the colour, markers, spinners and
panels; it is pure presentation and never affects the build, signing or
publication.

`--check` is the fast inner loop: stages 01–05 only. The gate runs with
`--skip-signature`, so a check build passes cleanly even though no
fresh signature exists on disk; no signed artefacts are produced. The
full gate — every blocking check, GPG verification included — runs at
stage 08, after signing. `--no-sign` covers the same stages for a CI
environment without the key: it builds and verifies, but no approval,
signature, release archives, deploy gate or ship runs. It is a
build-only convenience, not a deploy path. `--editorial` is gated off
by default so the standard build stays fast and free of the pandoc /
Chromium dependency.

`--public-check` extends `--check` with the public-readiness panel: the
full-history secret scan (`tools/quality/secret_scan.py`) plus
`validate_public_readiness.py --full`. `--public-release` runs the full
ceremony with that panel before review, then — only after the live
smoke test passes — stage 14 asks for a typed `PUBLIC` confirmation and
flips the GitHub repository public via `gh repo edit`. Unattended runs
ship nothing unless explicitly pre-approved with `--yes-public` or
`PUBLIC_RELEASE_APPROVED=1`; `--no-push` caps any run at the commit —
useful when the push should happen later, deliberately.

---

## Build pipeline stages

The build is a numbered publication ceremony. Stages 01 and 06–13 are
operator checkpoints and rituals; stages 02–04 do the generation work,
and the generator order inside them is the load-bearing part (see
below). Stage 14 exists only in `--public-release` runs.

### The stages

| Stage | Name                   | What it does                                                                                                                                                                                                                                    | What it produces                                           |
| ----- | ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| 01    | PUBLICATION INTENT     | Interactive menu: create new edition / rebuild existing / check only / exit; records the edition date and a one-line note. TTY only; skipped when a mode flag is given.                                                                         | The run's mode, edition and note                           |
| 02    | RENDER                 | Source-quality and QR-drift gates, copy compile, bilingual render, single-tree prune, repository-hygiene gate, font subsets (order below).                                                                                                      | The `/en-au/` + `/fr/` page trees and the language gate    |
| 03    | PREPARE PUBLIC BYTES   | Every generator that produces or sweeps public artefacts, ending in the source-mirror convergence loop (order below). `--editorial` adds the review exports here.                                                                               | All generated public files except the final manifest       |
| 04    | SEAL                   | Final `generate_integrity.py` pass over the now-stable post-SRI tree.                                                                                                                                                                           | Final `integrity.json` (archives queued until approval)    |
| 05    | VERIFY                 | `gate.py --skip-signature --all` (blocking, pre-signature) then `lint.py` (advisory, non-blocking). `--check` and `--no-sign` end here.                                                                                                         | Go / no-go verdict                                         |
| 06    | PUBLICATION REVIEW     | Summary panel — edition, note, page counts, public-file and manifest-entry counts, gate results — then a deliberate yes/no on a TTY (off-TTY proceeds unattended).                                                                              | The decision to sign                                       |
| 07    | PUBLICATION APPROVAL   | Derives the signing fingerprint from the _published_ `pgp-key.asc` and requires the matching local secret key — never gpg's ambient default — then `gpg --detach-sign` over `integrity.json`. The hardware-token seam lives here.               | `integrity.json.sig`                                       |
| 08    | SIGNATURE VERIFICATION | `gpg --verify` the fresh signature; build the release archives (`tools/release/build_release_archives.py`); run the full deploy gate (`gate.py`, signature checks included).                                                                    | Verified signature, sealed archives, deploy-ready verdict  |
| 09    | PUBLICATION RECORD     | Panel from `.well-known/build.json` — file count, git commit, key fingerprint. No new artefact.                                                                                                                                                 | The on-screen record                                       |
| 10    | COMMIT                 | `git add public/ metadata/` + a `Publish edition <date>` commit. Reached only via the interactive ship menu.                                                                                                                                    | The committed, attested bytes                              |
| 11    | PUSH                   | Typed `DEPLOY` confirmation, then `git push origin main`. The push only _verifies_ on CI — it does NOT ship. To publish, run the **Deploy to Gandi SFTP** workflow manually (`workflow_dispatch`, `confirm=DEPLOY`); `gh run watch` follows it. | The verifying push (publish is a separate manual dispatch) |
| 12    | SMOKE TEST             | Live probes: expected-200 routes, expected-denial routes, and the live `integrity.json.sig` verified in a throwaway keyring.                                                                                                                    | Live verdict                                               |
| 13    | LIVE                   | The shipped panel: edition, URL, commit, smoke-test and signature status.                                                                                                                                                                       | —                                                          |
| 14    | PUBLIC                 | `--public-release` only, after the smoke test: typed `PUBLIC` confirmation, then `gh repo edit --visibility public`.                                                                                                                            | The repository's public visibility                         |

Stages 10–13 run only from the interactive ship menu after stage 09;
off a TTY the build ends sealed and recorded, with nothing committed,
pushed or deployed.

### Inside stages 02–04: the generator order

This is where the original pipeline lives; the order is the contract.

**Stage 02 — RENDER**

1. `tools/quality/quality.sh --check` — source quality gate
   (formatting / lint preflight on the authored source).
2. `generate_qr.py --check` — QR drift gate.
3. `copy/build_copy.py` — compile `content/en/*.yml` → the `en` subtree
   of `tools/build/copy/strings.json` (resolves `{{ shared.x.y }}`
   refs, lints duplicates; the hand-curated `fr` subtree is preserved).
4. `render_pages.py` — render the bilingual `/en-au/` + `/fr/` trees
   and the `/` language gate from YAML through templates.
5. `copy/prune_single_tree.py` — remove single-tree leftovers.
6. `validate_repository_hygiene.py` — forbidden-artefact gate on
   `public/` (see file class 7).
7. `build_font_subsets.py` — font subsets (non-blocking).

**Stage 03 — PREPARE PUBLIC BYTES**

1. `generate_site.py` — sweep edition / asset_version / CSP hashes into
   HTML and `.htaccess`; minify `styles/*.src.css` → `styles.css`,
   `print.css`, `fonts-full.css`; emit the behaviour-scoped JS bundles
   under `/js/` (+ `sw-register.js`) from `templates/*.template.js`;
   emit `.well-known/person.json`, `site-metadata.json`, `llms.txt`,
   `sitemap.xml`.
2. `generate_htaccess.py` — regenerate the managed `.htaccess` regions.
3. `generate_release_record.py`, `generate_tests_page.py`,
   `generate_documentation.py` — release-record landing page, tests
   results page, documentation surface.
4. `prune_legacy_versioned_assets.py` — remove stale dated asset
   siblings.
5. `generate_sw.py` — emit `sw.js` with the PRECACHE list (driven by
   `tools/lib/public_inventory.py`) and a cache-name fingerprint.
6. `generate_integrity.py` (preliminary) — hash `public/` to feed the
   verification map.
7. `generate_verification_map.py` — emit `verify/verification-data.js`
   (per-route verification records) from the preliminary hashes.
8. `generate_sri.py` — sweep SHA-384 SRI hashes onto every `<link>` /
   `<script>`.
9. Sitemap checksum → `sitemap.xml.sha256`.
10. (`--editorial` only) `copy/build_copy_review.py` +
    `generate_editorial_binaries.py`.
11. The convergence loop: `generate_file_metadata.py` (plus its
    `--sweep` and `--final` passes), `generate_source_view.py`,
    `generate_source_reader.py`, `derive_build_manifest.py`, and
    re-runs of `generate_integrity.py`, `generate_verification_map.py`
    and `generate_sri.py` until the file metadata, source mirrors,
    verification map and SRI all agree.
12. `inject_source_sha_footer.py`, a final
    `generate_file_metadata.py --final`, and
    `generate_public_exposure_manifest.py` close the stage.

**Stage 04 — SEAL**

A final `generate_integrity.py` pass re-hashes the now-stable post-SRI
tree → `integrity.json`. In a full build the release archive is
deliberately queued until after publication approval (stage 08), so the
archive embeds the signed manifest.

### Why the order is load-bearing

Three things mutate HTML in place (`generate_site`, `generate_sri`, the
file-metadata sweeps) and three things produce JS/CSS bytes that SRI
hashes (`generate_site`, `generate_sw`, `generate_verification_map`).
SRI runs once at the end of the byte-mutating phase, after
`verification-data.js` is finalized and before the final integrity
manifest hashes the tree. Otherwise the SRI baked into HTML references
stale bytes of `verification-data.js`, the browser blocks the script,
and the Verify page falls into the "Route not in the verification map"
branch. Because `verification-data.js` is itself a versioned, hashed
asset, stage 03 iterates a short convergence loop to re-version,
re-mirror, and re-hash until the source mirrors, verification map, and
SRI all agree.

### Two-tier deploy gate

The gate is two-tier and the distinction is canonical:

- **`tools/quality/gate.py` — BLOCKING.** Runs only the `Tier.BLOCKING` checks
  from `tools/lib/checks.py`: security and correctness. A failure means the
  tree is unsafe or incorrect to ship. `gate.py` fails fast by default
  (`--all` reports every blocking failure; `--json <path>` writes a
  machine-readable report and implies `--all`; `--skip-signature` omits
  the signature checks for pre-signature runs). Exit 0 = ready to
  deploy, exit 1 = blocked. Inside the build it runs twice: stage 05
  with `--skip-signature --all`, stage 08 in full after signing.
- **`tools/quality/lint.py` — ADVISORY.** Runs only the `Tier.ADVISORY` checks:
  SEO refinement, CSS architecture, editorial copy, comment style,
  nav/anchor shape. These protect polish and maintainability but never
  make the site unsafe, so `lint.py` exits 0 by default even when checks
  fail (`--strict` to exit non-zero; `--format text|json|markdown`). In
  CI, run lint as a non-blocking job so quality findings stay visible
  without blocking an urgent content or security deploy.

> The inline cross-cutting checks (GPG verification, integrity freshness,
> asset-version coherence, sw precache, local-path leakage, archive safety,
> changelog freshness) are functions in `tools/quality/inline_checks.py`;
> `tools/lib/checks.py` registers them alongside the `validate_*` scripts.
> `gate.py` (blocking) and `lint.py` (advisory) are the only entry points.

The categories of blocking check enforced at gate time include:
edition consistency (every active output's edition equals
`identity_canonical.edition`), source-mirror byte-equality (every
`/source/*.txt` byte-equal to its origin; manifest matches disk), GPG
signature verification (`gpg --verify integrity.json.sig
integrity.json`), manifest freshness (every active file in
`integrity.json` with a sha256 that matches disk), signature freshness
(`integrity.json.sig` mtime ≥ `integrity.json` mtime), asset-version
coherence (`site-metadata` ↔ HTML `?v=` ↔ `sw.js` cache name ↔
disk-recomputed bundle hash), SW-precache resolution (every PRECACHE URL
maps to a file on disk with an allowed extension), verification-map
freshness, frozen-archive immutability (every byte under
`public/integrity/releases/YYYY-MM/` matches
`metadata/archive-baseline.json`), and the local-path leak scan
(`/home/`, `Desktop/`, `htdocs/htdocs`, and other server-internal
absolute-path patterns must not appear in any shipped file). Release
archives carry three further gates: per-archive `.sig` and
`SHA256SUMS.sig` verification, `integrity-redistributable.json` byte
matching the ZIP, and the `security.txt` `Expires` field being at least
60 days in the future (RFC 9116 §2.5.5).

---

## File-class taxonomy

Every file in the repository sorts into one of seven classes. The class
determines where it lives, whether it ships to the live host, and
whether the build is allowed to touch it.

### 1. Authored public files — ship verbatim

Hand-edited HTML, CSS, and JS that ship to the live host. The two
authored editions live under `public/en-au/` (English) and `public/fr/`
(French); `public/index.html` is the lightweight language gate. Shared
chrome, error pages, manifests, icons, fonts, and `.well-known/`
documents round out the class:

```
public/index.html                     ← language gate
public/en-au/…  public/fr/…           ← the two authored editions
public/integrity/  public/verify/  public/source/
public/403.html  /404.html  /500.html  /maintenance.html
public/robots.txt  /humans.txt  /changelog.txt
public/manifest.webmanifest  /.htaccess
public/.well-known/security.txt  /pgp-key.asc  /attribution.txt (+ .sig)  /webfinger
public/ai-usage.txt  /assertion.txt  /pgp.txt  /statement.txt  /attestations.json
public/favicon.ico  /favicon.svg  /apple-touch-icon.png  /icon-192.png  /icon-512.png
public/fonts/*.woff2  public/images/*.{svg,png,jpg}
```

The build is allowed to **sweep in place** (`generate_site.py`) for HTML
data-edition / document-edition / asset_version `?v=` / SRI / JSON-LD,
`.htaccess` CSP hashes, and localised dates. Hand edits to those swept
regions are overwritten on the next build — change the source of truth
(e.g. `tools/config/identity_canonical.json` or the YAML copy) and rebuild.

### 2. Generated public files — ship, but never hand-edit

Build outputs that ship to the live host. The build overwrites them:

```
public/js/*.js  public/sw-register.js  ← behaviour-scoped bundles from templates/*.template.js
public/styles.css  /print.css  /fonts-full.css  ← minified from styles/*.src.css
public/site-metadata.json          ← asset_version oracle
public/.well-known/person.json     ← JSON-LD Person entity
public/llms.txt                    ← LLM identity summary
public/sitemap.xml (+ .sha256)     ← URL list with mtimes + checksum
public/source/*.txt                ← byte-equal mirrors
public/source/source-manifest.json (+ .txt)  /source/index.html  /source/README.txt
public/sw.js                       ← service worker + precache list
public/verify/verification-data.js ← per-route verification records
public/documentation/  public/tests/  ← generated documentation + tests surfaces
public/integrity.json (+ .sig)     ← SHA-256 manifest + detached PGP signature
public/integrity/releases/<edition>/…  ← release ZIP/TAR.GZ + .sig + .sha256
        + SHA256SUMS (+ .sig) + integrity-redistributable.json (+ .sig)
public/images/architecture*.svg    ← from a manual generator, not in build.sh
```

### 3. Build inputs — read by the build, never deployed

```
tools/config/identity_canonical.json   ← single source of truth for identity (edition, name, sameAs, …)
tools/build/copy/strings.json   ← en/fr translations; en subtree REGENERATED each build
                                  from content/en/*.yml (edits to en.* overwritten); fr hand-edited
content/en/shared.yml           ← editorial source: cross-page shared copy
content/en/pages/*.yml          ← editorial source: per-page copy
content/fr/…                    ← French editorial source
content/routes.json             ← route registry
metadata/archive-baseline.json  ← frozen-archive immutability baseline
metadata/content-history.json   ← first-seen-date oracle
styles/*.src.css                ← readable CSS source (minified into public/ each build)
templates/*.template.js         ← sources for the generated JS bundles
```

`templates/` is a separate directory from `tools/` to keep authored
build inputs visually distinct from the build machinery.

### 4. Build tools — the pipeline itself, never deployed

```
tools/build/build.sh                  ← the 13-stage publication ceremony (orchestrator)
tools/build/term.sh                   ← terminal presentation primitives (never affects the build)
tools/lib/paths.py                  ← path constants imported by every Python tool
tools/lib/public_inventory.py       ← public-asset surface (sw.js precache + gate)
tools/build/generate_*.py           ← site / sw / integrity / source / sri / verification-map / …
tools/build/render_pages.py           ← bilingual tree + language-gate renderer
tools/build/copy/build_copy.py      ← YAML → strings.json copy compiler
tools/release/build_release_archives.py ← release ZIP + TAR.GZ + SHA256SUMS + sigs
tools/lib/checks.py                 ← registry: every check with its tier + category
tools/quality/gate.py                   ← deploy-blocking gate (security + correctness)
tools/quality/lint.py                   ← advisory quality lint (non-blocking)
tools/quality/inline_checks.py          ← inline cross-cutting check functions (imported by checks.py)
tools/quality/validate_*.py         ← edition / bilingual / htaccess / hygiene validators
tools/verify/validate_*.py          ← release / source-mirror / verification-data validators
tools/release/deploy.sh                 ← build + commit + push convenience wrapper
tools/release/deploy.sftp.lftp.template ← manual emergency-deploy lftp recipe (host/account from env; render with render_deploy_lftp.py)
tools/quality/csp-hashes.sh             ← manual CSP-hash diagnostic helper
```

### 5. Internal documentation — repo-only, never deployed

`docs/` is for the operator, not the public:

```
docs/README.md                   ← entry point
docs/OPERATIONS.md               ← edition / asset / CSP / tests / SW recovery
docs/BUILD-AND-DEPLOYMENT.md     ← this file
docs/ARCHITECTURE.md             ← conceptual map
docs/GATES-CHECKS-AND-QUALITY.md  docs/TRUST-AND-VERIFICATION.md
docs/SECURITY-AND-PRIVACY.md  docs/CONTENT-MODEL.md  docs/INCIDENT-RESPONSE.md
docs/audits/                     ← local-only audit notes (gitignored)
```

### 6. Server-only files — exist on the host, never under public/

Templates for files that live on the live host but must never appear
under `public/` because they contain absolute server paths or other
server-internal data:

```
tools/release/server/user.ini.example    ← PHP auto_prepend_file directive template
```

The deploy pipeline does **not** upload `tools/release/server/`. Server-side
files are placed by hand when needed. The `mirror -R --no-delete`
semantics protect existing server-side files across deploys.

### 7. Forbidden public files — must never appear anywhere in the artefact

These must never appear in `public/`, in source mirrors, in
`integrity.json`, in the source manifest, in the SW precache, or in
release archives:

```
.user.ini  .env  .env.*  .htpasswd
Thumbs.db  .DS_Store  *.swp
*.sqlite  *.db  *.log  *.bak  *.tmp  *.orig
.git/  .github/  private/  console_data/  node_modules/  __pycache__/  *.pyc
id_ed25519  id_ed25519.pub  *.totp_key  *-key.txt
composer.json  composer.lock  package.json  package-lock.json  yarn.lock  pnpm-lock.yaml
styles.v*.css  source/styles.v*.css.txt   ← old asset-version scheme
```

Plus any string under any public file matching a server-internal
absolute-path pattern (`/home/`, `Desktop/`, server vhost roots,
`htdocs/htdocs`). Plus, inside release archives only: proprietary font
binaries (`.woff2`, `.woff`, `.ttf`, `.otf`) — the live site serves them
under licence; redistribution is not permitted, and
`FONT-LICENSE-NOTICE.txt` inside each archive explains the omission.

These rules are enforced at several points: the repository-hygiene gate
(stage 02), the integrity walk and archive-build entry (which abort if
any forbidden artefact is present), and the local-path leak scan inside
`gate.py`.

---

## Why build and deploy are separate

The PGP signing key is the trust root of the site. Putting it into a
GitHub Actions secret would make every workflow change a potential
exfiltration vector — anyone with repo write access could open a PR
that, when merged, runs a workflow that prints the secret. Branch
protection mitigates but does not eliminate this.

The current model keeps the key on the operator's machine, where it is
already needed for everything else. CI's role is reduced to pushing
bytes that have already been signed locally — equivalent in trust to an
`rsync` from the operator's machine. **`tools/build/build.sh` and the CI
workflow are intentionally not symmetric**: the local build signs, the
CI workflow does not. This is the current posture, not a permanent one;
if in-CI rebuilds are ever wanted, the workflow can take a signing-key
secret and the `--no-sign` short-circuit can be removed.

---

## Why the signing key stays local

The runner uploads exactly the bytes already committed at the chosen
ref, after re-verifying `integrity.json.sig` against the committed public
key (`public/.well-known/pgp-key.asc`). If the signature does not verify,
the workflow fails before any SFTP transfer. The key never enters CI, so
a compromised or malicious workflow can publish only bytes that were
already signed locally — it cannot forge a new signed manifest.

---

## Local deploy

Deployment is the push: the GitHub Actions workflow mirrors `public/`
to the host on every push to `main`, so no SFTP credentials are needed
locally. The preferred route is the interactive ship path inside
`tools/build/build.sh` (stages 10–11: commit, typed `DEPLOY`
confirmation, push). `tools/release/deploy.sh` is the thin
non-ceremonial equivalent:

```sh
bash tools/release/deploy.sh                # full build + git commit + push
bash tools/release/deploy.sh --skip-build   # commit + push without rebuilding
bash tools/release/deploy.sh --help         # usage
```

For a true SFTP-from-this-machine emergency (GitHub or Actions
unavailable), `tools/release/deploy.sftp.lftp.template` is a manual,
staged lftp recipe. The host + account are never committed: export
`SFTP_USERNAME` and `SFTP_HOST` from your secret store and render the
concrete (gitignored) recipe with
`python3 tools/release/render_deploy_lftp.py`, then
`cd public && lftp -f ../tools/release/deploy.sftp.lftp`. lftp prompts for
the SFTP password interactively — nothing is stored.

---

## CI deploy and the secrets model

The deploy workflow (`.github/workflows/deploy.yml`) fires on every
push to `main` — that is the normal path, taken by stage 11 of the
build — and can also be triggered manually:

```sh
gh workflow run "Deploy to Gandi SFTP + smoke test" -f confirm=DEPLOY
gh run watch
```

The manual path requires the explicit `confirm=DEPLOY` input. A fork PR
can trigger neither path: `pull_request` events do not fire the
workflow, and pushing to `main` requires write access. The runner does
not rebuild and does not hold the PGP key: it verifies the committed
`integrity.json.sig` against the committed public key in an isolated
throwaway keyring, runs the read-only release sanity check
(`tools/verify/validate_release.py`), mirrors `public/` over SFTP, then
runs the post-deploy smoke test.

### Required GitHub Actions secrets

| Secret             | Holds (template)                                                        |
| ------------------ | ----------------------------------------------------------------------- |
| `SFTP_HOST`        | `SFTP_HOST` — SFTP endpoint hostname                                    |
| `SFTP_USERNAME`    | `SFTP_USERNAME` — SFTP account / login                                  |
| `SFTP_PASSWORD`    | `SFTP_PASSWORD` — SFTP password (rotating to an SSH key is recommended) |
| `SFTP_REMOTE_PATH` | `SFTP_REMOTE_PATH` — remote web-root path the mirror targets            |
| `SFTP_KNOWN_HOSTS` | `SFTP_KNOWN_HOSTS` — pinned host key line(s); optional but recommended  |

Set them with `gh secret set SFTP_HOST --body '…'` (etc.) or in
`Settings → Secrets and variables → Actions`. The workflow maps the
secrets to the env names its lftp heredoc expects; the local
`tools/release/deploy.sh` needs none of them — it deploys by pushing.

### Host-key pinning

`SFTP_KNOWN_HOSTS` pins the SFTP server's host key. Pinning is
conditional and fails safe in both directions: when the secret is set,
the runner writes it to a `known_hosts` file and connects with
`StrictHostKeyChecking=yes`, so a deploy aborts rather than trusting an
unexpected or man-in-the-middle host key; when the secret is unset, the
workflow falls back to `StrictHostKeyChecking=no` with a loud CI
warning, so a missing secret never breaks a deploy. Pin the host key
out-of-band (verified the first time from a trusted network) and rotate
`SFTP_KNOWN_HOSTS` whenever the provider rotates the host key.

### Pre-conditions for a CI deploy

- The commit being deployed is on the default branch and includes a
  valid, locally-signed `public/integrity.json.sig`.
- `bash tools/build/build.sh` was run locally before the push and the
  resulting bytes were committed.

---

## Branch promotion model

Work flows `feature/* → preprod → main`. Three workflows implement it:

- `pr-checks.yml` — on every PR into `preprod` or `main`: the blocking
  `release-gate` job runs the full gate via
  `tools/verify/validate_release.py` (byte-identical to deploy-time
  verification, including the committed-signature check), and the
  blocking `secret-scan` job runs `scan_git_history.py --strict` plus
  `validate_repository_hygiene.py` over the full history. Advisory
  lint jobs ride along without blocking.
- `preprod-deploy.yml` — on push to `preprod`: re-verifies, then mirrors
  to the staging host using `SFTP_PREPROD_*` secrets from the
  `preproduction` environment. Until those secrets exist the deploy
  steps skip cleanly; verification always runs.
- `deploy.yml` — on push to `main` (or manual dispatch): targets the
  `production` environment, which requires the maintainer's approval
  before environment secrets are released, and only accepts deploys
  from `main`.

Rulesets protect both branches: PRs required, status checks
(`release-gate`, `secret-scan`) required, force pushes and deletion
blocked; `main` additionally requires linear history, so promotions
merge as squash or rebase. After each promotion, re-align `preprod`
with `git push origin main:preprod --force-with-lease` (uses the
logged repository-admin bypass).

Signing stays local in this model: feature work is built and signed on
the maintainer's machine, the signed bytes are committed, and every CI
hop only re-verifies them.

### Staging must send noindex

The deployed bytes are production's signed bytes — `robots.txt` and
`.htaccess` cannot differ per target without breaking the signed
integrity manifest. The staging vhost itself MUST therefore send
`X-Robots-Tag: noindex, nofollow` on every response (server
configuration, e.g. in the staging host's Apache vhost). The staging
smoke test fails loudly if the header is missing, so an indexable
staging host cannot pass silently. Ideally also put HTTP basic auth in
front of staging; staging must never be presented as the canonical
site.

---

## Two-pass SFTP mirror, no `--delete`

The deploy mirrors `public/` into the remote web root with a
non-deleting, two-pass pattern (`mirror -R --no-perms`, never
`--delete`): pass 1 uploads everything **except** `*.html`, so every
JS/CSS byte referenced by a versioned `?v=` URL is fully in place at
origin first; pass 2 uploads the HTML that names those URLs. Without
the split, the edge cache can lock in stale bytes under a brand-new
`?v=` URL during the race window and serve them with
`Cache-Control: immutable` indefinitely (the SRI-mismatch class of
bug).

Files removed from `public/` in git stay on the live host until
manually cleaned — `--delete` is deliberately omitted so that an
accidental `git rm`, a botched rebase, or a buggy CI step cannot wipe
live files in seconds. Orphan cleanup is rare and the cost of removing
something live is high, so it stays a manual, deliberate decision via
an interactive SFTP session:

```sh
sftp ${SFTP_USERNAME}@${SFTP_HOST}
> cd SFTP_REMOTE_PATH
> rm <stale-file>
> bye
```

The same `--no-delete` semantics protect server-only files (e.g. the
host's `.user.ini`, which is denied over HTTP and never lives in
`public/`) across deploys.

---

## Post-deploy smoke test

Two smoke tests probe the live URL contract after a deploy: the CI
workflow's post-deploy step (every deploy), and stage 12 of the build
ceremony (when shipping interactively). The CI step checks:

- Expected-200 routes — the language gate, the `/en-au/` and `/fr/`
  page trees (privacy / security / integrity / verify in both
  languages), `/source/`, `/documentation/` (+ `README.pdf` /
  `README.txt`), `/integrity.json` (+ `.sig`),
  `/.well-known/security.txt`, `/.well-known/pgp-key.asc`,
  `/sitemap.xml` (+ `.sha256`), `/robots.txt`, `/humans.txt`,
  `/llms.txt`, `/changelog.txt`.
- Legacy 301s — `/en/…` and the pre-cut-over single-tree URLs
  (`/privacy/`, `/security/`, `/integrity/`, `/verify/`) must redirect
  to their `/en-au/` editions.
- Expected-403/404 routes that prove the deny rules hold: `/.user.ini`,
  `/tools/`, `/templates/`, `/private/`, `/cite.css`,
  `/documentation/README.md`.
- Header assertions — the global CSP on `/` (and no leaked source-view
  CSP), the source-view CSP variant on `/source/view/` and
  `/fr/source/voir/`, `Service-Worker-Allowed: /` and a JavaScript
  content-type on `/sw.js`.
- The live `integrity.json.sig` re-verified against the committed key
  in the same isolated keyring used before upload.

Stage 12 runs a smaller probe set from the operator's machine, plus a
fresh throwaway-keyring verification of the live signature. Any drift
fails the run. Both run from the deployer's network — a green light,
but not a substitute for browser-side checks on real visitor paths.

---

## Rollback

Rollback is **not** automated. Two paths:

1. **Revert the bad commit(s) on `main` (preferred).**

   ```sh
   git revert <bad-commit>
   git push origin main
   ```

   The push re-triggers the SFTP mirror, which puts the prior bytes
   back; the reverted tree carries its own matching `integrity.json` +
   `.sig`, so the workflow's signature check still passes. Combined
   with the non-deleting mirror, files added by the bad deploy stay on
   the host alongside the rolled-back versions. For most regressions
   (HTML or asset content), this is the right move.

2. **Surgical interactive SFTP fix.** For a single bad file, an
   interactive `sftp put` is faster than a re-deploy. After any manual
   fix, re-trigger the workflow
   (`gh workflow run "Deploy to Gandi SFTP + smoke test" -f confirm=DEPLOY`)
   to re-baseline the rest of the tree.

After any rollback, always verify the live state:

```sh
curl -fsS https://trentpower.fr/integrity.json     -o /tmp/i.json
curl -fsS https://trentpower.fr/integrity.json.sig -o /tmp/i.json.sig
gpg --verify /tmp/i.json.sig /tmp/i.json
```

If the signature fails, the manifest and the live tree are out of sync —
re-deploy or restore from a known-good tag.

---

## Residual risks

1. **Workflow modification by a merged malicious commit.** A bad PR that
   edits the deploy workflow could exfiltrate the SFTP credentials.
   Mitigations: branch protection on the default branch, no
   `pull_request_target` in the deploy workflow, and triggers limited
   to push-on-`main` and `workflow_dispatch` — a fork PR cannot fire
   either. A merged bad PR remains a residual risk.
2. **Password in secrets.** Recommended follow-up: rotate to a
   deploy-only ed25519 keypair and switch the workflow to key auth.
3. **No `--delete`.** The live host can drift over time as files are
   removed from git but stay on the host. An accepted trade-off.
4. **Smoke test runs from the deployer's network.** Adequate as a
   green-light signal, not a substitute for real-visitor browser checks.
5. **Licensed fonts are restored, not committed.** The CI runner fetches
   the Klim binaries from the live host (verified against the signed
   `integrity.json`) before the gate runs. If the live host were ever
   wiped _and_ the local originals lost, a CI deploy would fail closed —
   recovery is a manual local deploy from the operator's machine, which
   keeps the licensed originals. See `metadata/repo-exclusions.json`.

---

## Determinism

The build is byte-stable across consecutive runs within the same UTC day,
with no build-time non-determinism in the release path: HTML is
byte-stable, `integrity.json` is byte-stable with no source change,
`sw.js` (precache hash + cache name) is byte-stable, `source/*.txt`
mirrors are byte-equal to their origins, and `verification-data.js` is
byte-stable. Release ZIP/TAR.GZ are content-deterministic (sorted order,
mtimes pinned to edition midnight, gzip mtime 0, no host metadata) except
that they embed `integrity.json.sig`, whose GPG salt rotates per
signature — so the archive's own SHA256 rotates per build while the
contained `.sig` still verifies against the contained `.json`. Anything
else changing byte-for-byte across builds without a source change is a
determinism regression worth investigating.
