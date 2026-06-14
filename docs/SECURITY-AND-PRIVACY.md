# Security and privacy — trentpower.fr

trentpower.fr is a static publication of HTML, CSS, and JavaScript with no
runtime dependencies. Its security and privacy posture follows from that:
nothing third-party runs, nothing is tracked, and only an explicitly
allow-listed set of files is ever served.

This document covers the privacy constraints, the CSP and cross-origin
posture, the public-exposure allow-list architecture (including how to add
a new public route safely), and local secret-handling rules.

---

## Privacy constraints

The site collects nothing and loads nothing third-party at runtime:

- **No analytics.** No first- or third-party analytics scripts.
- **No cookies.** The site sets no cookies.
- **No tracking pixels** or beacons.
- **No third-party runtime assets.** No CDN scripts, fonts, frames, or
  images are fetched at runtime — everything is first-party and
  self-hosted. `default-src 'none'` plus `connect-src 'none'` on normal
  pages enforce this at the browser level.
- **Permissions denied by default.** The Permissions-Policy denies every
  recognised feature (`=()`), with the single exception of
  `clipboard-write=(self)` for the citation-copy path.

The only network capability granted to runtime code is the service
worker's scoped `connect-src 'self'` (see TRUST-AND-VERIFICATION.md), used
solely for offline precaching of first-party files.

---

## CSP and cross-origin isolation posture

The Content-Security-Policy is locked down and must stay that way:

- `default-src 'none'` — retained.
- `connect-src 'none'` on normal pages — retained. The service worker's
  per-file override is `connect-src 'self'`.
- `script-src` is `'self'` plus a small fixed set of `sha256` hashes for
  the inline early-language-detect and error-page i18n IIFEs. **No**
  `unsafe-inline`, **no** `unsafe-eval`, **no** `'inline-speculation-rules'`.

Inline-script discipline (from the 1 May 2026 console pass):

- Every inline `<script>` is either covered by a static CSP hash or is a
  non-enforced type. The language-detect IIFE is hashed
  (`sha256-ong18574DRSzuyO+zjuDNWecbI/I+ojY9Bvoi6zBtvw=`); the error-page
  i18n IIFE is hashed (`sha256-6IU4kJUH23u9bEELiD8ZdnaSmU+/A6HoR4mKug6Msl0=`).
- `application/ld+json` schema blocks are not hashed by design — browsers
  do not enforce `script-src` on that type.
- There are **no** inline event handlers (`onclick=`, `onerror=`, …)
  anywhere, and **no** `eval()`, `new Function()`, or string-form
  `setTimeout`/`setInterval` in any first-party JS or HTML.
- Inline speculation rules were removed (they added no measurable benefit
  to a small static site and created CSP friction); the generator emits
  none.

Cross-origin isolation and transport headers (all retained):

- `Cross-Origin-Opener-Policy: same-origin`
- `Cross-Origin-Embedder-Policy: require-corp`
- `Cross-Origin-Resource-Policy: same-origin` — with a single exception for
  `/images/og/` (social scrapers need a cross-origin pull), set to
  `cross-origin` only there.
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `X-Permitted-Cross-Domain-Policies`, `X-DNS-Prefetch-Control` — all
  retained.

The Permissions-Policy was trimmed to a strict, widely-recognised set;
experimental/deprecated features that only produced console noise
(`ambient-light-sensor`, `document-domain`, `attribution-reporting`,
`browsing-topics`, `interest-cohort`, etc.) were removed. No meaningful
capability was opened in doing so.

> Console noise from `lockdown-install.js` / "SES Removing unpermitted
> intrinsics" and Web3 wallet shims is **not** site code — it is injected
> by browser extensions (MetaMask, Coinbase/Brave Wallet, etc.) into every
> page. Verify in a clean Chrome profile with extensions disabled before
> attributing any CSP/console warning to the site.

---

## Public-exposure allow-list architecture

The public site is **allow-listed, not deny-listed.** Only files and routes
declared in the manifest are intended to be served; everything else is
denied by default by the rewrite-gate at the top of `public/.htaccess`.

This protects against accidental SFTP uploads, backup files, source maps,
local databases, raw build artefacts, private configuration, lockfiles, and
any future class of accidental leak.

### Components

- **`tools/build/generate_public_exposure_manifest.py`** — emits the manifest
  from hardcoded route + glob lists. Sanity-checks: every URL in the public
  inventory resolves against the manifest, and every file under
  `public/.well-known/` and `public/editorial/` is either declared or
  matches a deny pattern.
- **`tools/config/public-exposure.json`** — the manifest itself, schema
  `trentpower.public-exposure.v1`. Committed as a build-source-of-truth
  artefact. It lives under `tools/`, not `public/`, so it is **never
  deployed**.
- **`tools/quality/validate_public_exposure.py`** — the predeploy gate. Walks
  `public/` and proves:
  1. every file is reachable through at least one allow rule;
  2. no file matches a deny rule (`.env`, `.git/`, `.bak`, etc.);
  3. every internal `<href>` / `<src>` / `og:image` / preload link on every
     public HTML page resolves against an allow rule **and** to a real file
     on disk;
  4. baseline integrity artefacts are present (`integrity.json`,
     `integrity.json.sig`, `pgp-key.asc`, `SHA256SUMS`, `SHA256SUMS.sig`,
     and per-edition `SHA256SUMS` / `SHA256SUMS.sig`).
- **`public/.htaccess`** — the rewrite-gate block runs before all
  header/cache rules. Hard deny on dangerous paths and extensions, explicit
  allow rules per category, and a final fallback
  `RewriteRule . - [F,L]` that denies anything not matched (the
  **rewrite-gate `[F,L]` fallback**).

> Gate note: the canonical, blocking gate is `tools/quality/gate.py` (with
> `tools/quality/lint.py` as advisory). `tools/quality/validate_public_exposure.py`
> runs in the blocking tier; the inline cross-cutting checks (leak scans,
> archive safety, GPG verification, …) are functions in
> `tools/quality/inline_checks.py`, registered via `tools/lib/checks.py`.

### Adding a new public route, asset, or artefact

1. Add the page to the generator (or drop the file under `public/`).
2. Update `tools/build/generate_public_exposure_manifest.py` (the hardcoded list
   of routes / root files / globs).
3. Add the matching `RewriteRule` allow line in `public/.htaccess`, in the
   corresponding section.
4. Regenerate: `python3 tools/build/generate_public_exposure_manifest.py`.
5. Validate: `python3 tools/quality/validate_public_exposure.py` — must stay green.
6. Local smoke test (if Apache is available), or push to a staging branch
   first.

### Adding a new deny pattern

1. Update `DENY_EXTENSION_PATTERNS`, `DENY_PATH_PATTERNS`, or
   `DENY_BASENAME_PATTERNS` in the generator.
2. Add the matching deny rule near the top of the `.htaccess` rewrite gate.
3. Re-run the validator. If the new deny matches an existing file under
   `public/`, the validator reports the conflict; either remove the file or
   list it in `DEPLOY_EXCLUDED_GLOBS`.

### Bilingual roots

The authored editions live at `/en-au/` and `/fr/`; `/` is the language
gate. The manifest's `language_roots` field and the corresponding
`.htaccess` allow patterns cover these editions; when adding or changing a
language root, set the manifest's `LANGUAGE_ROOTS`, enable the matching
`.htaccess` allow block, regenerate the manifest, and re-run the validator.

### Post-deploy smoke test

After any `.htaccess` change, confirm allow-listed paths return 200 and
denied paths return 403:

```bash
for path in /privacy/ /verify/ /integrity/ /source/ /security/ \
            /robots.txt /sitemap.xml /integrity.json /styles.css \
            /app.js /favicon.svg /.well-known/security.txt; do
  code=$(curl -sk -o /dev/null -w "%{http_code}" "https://trentpower.fr$path")
  printf "%-50s %s\n" "$path" "$code"
done

for path in /.env /.git/config /package.json /tools/x /src/x \
            /shell.php /test.bak /random.html; do
  code=$(curl -sk -o /dev/null -w "%{http_code}" "https://trentpower.fr$path")
  printf "%-50s %s\n" "$path" "$code"
done
```

200s for the first block, 403s for the second. Representative denied paths
include `.env*`, `.git/config`, `package.json` / lockfiles, `tools/*`,
`templates/*`, `src/*`, `docs/*`, `*.php`, `*.sqlite`, `*.bak`, `*.map`,
and any unknown file or directory.

### Rollback

If a new gate denies a legitimate path, restore the pre-change `.htaccess`
backup (kept at the repo root, never deployed), then rebuild, re-sign, and
push:

```bash
cp .htaccess.predeny.<DATE>.bak public/.htaccess
bash tools/build/build.sh
git add public/.htaccess public/integrity.json public/integrity.json.sig
git commit -m "rollback: restore predeny .htaccess"
git push
```

---

## Dependency security (SCA)

Dependencies are scanned for known vulnerabilities on every pull request by the
`sca` job ([pr-checks.yml](../.github/workflows/pr-checks.yml)), which runs
osv-scanner against the Node lockfile and the Python requirement files, failing
closed. The hash-pinned CI requirement sets in `.github/requirements/` are
additionally tracked by Dependabot.

Remediation thresholds:

- **High or critical** dependency vulnerabilities are fixed before the next
  edition is published. No edition ships with an unresolved high or critical
  finding unless it is explicitly declared non-exploitable in the VEX
  ([../security/openvex.json](../security/openvex.json)) with a recorded reason.
- **Lower severities** are triaged: fixed opportunistically, or recorded in the
  VEX when they cannot affect a static publication with no runtime.

Suppression is never silent: every ignored finding has a matching VEX statement
explaining why it does not affect the published bytes.

---

## Static analysis (SAST)

CodeQL (GitHub default setup) runs static analysis on every pull request and its
check blocks the merge. Remediation threshold: a **high-severity** CodeQL finding
blocks the release until it is fixed or dismissed with a recorded rationale; lower
severities are triaged. The build tooling is additionally linted by ruff,
shellcheck and the quality gate on every PR and every local `--check` build.

---

## Local secret-handling rules

- No real secrets, hostnames, usernames, or server paths belong in the
  repository. Documentation and config samples use **template placeholders
  only** (e.g. `USER`, `<DATE>`, `<edition>`).
- Local-only audit notes and backups (`.bak`, `*.predeny.*`) live at the
  repo root or under `tools/`/`docs/`, **never** under `public/`, so they
  are excluded from deploy and denied by the rewrite gate.
- Build-source artefacts that must not ship (e.g.
  `tools/config/public-exposure.json`) live under `tools/` and are covered by deny
  rules.
- The deploy is automated via GitHub Actions; credentials live in CI
  secrets, not in the tree. Nothing under `public/` should ever contain a
  secret, because every byte there is mirrored at `/source/` and attested in
  `/integrity.json`.

---

## Authorship & AI-usage policy

Authorship and tool provenance are handled separately and are documented in
their own canonical file. In short: all content and code are reviewed
manually before publication; selective language-model assistance may be
used for drafting or structuring, but no automated publishing occurs, and
no AI/co-author trailers are appended to commits.

See **[AUTHORSHIP-STATEMENT.md](AUTHORSHIP-STATEMENT.md)** for the full,
canonical statement, enforcement (`tools/quality/validate_git_metadata.py`,
predeploy step 14), and wording rules. That document is intentionally kept
standalone at its own path (a validator allow-lists it by path) — its
contents are not duplicated here.
