# Gates, checks & code quality

The complete reference for how the deploy gate is structured, what each layer
guarantees, every check in the registry, and the dev-only code-quality tooling.
Companion to [`BUILD-AND-DEPLOYMENT.md`](./BUILD-AND-DEPLOYMENT.md) (file
classes + the CI workflow).

This document merges the former `gate-architecture.md`, `check-registry.md` and
`quality.md`.

---

## 1. The two-tier gate

As of 2026-05-30 the single mixed gate was split into two tiers driven by one
registry. **Same guarantees, explicit severity:** security and correctness block
a deploy; editorial/SEO quality is reported but never blocks shipping a content
or security fix.

```
  tools/lib/checks.py        single registry: every check tagged
                         tier (blocking|advisory), category (SEC|COR|QUAL),
                         + a one-line rationale, in gate order.
        │
        ├─▶ tools/quality/gate.py    BLOCKING tier — security + correctness.
        │                    The deploy gate. fail-fast (--all to report all).
        │                    Run by build.sh (stage 05 --skip-signature, stage 08 full)
        │                    and by validate_release.py / CI.
        │
        └─▶ tools/quality/lint.py    ADVISORY tier — quality / editorial / SEO.
                             Exits 0 by default (never blocks); --strict to enforce
                             locally; --format text|json|markdown. Run non-blocking
                             in CI (posts a table to the run summary).
```

- **`tools/lib/checks.py`** is the single registry. Every check is tagged with a
  `tier` (`blocking` | `advisory`), a `category` (`SEC` | `COR` | `QUAL`), and a
  one-line rationale, all in gate order.
- **`tools/quality/gate.py`** runs the BLOCKING tier — security + correctness. This is
  _the deploy gate_. It is fail-fast by default (`--all` reports every failure).
  Run by `build.sh` twice — at stage 05 with `--skip-signature` (pre-signature)
  and in full at stage 08 after signing — and by `validate_release.py` / CI.
- **`tools/quality/lint.py`** runs the ADVISORY tier — quality / editorial / SEO. It
  exits 0 by default (never blocks); `--strict` enforces locally;
  `--format text|json|markdown` chooses output. Run non-blocking in CI, where it
  posts a table to the run summary.

> **`tools/quality/inline_checks.py`** holds the inline cross-cutting check
> _functions_ (GPG verification, integrity and signature freshness,
> asset-version coherence, sw precache, local-path leakage, hidden-artefact and
> archive safety, frozen-archive immutability, changelog freshness). It is a
> library with no entry point: the registry imports it, and `gate.py` /
> `lint.py` run the checks.

- `build.sh` runs `gate.py --skip-signature` then `lint.py` (non-blocking) at
  stage 05, and the full `gate.py` at stage 08 after signing.
- `validate_release.py` wraps `gate.py` and adds release-artefact checks; CI runs
  `validate_release.py` before upload.

### Adding or re-tiering a check

Edit `tools/lib/checks.py` only: add a `Check(...)` entry (function- or
command-backed) with its `tier`, `category`, and `rationale`. `gate.py` /
`lint.py` pick it up automatically; `check-registry.md` regenerates from the same
source. (This consolidated doc is _not_ auto-generated — it is safe to edit by
hand, but keep the registry table below in sync with `tools/lib/checks.py`.)

### What is blocking vs advisory

See the full registry in §3. In summary:

- **Blocking** = the site's public promises (signature, manifest, source-mirror
  byte-match, frozen-archive immutability, path leakage, htaccess allow-list,
  public exposure, no runtime contamination, …) plus correctness (dates, asset
  versions, sw precache, html / bilingual / lang-gate, fonts).
- **Advisory** = orphan images, schema/SEO polish, css-architecture, comment
  style, editorial copy, nav/anchor shape, translation-state, lighthouse
  invariants, etc.

> Two advisory checks (`public_comment_hygiene`, `schema_graph`) carry a NOTE in
> the registry: if either grows a _hard_ assertion (a real secret leak, or broken
> JSON-LD), split that assertion back to blocking. **Demotion must never drop a
> security or correctness guarantee.**

---

## 2. Trust model — what each artefact proves

| Artefact                             | Proves                                                      | Mechanism                                                                                                                              |
| ------------------------------------ | ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `integrity.json`                     | the exact bytes of every active public file                 | sha256 per file, regenerated each build over the final tree                                                                            |
| `integrity.json.sig`                 | the manifest was produced by the site author                | detached GPG signature over `integrity.json`, verified against the **published** key `/.well-known/pgp-key.asc` in a throwaway keyring |
| `/source/*.txt` mirrors              | the live HTML/JS/CSS is exactly what is published as source | each mirror byte-matches its live file (gate: `source_mirrors`); the footer stamps an 8-hex prefix of the mirror's sha256              |
| release archives (ZIP/TAR.GZ + .sig) | a frozen, reproducible edition snapshot                     | deterministic packaging; sealed archives are immutable (gate: `frozen_archives_immutable`)                                             |
| SRI on `<link>`/`<script>`           | the browser ran the exact bytes we hashed                   | SHA-384 integrity attribute per asset                                                                                                  |

### Why `verification-data.js` is signed-not-SRI (intentional)

`/verify/verification-data.js` carries the per-route Verify metadata (sizes,
source hashes, citation, history). It is **deliberately exempt from SRI** because
the file embeds hashes of other files that include the HTML hash that would embed
_its own_ SRI — a self-referential cycle that would stop two consecutive builds
from being byte-identical. Its integrity is instead covered by the **signed
`integrity.json` manifest** (it is listed there like every other file). So the
trust property holds: the data is signed; SRI is simply the wrong tool for this
one self-referential asset. The Verify page loads it as a same-origin `<script>`
that assigns `window.TP_VERIFICATION_MAP`; the modal on content pages reads the
same global.

What SRI does **not** prove: that the _content_ is honest — only that the bytes
are unchanged in transit. Honesty of the content is what the manifest +
signature + source mirrors prove.

### Build convergence (why some generators run more than once)

`build.sh` re-runs `generate_integrity`, `generate_sri`,
`generate_verification_map`, `generate_source_view` and `generate_file_metadata`
a few times each. This resolves a real dependency cycle: HTML bytes → SRI → HTML;
and `verification-data.js` carries the sizes/source-hashes of files that shift as
the tree settles. The build brute-forces to a fixed point. `validate_file_sizes`
and `validate_dates` are the gate checks that _prove_ convergence was reached.
The loop is intentional and gated; flattening it is a known future option (move
the volatile data to a fetched JSON generated once at the end) but carries
Verify-surface risk and is not required for any guarantee — the current design is
already signed and correct.

### Deploy workflow (summary)

`.github/workflows/deploy.yml` (see also `DEPLOYMENT.md`):

- **Pre-upload:** verify `integrity.json.sig` against the published key in a
  throwaway `GNUPGHOME` (never the runner's ambient keyring); run
  `validate_release.py` (which runs the blocking gate + release checks).
- **Upload:** two-pass `lftp` SFTP mirror (assets first, then `*.html`) to avoid
  the asset↔html cache race.
- **Post-deploy smoke test:** re-fetch and re-verify the **live** signature in
  the same isolated keyring; assert route status codes, CSP variants,
  cache-control, SW headers, HSTS, and legacy 301s.
- **Advisory lint** runs as a separate, non-blocking CI job.
- **TODO (needs a secret):** SFTP host-key pinning — add `SFTP_KNOWN_HOSTS` and
  switch the lftp connect-program to `StrictHostKeyChecking=yes` +
  `UserKnownHostsFile`.

---

## 3. The check registry

Sourced from `tools/lib/checks.py` — **48 checks (36 blocking, 12 advisory)**.
`tools/quality/gate.py` runs the blocking tier (deploy-blocking); `tools/quality/lint.py` runs
the advisory tier (never blocks).

| id                             | category | tier     | blocks deploy | owning check                            | rationale                                                                                                                                 |
| ------------------------------ | -------- | -------- | ------------- | --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `edition`                      | COR      | blocking | yes           | `validate_edition.py`                   | no stale edition reference anywhere on the site                                                                                           |
| `repository_hygiene`           | SEC      | blocking | yes           | `validate_repository_hygiene.py`        | no keys / .env / hidden / stale generated artefacts ship                                                                                  |
| `public_readiness`             | SEC      | blocking | yes           | `validate_public_readiness.py`          | public-repo posture holds: licences present, no private-claim drift, no tracked secrets or licensed binaries                              |
| `source_mirrors`               | SEC      | blocking | yes           | `validate_source_mirrors.py`            | every /source/ mirror byte-matches the live file it claims to mirror                                                                      |
| `file_sizes`                   | COR      | blocking | yes           | `validate_file_sizes.py`                | recorded file sizes match disk (convergence honesty)                                                                                      |
| `dates`                        | COR      | blocking | yes           | `validate_dates.py`                     | no date drift across sitemap / json-ld / manifest / metadata                                                                              |
| `gpg`                          | SEC      | blocking | yes           | `check_gpg()`                           | signature verifies against the published key in a clean temp keyring                                                                      |
| `integrity_manifest_freshness` | SEC      | blocking | yes           | `check_integrity_manifest_freshness()`  | every active public file is recorded in integrity.json with a matching hash                                                               |
| `integrity_sig_freshness`      | SEC      | blocking | yes           | `check_integrity_sig_freshness()`       | signature is not stale relative to the manifest it signs                                                                                  |
| `verification_map_dates`       | COR      | blocking | yes           | `check_verification_map_dates()`        | every Verify record is validated today (UTC)                                                                                              |
| `asset_version_coherence`      | COR      | blocking | yes           | `check_asset_version_coherence()`       | asset version agrees across HTML, sw.js and the recomputed bundle hash                                                                    |
| `no_dated_assets`              | COR      | blocking | yes           | `validate_no_dated_assets.py`           | clean asset filenames only; cache-busting lives in ?v=, not the name                                                                      |
| `sw_precache`                  | COR      | blocking | yes           | `check_sw_precache()`                   | every sw.js precache URL maps to a real file of a valid type                                                                              |
| `local_path_leakage`           | SEC      | blocking | yes           | `check_local_path_leakage()`            | no /home/, Desktop/, htdocs/htdocs or server paths leak into public bytes                                                                 |
| `hidden_and_archive_safety`    | SEC      | blocking | yes           | `check_hidden_and_archive_safety()`     | no hidden artefacts/keys; release ZIP free of fonts and stale stylesheets                                                                 |
| `frozen_archives_immutable`    | SEC      | blocking | yes           | `check_frozen_archives_immutable()`     | sealed release archives are byte-identical to their baseline                                                                              |
| `images`                       | COR      | blocking | yes           | `validate_images.py`                    | declared images exist with valid dimensions/formats                                                                                       |
| `no_orphan_images`             | QUAL     | advisory | no            | `validate_no_orphan_images.py`          | no unreferenced images shipped                                                                                                            |
| `signing_status`               | SEC      | blocking | yes           | `validate_signing_status.py`            | the site's 'signed' trust claims match reality                                                                                            |
| `site_metadata`                | COR      | blocking | yes           | `validate_site_metadata.py`             | canonical site-metadata schema is well-formed                                                                                             |
| `archive_text_casing`          | QUAL     | advisory | no            | `validate_archive_text_casing.py`       | ZIP orientation/casing convention                                                                                                         |
| `language_consistency`         | QUAL     | advisory | no            | `validate_language_consistency.py`      | authorship-language consistency                                                                                                           |
| `git_metadata`                 | SEC      | blocking | yes           | `validate_git_metadata.py`              | no AI/attribution trailers; git metadata policy holds                                                                                     |
| `trusted_types`                | SEC      | blocking | yes           | `validate_trusted_types.py`             | Trusted Types / CSP posture holds (XSS hardening)                                                                                         |
| `schema_graph`                 | QUAL     | advisory | no            | `validate_schema_graph.py`              | JSON-LD @graph coherence (SEO/GEO). NOTE: broken JSON-LD should be promoted to blocking when this merges into validate_html in PR3        |
| `lighthouse_invariants`        | QUAL     | advisory | no            | `validate_lighthouse_invariants.py`     | static invariants protecting the Lighthouse score                                                                                         |
| `fonts`                        | COR      | blocking | yes           | `validate_fonts.py`                     | declared fonts exist                                                                                                                      |
| `public_comment_hygiene`       | QUAL     | advisory | no            | `validate_public_comment_hygiene.py`    | no machinery references in deployed comments. NOTE: if it asserts any hard secret-leak rule, split that assertion back to blocking in PR3 |
| `source_mirror_readability`    | QUAL     | advisory | no            | `validate_source_mirror_readability.py` | /source/ assets are served as readable text (byte-match itself is blocking, above)                                                        |
| `no_runtime_contamination`     | SEC      | blocking | yes           | `validate_no_runtime_contamination.py`  | no third-party runtime / network calls injected                                                                                           |
| `html_correctness`             | COR      | blocking | yes           | `validate_html_correctness.py`          | no structural HTML defects (parse-clean)                                                                                                  |
| `css_architecture`             | QUAL     | advisory | no            | `validate_css_architecture.py`          | cascade-layer contract (@layer rules, !important budget)                                                                                  |
| `editorial_copy`               | QUAL     | advisory | no            | `validate_editorial_copy.py`            | editorial-copy rules                                                                                                                      |
| `nav_regression`               | QUAL     | advisory | no            | `validate_nav_regression.py`            | masthead-only header shape didn't regress                                                                                                 |
| `home_anchors`                 | QUAL     | advisory | no            | `validate_home_anchors.py`              | homepage anchor model intact                                                                                                              |
| `bilingual_html`               | COR      | blocking | yes           | `validate_bilingual_html.py`            | per-page lang/canonical/hreflang + no runtime-i18n residue                                                                                |
| `translation_state`            | QUAL     | advisory | no            | `validate_translation_state.py`         | every content/fr/ page declares translation freshness                                                                                     |
| `lowercase_comments`           | QUAL     | advisory | no            | `validate_lowercase_comments.py`        | CSS/source comment prose is lowercase                                                                                                     |
| `lang_gate`                    | COR      | blocking | yes           | `validate_lang_gate.py`                 | the / language vestibule is static, self-canonical, no auto-redirect                                                                      |
| `public_exposure`              | SEC      | blocking | yes           | `validate_public_exposure.py`           | the public-exposure allow-list covers exactly the real public routes                                                                      |
| `htaccess_allowlist`           | SEC      | blocking | yes           | `validate_htaccess_allowlist.py`        | simulate the .htaccess rewrite gate -- only intended URLs are reachable                                                                   |
| `htaccess_drift`               | SEC      | blocking | yes           | `generate_htaccess.py`                  | generated .htaccess regions have no uncommitted drift                                                                                     |
| `htaccess_audit`               | SEC      | blocking | yes           | `audit_htaccess.py`                     | focused .htaccess + CSP-freshness audit                                                                                                   |
| `changelog_freshness`          | COR      | blocking | yes           | `check_changelog_freshness()`           | edition is not newer than the topmost changelog entry                                                                                     |

---

## 4. Code quality — format, lint, commit

Zero-friction formatting + correctness linting for the trentpower.fr sources. It
is **dev-only** — nothing here ships to the live site — and it is scoped to
**authored source**, never the generated/signed `public/` tree.

### What runs on what

| Language                | Tool                       | Mode          | Source targets                                                  |
| ----------------------- | -------------------------- | ------------- | --------------------------------------------------------------- |
| Python                  | **Ruff**                   | format + lint | `tools/**/*.py`                                                 |
| Shell                   | **shfmt** + **ShellCheck** | format + lint | `tools/*.sh`, `tools/hooks/*`                                   |
| JS (authored)           | **ESLint**                 | lint only     | `templates/*.template.js`, `public/verify/verify.js`            |
| YAML/MD/JSON (authored) | **Prettier**               | format        | `content/**/*.yml`, `docs/**/*.md`, root `*.md`, `package.json` |
| CSS                     | **Stylelint**              | lint only     | `tools/*.src.css`                                               |

Everything generated/signed is excluded permanently via `.prettierignore`,
`.stylelintignore`, `eslint.config.js` (files-scoped) and `pyproject.toml`
(`extend-exclude`). The `public/` tree, `integrity.json`, source mirrors,
editorial exports and release archives are **never** touched.

### Why these scopes (the source-vs-generated rule)

- The only authored JS is the `templates/*.template.js` build inputs + the one
  hand-authored `public/verify/verify.js`. Everything in `public/js/`, `sw.js`,
  `verify/verification-data.js` is **generated and hashed in `integrity.json`** —
  reformatting it would break signatures.
- CSS is authored in `tools/*.src.css` (minified → `public/styles.css`). The
  `@layer` architecture is enforced by `tools/quality/validate_css_architecture.py`;
  Stylelint runs **lint-only** (no `--fix`) with aesthetic/vendor-prefix rules
  disabled so it never fights that gate or the editorial style.
- HTML templates use `{{ token }}` syntax, so no HTML linter is used; generated
  HTML is already validated by `validate_html_correctness` /
  `validate_bilingual_html` / `validate_schema_graph`.

### Daily workflow

```sh
npm install                 # one-time: the Node tools (prettier, eslint, stylelint)
bash tools/install-hooks.sh # one-time: the pre-commit hook

npm run quality             # check everything (format:check + all linters)
npm run quality:fix         # auto-format (ruff/shfmt/prettier); linters still report
```

Granular scripts: `format`, `format:check`, `lint:js`, `lint:css`, `lint:py`,
`lint:sh`.

The native tools (Ruff, ShellCheck, shfmt) are standalone binaries — install
once:

```sh
curl -LsSf https://astral.sh/ruff/install.sh | sh        # ruff -> ~/.local/bin
# shellcheck + shfmt: distro package, or the project's release binaries (aarch64/arm64)
```

`quality.sh` **skips any tool that is not installed**, so a partial local
toolchain still works; CI installs the full set.

### Where it sits in the pipeline (never format after signing)

```
quality  ->  generate  ->  hash  ->  sign  ->  archive  ->  gate
```

`build.sh` runs `tools/quality/quality.sh --check` as the first step of stage
**02 · RENDER**, _before_ any generation or signing, so malformed/unformatted
source can never reach the
integrity hashes. The post-build `gate.py` (which runs after signing)
additionally enforces the `validate_verification_data` shape check on the
generated Verify map.

### HTML — why there is no HTML formatter (at any level)

Prettier is deliberately **not** run on HTML. The question "format at template /
yaml / generator / post-generation level?" was investigated; every level has a
hard blocker:

| Level                                   | Verdict        | Blocker                                                                                                                                                                                                           |
| --------------------------------------- | -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Template** (`templates/pages/*.html`) | ✗ blocked      | Prettier's HTML parser corrupts closing tags (`</a` without `>`) on the `>{{ token }}</tag>` pattern — ~831 instances — and re-indents the (signed) JSON-LD + reflows the numbered `<!-- head · NN -->` comments. |
| **YAML**                                | n/a            | YAML is content data, not HTML — `content/*.yml` is formatted by Prettier, but that is values, not markup.                                                                                                        |
| **Generator** (`render_pages.py`)       | n/a            | It is a `{{token}}` substituter, not an HTML formatter — out of scope.                                                                                                                                            |
| **Post-generation, pre-sign**           | ✗ not worth it | Possible, but reflows the JSON-LD + head comments (intentional structure), and injects Node into the deterministic build, for no correctness gain.                                                                |

HTML correctness instead stays with the existing Python validators —
`validate_html_correctness`, `validate_bilingual_html`, `validate_schema_graph` —
and the templates + `render_pages.py` already produce consistent,
intentionally-structured HTML.

### Enforcement ratchet (`QUALITY_ENFORCE`)

Adoption is gradual — the codebase is not broken all at once:

| Stage                | State                                                                              |
| -------------------- | ---------------------------------------------------------------------------------- |
| 1. Land tooling      | configs + `quality.sh` + hook in place; `QUALITY_ENFORCE=0` (advisory, exits 0).   |
| 2. Format pass       | `npm run quality:fix` committed separately as a no-logic-change diff.              |
| 3. Lint as warnings  | linter findings visible in the build/CI/hook output, non-blocking.                 |
| 4. Ratchet to errors | set `QUALITY_ENFORCE=1` (in the build env + CI) once the warnings are burned down. |

`QUALITY_ENFORCE=0` (default) → issues are reported but never block.
`QUALITY_ENFORCE=1` → `quality.sh` exits non-zero and the `build.sh` preflight
(and the pre-commit hook) block. Flip it deliberately, per language, when that
language's source is clean.

### The publication firewall (validation, in Python — not a second stack)

The trust/route surfaces are validated by the existing Python gate, not a
parallel Node/Zod layer. The "firewall" coverage added on top:

- **`tools/lib/routes.py` `_validate`** — every route slug is allowlisted
  (`^[a-z0-9]+(?:-[a-z0-9]+)*$` per `/`-segment, empty allowed for home); rejects
  `..`, traversal, absolute/leading-slash and backslash slugs at the route
  source.
- **`tools/verify/validate_verification_data.py`** — every Verify record is shaped +
  bounded (path-safe, `sha256-<b64>`, `size_bytes` a positive int ≤ 2 MB, dates
  `YYYY-MM-DD`, no duplicates). Wired into `gate.py` as a blocking check.

Everything else (edition dates, integrity manifest, canonical/hreflang, path
leakage, public-exposure) is already covered by `validate_edition`,
`validate_dates`, `validate_release`, `validate_bilingual_html`,
`validate_public_exposure` and `check_local_path_leakage` — see the registry in
§3.

---

## 5. Check report contract

The machine-readable envelope every check runner writes. Defined once in
`tools/lib/check_report.py`; this section is the canonical prose definition.

All reports are **local-only runtime artefacts** written under
`reports/checks/`. They carry a real wall-clock timestamp, are gitignored
(`reports/checks/*.json`), and never enter `public/` or a release archive.

### Producers

| Report                                 | Producer                                                         | Command  | Builder              |
| -------------------------------------- | ---------------------------------------------------------------- | -------- | -------------------- |
| `reports/checks/last-gate.json`        | `tools/quality/gate.py --json PATH`                              | `gate`   | `build_check_report` |
| `reports/checks/last-lint.json`        | `tools/quality/lint.py --json PATH`                              | `lint`   | `build_check_report` |
| `reports/checks/last-audit.json`       | `tools/score-ledger/score_ledger.py report --latest --json PATH` | `audit`  | `build_audit_report` |
| `reports/checks/last-secret-scan.json` | `tools/quality/secret_scan.py`                                   | `secret` | (envelope head only) |

`tools/lib/checks.py` owns checks; `tools/score-ledger/` owns the live audit.
The envelope belongs to neither, so it lives in the neutral `check_report`
module both import.

### Shared head

Every report begins with the same head:

```json
{
  "schema_version": 1,
  "generated_at": "2026-06-10T12:00:00Z",
  "command": "gate",
  "status": "passed",
  "summary": { "passed": 36, "failed": 0, "warnings": 0, "duration_ms": 12450 }
}
```

- `status` — `"passed"` | `"failed"`. For gate/lint, `"failed"` iff at least
  one **blocking** check failed; advisory failures surface as
  `summary.warnings` and never flip status. For audit, `"failed"` iff any
  scorecard is FAIL — **a report signal only; the audit never gates a deploy.**

### Check report body (gate / lint)

Each entry in `checks[]` carries `id`, `label`, `tier`
(`"blocking"`|`"advisory"`), `category` (`"SEC"`|`"COR"`|`"QUAL"`), `status`,
`duration_ms`, `rationale`, captured `stdout`/`stderr`, and `affected_files`
(ships `[]` — populating it needs validators to emit structured file lists).

### Audit report body (score-ledger)

In addition to the shared head: `run` (run id, timestamps, pages),
`scorecards` (`PASS`|`REVIEW`|`FAIL` with `top_driver`), `headline_metrics`
(value/previous/best/`rolling_median` — the trustworthy baseline; a single-run
dip is not a regression), and `open_actions`.

### API (`tools/lib/check_report.py`)

- `utc_now_iso()` — UTC ISO-8601 with trailing `Z`.
- `atomic_write_json(obj, path)` — temp-then-rename; never leaves a partial file.
- `summarise_results(checks)` — `{passed, failed, warnings, duration_ms}`.
- `build_check_report(command, checks)` — gate/lint envelope.
- `build_audit_report(command, run, scorecards, headline_metrics, open_actions)` — audit envelope.

`tools/lib/checks.py` adds `CheckResult` + `run_check_captured(check)`
producing the per-check dict that `build_check_report` consumes.
