# Operations — trentpower.fr

Procedures for building, deploying, testing, and recovering the site. The site
is a static bilingual publication (`/en-au/` + `/fr/`, `/` is a language gate).
No runtime backend; manual, deliberate, finite.

This document merges the maintenance procedures, the post-deploy test plan, the
service-worker recovery notes, and the caching/headers policy.

> Hostnames, usernames, server paths, and secret values in this document are
> **template placeholders** (e.g. `<SFTP_HOST>`, `<SFTP_USERNAME>`,
> `<SFTP_REMOTE_PATH>`). Substitute your real values locally; never commit them.

Contents:

1. [Single source of truth + generators](#1-single-source-of-truth--generators)
2. [Edition date](#2-edition-date)
3. [Asset versioning](#3-asset-versioning)
4. [CSP / security headers](#4-csp--security-headers)
5. [Build, gate, and release checklist](#5-build-gate-and-release-checklist)
6. [Integrity manifest + signing](#6-integrity-manifest--signing)
7. [Deployment](#7-deployment)
8. [Caching policy](#8-caching-policy)
9. [Post-deploy smoke test](#9-post-deploy-smoke-test)
10. [Full test plan](#10-full-test-plan)
11. [Service-worker recovery](#11-service-worker-recovery)
12. [Maintenance mode](#12-maintenance-mode)
13. [Annual maintenance](#13-annual-maintenance)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Single source of truth + generators

The site uses a single-source-of-truth architecture. Editorial copy lives in
`content/` YAML (see `docs/CONTENT-MODEL.md`); identity/edition data lives in a
canonical JSON source. Generators derive every machine-facing file and update
every HTML surface from those sources — you never hand-edit a generated file.

### Build entrypoint

`bash tools/build/build.sh` is the authoritative engine (renders, hashes, signs,
gates). Use `--check` for the fast inner loop, no flag for the
full signed build. CI calls `build.sh` directly.

### Generator table

| Generator                                                          | Outputs                                                                                                                                                                                                 | When to run                                                               |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| copy/i18n build (`tools/build/copy/build_copy.py`, via `build.sh`) | regenerates the derived copy from `content/*/**.yml`                                                                                                                                                    | after editing any `content/` YAML                                         |
| `tools/build/generate_routes_json.py`                              | `content/routes.json`                                                                                                                                                                                   | after editing `content/shared/routes.yml`                                 |
| site generator (`generate_site.py`, via `build.sh`)                | machine-facing identity files (Person JSON-LD / `person.json`, `site-metadata.json`, `llms.txt`, `sitemap.xml`) + propagates edition + `rel="me"` links + `.htaccess` CSP hashes into all HTML surfaces | after editing the canonical identity/edition source or any content change |
| templates → generated JS (via `build.sh`)                          | the behaviour-scoped public JS bundles under `/js/` (+ `sw-register.js`) from `templates/*.template.js`                                                                                                 | every build — **edit the `*.template.js`, never the generated `*.js`**    |
| `generate_sw.py`                                                   | `sw.js`                                                                                                                                                                                                 | after adding/removing/renaming versioned assets                           |
| `generate_integrity.py`                                            | `integrity.json`                                                                                                                                                                                        | after every file change, **always last**                                  |

### What the site generator propagates

From a single edit to the canonical identity/edition source:

| Surface              | Field propagated                                                               |
| -------------------- | ------------------------------------------------------------------------------ |
| `person.json`        | full Person JSON-LD (description, sameAs, all fields)                          |
| `site-metadata.json` | edition, citation, author identity                                             |
| generated cite JS    | citation string with edition date                                              |
| `llms.txt`           | description, role, topics, identity verification links                         |
| `sitemap.xml`        | lastmod dates from file mtimes (integrity files use edition date)              |
| home pages           | meta description, og:description, Person JSON-LD, WebSite JSON-LD dateModified |
| all HTML files       | `<meta name="document-edition">`                                               |
| all HTML files       | `<link rel="me">` links from the sameAs array                                  |
| integrity page       | "Last reviewed: DD Month YYYY"                                                 |
| `.htaccess`          | CSP SHA-256 hashes (recomputed from updated JSON-LD)                           |

### Validation

The site generator validates before writing: all required fields present, edition
date is valid ISO 8601 (`YYYY-MM-DD`), URL matches domain, all sameAs entries use
HTTPS, image metadata complete. On failure it exits with errors and writes
nothing.

### The gate

- `python3 tools/quality/gate.py` — **blocking** canonical gate. Must be green before
  deploying. Use `--json reports/checks/last-gate.json` for the machine report.
- `python3 tools/quality/lint.py` — **advisory** only. Failures surface as warnings;
  they never block. `--json reports/checks/last-lint.json`.
- Check logic lives in the `validate_*` scripts and in
  `tools/quality/inline_checks.py` (inline cross-cutting checks);
  `tools/lib/checks.py` registers all of them into the two tiers.

### Adding a sameAs link (worked example)

1. Edit the canonical identity source's `sameAs` array (HTTPS only), e.g. add a
   Wikidata identifier.
2. Run the build (`bash tools/build/build.sh`) — the new link propagates to the
   Person JSON-LD (home + `person.json`), every `<link rel="me">`, `llms.txt`
   identity verification, and the `.htaccess` CSP hashes.
3. The build regenerates `integrity.json` last.
4. Gate, sign, deploy.

---

## 2. Edition date

ISO 8601 (`YYYY-MM-DD`). The canonical edition source is the only place you set
it; the build propagates it to:

- `site-metadata.json` (generated)
- generated cite JS citation string
- `llms.txt` citation line
- `sitemap.xml` lastmod entries (from file mtimes; integrity files use the
  edition date)
- `<meta name="document-edition">` in every HTML page
- the integrity page review date (`DD Month YYYY` format)

All surfaces update automatically — never hand-roll the date across files.

---

## 3. Asset versioning

### Scheme

All cacheable static assets carry an explicit version number in the filename:

```
styles.v6.css
app.v6.js
ibm-plex-mono-400.v5.woff2
```

HTML URLs are never versioned. **Never reuse a version number, even for
identical content** — reuse causes cache poisoning across CDN and browser
caches.

### How to bump versions

Current state at time of writing: CSS at v6, fonts at v5, JS at v6. When
bumping, increment all to the next unified version (e.g. v7).

1. **Rename files:**
   ```bash
   mv styles.v6.css styles.v7.css
   mv app.v6.js app.v7.js
   cd fonts/
   for f in *.v5.woff2; do mv "$f" "$(echo $f | sed 's/.v5./.v7./')"; done
   ```
2. **Update all HTML references** in every `.html` file (`styles.v6.css →
styles.v7.css`, `app.v6.js → app.v7.js`).
3. **Update CSS font references** in the new stylesheet (`.v5.woff2 →
.v7.woff2`).
4. **Regenerate the service worker:** `python3 generate_sw.py`.
5. **Verify no old references remain:**
   ```bash
   grep -rn '\.v5\.\|\.v6\.' *.html styles.v7.css sw.js
   ```
6. **Regenerate and sign:** `python3 generate_integrity.py`, then sign and
   deploy.
7. **Delete old files from the server.**

---

## 4. CSP / security headers

All security headers are set in `.htaccess` using `Header always set`. CSP
SHA-256 hashes for the inline JSON-LD are **managed automatically** by the site
generator — when you change the canonical source and rebuild, it recomputes the
Person + WebSite JSON-LD hashes and updates `.htaccess` in place.

Manual hash recompute (only if needed):

```bash
./docs/csp-hashes.sh
```

### Current header set

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
X-Permitted-Cross-Domain-Policies: none
X-DNS-Prefetch-Control: off
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
Cross-Origin-Resource-Policy: same-origin
Permissions-Policy: (clipboard-write=(self), all other APIs denied ())
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'none'; ... script-src 'self' + 3 SHA-256 hashes; connect-src 'none'
X-Powered-By: (unset)
```

HTTP Link header (advertises the Person JSON-LD):

```
Link: <https://trentpower.fr/.well-known/person.json>; rel="alternate"; type="application/ld+json"
```

`clipboard-write=(self)` is allowed for the code copy button on the integrity
page and the Cite button in the footer.

**Never add** `'unsafe-inline'`, `'unsafe-eval'`, `connect-src` allowances, or
third-party domains to any security header.

Test: `curl -I https://trentpower.fr/`. External scanners:
[securityheaders.com](https://securityheaders.com/?q=trentpower.fr),
[Mozilla Observatory](https://observatory.mozilla.org/analyze/trentpower.fr),
[SSL Labs](https://www.ssllabs.com/ssltest/analyze.html?d=trentpower.fr).

---

## 5. Build, gate, and release checklist

Run for every deploy. No exceptions.

### Standard deploy (content or config changes)

```bash
# 1. Make your changes (content YAML, templates, identity source).

# 2. Build (regenerates copy, JS, identity surfaces, CSP hashes):
bash tools/build/build.sh

# 3. If versioned assets changed, regenerate the SW:
python3 generate_sw.py

# 4. Always last — regenerate integrity:
python3 generate_integrity.py

# 5. Gate (must be green):
python3 tools/quality/gate.py

# 6. Sign:
unset GNUPGHOME
gpg --detach-sign --armor -o integrity.json.sig integrity.json

# 7. Deploy (see §7), then run the smoke test (§9).
```

### Full deploy (identity or edition roll)

```bash
# 1. Edit the canonical identity/edition source (edition date, identity changes).

# 2. Build (propagates to all surfaces automatically):
bash tools/build/build.sh
python3 generate_sw.py        # only if assets changed
python3 generate_integrity.py

# 3. Gate:
python3 tools/quality/gate.py

# 4. Sign:
unset GNUPGHOME
gpg --detach-sign --armor -o integrity.json.sig integrity.json
gpg --clearsign --output tmp.txt assertion.txt && mv tmp.txt assertion.txt
gpg --clearsign --output tmp.txt statement.txt && mv tmp.txt statement.txt

# 5. Deploy all changed files; delete any removed files from the server.
```

### Signing inventory

| File                                              | Method               | When to re-sign                  |
| ------------------------------------------------- | -------------------- | -------------------------------- |
| `integrity.json` → `integrity.json.sig`           | detached signature   | every deploy                     |
| `assertion.txt`                                   | clearsigned in-place | only if assertion text changes   |
| `statement.txt`                                   | clearsigned in-place | only if statement text changes   |
| `.well-known/security.txt`                        | clearsigned in-place | only if content changes          |
| `.well-known/attribution.txt` → `attribution.sig` | detached signature   | only if attribution text changes |

---

## 6. Integrity manifest + signing

Every time a file is added, changed, or removed, `integrity.json` must be
regenerated and re-signed.

### When to regenerate

After **any** change to **any** publicly served file. If you changed a file and
deployed it, regenerate.

### How to regenerate

```bash
python3 generate_integrity.py
```

Hashes all publicly served files (excluding generator scripts, documentation,
`.DS_Store`, `private/`, and `integrity.json` itself). **Always run this last**,
after all other generators and manual edits.

### How to sign

```bash
unset GNUPGHOME
gpg --detach-sign --armor -o integrity.json.sig integrity.json
```

### Temporary keyring + signing safety

- **Verification** uses a temporary keyring (`GNUPGHOME` set to a `mktemp`
  directory; public key only).
- **Signing** requires the normal personal keyring (`GNUPGHOME` unset).

If `GNUPGHOME` is still set to a temp directory after verification, signing
fails. Recovery:

```bash
unset GNUPGHOME
gpgconf --kill gpg-agent
gpgconf --launch gpg-agent
gpg --list-secret-keys --keyid-format LONG
```

**Rule:** never sign while `GNUPGHOME` is set to a temporary directory.

### Release archive

Signed historical snapshots live under `/integrity/releases/` (per-release
`index.html` + `integrity.json` + `integrity.json.sig`, plus a shared
`archive.css` and a releases listing page). See `docs/TRUST-AND-VERIFICATION.md` for the full
procedure.

---

## 7. Deployment

### Hosting profile

- **Provider:** PHP/Apache shared hosting (template: Gandi Simple Hosting).
- **Protocol:** SFTP.
- **Cache layer:** managed Varnish (not configurable).
- **TLS + HTTPS/www redirects:** managed at the provider edge, **not** in
  `.htaccess`.
- **Canonical domain:** `https://trentpower.fr` (no www).

### Deploy via GitHub Actions (preferred)

Pushing to `main` triggers the SFTP-to-host deploy workflow
(`.github/workflows/deploy.yml`); the runner mirrors the `public/` bytes already
in git, after re-verifying `integrity.json.sig` against the committed public
key. The runner **never** holds the signing key and never runs the generators —
`bash tools/build/build.sh` must have been run locally and the bytes committed first.

Manual trigger (if the workflow is gated on a confirm input):

```sh
gh workflow run "Deploy public/ to host SFTP" -f confirm=DEPLOY
gh run watch
```

Required repo secrets (template placeholders — set once via
`gh secret set <NAME>` or in repo Settings → Secrets and variables → Actions):

| Secret             | Value                                                       |
| ------------------ | ----------------------------------------------------------- |
| `SFTP_HOST`        | `<SFTP_HOST>`                                               |
| `SFTP_USERNAME`    | `<SFTP_USERNAME>`                                           |
| `SFTP_PASSWORD`    | `<SFTP_PASSWORD>`                                           |
| `SFTP_REMOTE_PATH` | `<SFTP_REMOTE_PATH>`                                        |
| `SFTP_KNOWN_HOSTS` | host-key pin (optional; see `docs/BUILD-AND-DEPLOYMENT.md`) |

Intentional limitations: **no `--delete`** on the mirror (files removed from
`public/` stay on the host until manually cleaned — protects against accidental
wipes); the deploy is gated on a deliberate trigger; the commit must be on
`main` with a valid `integrity.json.sig`.

### Deploy via local SFTP (alternative)

```bash
sftp <SFTP_USERNAME>@<SFTP_HOST>
# Upload changed files only:
put .htaccess
put index.html
put styles.v6.css
# ...or upload everything:
put -r .
```

After deploying, Varnish may serve cached responses for up to ~60 seconds. Wait
or request a cache purge through the provider admin panel.

### Provider gotchas (do NOT do these)

- **No `RewriteRule` HTTPS redirects.** Varnish terminates SSL before Apache;
  Apache never sees `HTTPS=on`, so HTTPS rewrite rules cause infinite redirect
  loops. HTTPS + www→non-www are handled at the provider edge.
- **No `AddType` in `.htaccess`** — `AllowOverride` does not permit `FileInfo`.
  Use `Header set Content-Type` inside `<FilesMatch>` blocks.
- **No non-ASCII in `.htaccess`** — em dashes, arrows, box-drawing characters
  make Apache reject the file ("Server unable to read htaccess file"). Verify:
  `grep -P '[^\x00-\x7F]' .htaccess`.
- **No hand-editing generated files** — edit the YAML/template/canonical source
  instead.
- **Varnish caches 404s aggressively.** Append `?bust=1` to test, or wait.
- **Duplicate file/directory conflicts** — a file named `privacy` blocks a
  `privacy/` directory; delete the file.
- **Directories must be 755, files 644.** Apache can't traverse directories
  without execute permission.
- **Trailing slashes matter** — link to `/privacy/` not `/privacy`; Varnish does
  not reliably redirect.

---

## 8. Caching policy

Desired headers + caching policy. Use this when configuring caching in a hosting
provider's UI or CDN dashboard rather than `.htaccess`. The repo's `.htaccess`
implements these exact rules for Apache. All content-type rules are enforced with
`X-Content-Type-Options: nosniff`.

### Security headers (apply to ALL responses)

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
X-Permitted-Cross-Domain-Policies: none
X-DNS-Prefetch-Control: off
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
Cross-Origin-Resource-Policy: same-origin
Permissions-Policy: accelerometer=(), autoplay=(), camera=(), clipboard-read=(), clipboard-write=(self), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), picture-in-picture=(), usb=(), web-share=()
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'none'; upgrade-insecure-requests; block-all-mixed-content; script-src 'self' <3 SHA-256 hashes>; style-src 'self'; font-src 'self'; img-src 'self'; manifest-src 'self'; worker-src 'self'; connect-src 'none'
Remove: X-Powered-By
```

### Cache rules

| Pattern                                                      | Cache-Control                          | Rationale                          |
| ------------------------------------------------------------ | -------------------------------------- | ---------------------------------- |
| `*.html`                                                     | `public, max-age=0, must-revalidate`   | always fresh                       |
| `*.v{N}.css`, `*.v{N}.js`, `*.v{N}.woff2`                    | `public, max-age=31536000, immutable`  | version in filename = safe forever |
| `images/trent-power.jpg`, `images/trent-power-og.jpg`        | `public, max-age=31536000, immutable`  | permanent entity images            |
| `sitemap.xml`, `robots.txt`                                  | `public, max-age=3600`                 | hourly                             |
| `security.txt`, `humans.txt`, `pgp.txt`                      | `public, max-age=86400`                | daily                              |
| `pgp-key.asc`, `attribution.txt`, `attribution.sig`          | `public, max-age=86400`                | daily                              |
| `person.json`, `site-metadata.json`                          | `public, max-age=86400`                | daily                              |
| `llms.txt`, `ai-usage.txt`, `assertion.txt`, `statement.txt` | `public, max-age=86400`                | daily                              |
| `cite.css`, `webfinger`                                      | `public, max-age=86400`                | daily                              |
| `attestations.json`, `manifest.webmanifest`                  | `public, max-age=86400`                | daily                              |
| `archive.css`                                                | `public, max-age=86400`                | daily                              |
| `integrity.json`, `integrity.json.sig`                       | `public, max-age=300, must-revalidate` | 5 minutes                          |

### Content types (explicit in `.htaccess`)

| Endpoint                                             | Content-Type                |
| ---------------------------------------------------- | --------------------------- |
| `webfinger`                                          | `application/jrd+json`      |
| `security.txt`                                       | `text/plain; charset=utf-8` |
| `robots.txt`                                         | `text/plain`                |
| `sitemap.xml`                                        | `application/xml`           |
| `pgp-key.asc`                                        | `application/pgp-keys`      |
| `attribution.sig`, `integrity.json.sig`              | `application/pgp-signature` |
| `person.json`, `integrity.json`, `attestations.json` | `application/json`          |
| `manifest.webmanifest`                               | `application/manifest+json` |
| `llms.txt`, `ai-usage.txt`                           | `text/plain; charset=utf-8` |

### Notes

- Versioned assets use `immutable` because the version number changes when
  content changes — safe forever-caching.
- HTML revalidates on every request for fresh content.
- Integrity files have a short 5-minute TTL so signature updates propagate
  quickly after deploys.
- **Never add** `'unsafe-inline'`, `'unsafe-eval'`, `connect-src` allowances, or
  third-party domains to any security header.

---

## 9. Post-deploy smoke test

Run this block after every deployment for fast validation (~2 min):

```bash
echo "=== Smoke test ==="
DOMAIN="https://trentpower.fr"

# 1. Homepage loads
echo "Homepage: $(curl -sI $DOMAIN/ | head -1)"

# 2. CSP present
echo "CSP: $(curl -sI $DOMAIN/ | grep -c 'content-security-policy') header(s)"

# 3. HSTS present
echo "HSTS: $(curl -sI $DOMAIN/ | grep -c 'strict-transport') header(s)"

# 4. Schema blocks
echo "Schema blocks: $(curl -sS $DOMAIN/ | grep -c '@type')"

# 5. Description alignment
META=$(curl -sS $DOMAIN/ | grep -A1 'name="description"' | grep -o 'content="[^"]*"')
OG=$(curl -sS $DOMAIN/ | grep 'og:description' | grep -o 'content="[^"]*"')
[ "$META" = "$OG" ] && echo "Descriptions: aligned" || echo "Descriptions: DIFFER"

# 6. Images serve
echo "Portrait: $(curl -sI $DOMAIN/images/trent-power.jpg | head -1)"
echo "OG image: $(curl -sI $DOMAIN/images/trent-power-og.jpg | head -1)"

# 7. Integrity signature
tmpdir="$(mktemp -d)" && export GNUPGHOME="$tmpdir"
ts=$(date +%s)
curl -fsS "$DOMAIN/.well-known/pgp-key.asc?ts=$ts" | gpg --import 2>/dev/null
curl -fsS "$DOMAIN/integrity.json?ts=$ts" -o /tmp/i.json
curl -fsS "$DOMAIN/integrity.json.sig?ts=$ts" -o /tmp/i.sig
RESULT=$(gpg --verify /tmp/i.sig /tmp/i.json 2>&1 | grep -c "Good signature")
[ "$RESULT" -ge 1 ] && echo "Signature: valid" || echo "Signature: FAILED"
unset GNUPGHOME && rm -rf "$tmpdir" /tmp/i.json /tmp/i.sig

# 8. Zero external requests (check manually in browser DevTools Network tab)
echo "External requests: check browser DevTools Network tab"

echo "=== Done ==="
```

**Acceptance:** all lines show `200 OK`, expected counts, or `aligned`/`valid`.
No `DIFFER` or `FAILED` lines.

---

## 10. Full test plan

Run after every deployment. Terminal tests use `curl` + `gpg`; online tests use
browser validators. Each category has acceptance criteria.

### Smoke-test categories

1. **Security headers** — every header present on the canonical homepage:

   ```bash
   curl -sI https://trentpower.fr/ | grep -iE 'content-security|strict-transport|x-frame|x-content|referrer-policy|permissions-policy|cross-origin|x-powered'
   ```

   CSP starts `default-src 'none'` with 3 `sha256-` hashes; HSTS
   `max-age=31536000; includeSubDomains`; `x-frame-options: DENY`;
   `x-content-type-options: nosniff`; `referrer-policy: no-referrer`;
   `permissions-policy` contains `clipboard-write=(self)` with all others `()`;
   COOP `same-origin`, COEP `require-corp`, CORP `same-origin`;
   `x-powered-by` must NOT appear.

2. **HTTPS + HSTS** — canonical host serves HSTS; HTTP→HTTPS and www→non-www
   redirect (301/302). The www redirect may NOT include HSTS (provider edge
   limitation — expected).

3. **CSP enforcement** — homepage CSP has `connect-src 'none'`; `sw.js` CSP has
   `connect-src 'self'` (override for the service-worker fetch); both have
   `script-src 'self'` + SHA-256 hashes. Zero CSP violation errors in DevTools
   console.

4. **Cache headers** — `*.html`: `public, max-age=0, must-revalidate`;
   versioned assets + images: `public, max-age=31536000, immutable`;
   `integrity.json[.sig]`: `public, max-age=300, must-revalidate`; governance
   files daily; `sitemap.xml`/`robots.txt` hourly. (See §8 for the full table.)

5. **Content-Type headers** — `pgp-key.asc`: `application/pgp-keys`;
   `*.sig`: `application/pgp-signature`; `integrity.json`/`attestations.json`:
   `application/json`; `manifest.webmanifest`: `application/manifest+json`.

6. **Page responses** — `/`, `/privacy/`, `/integrity/`,
   `/security/acknowledgments/` (and the localized `/en-au/...` + `/fr/...`
   equivalents) return `200`; nonexistent path `404`; `.htaccess` request
   `403`; `/privacy` (no slash) redirects to `/privacy/`.

7. **Governance files** — all of
   `/.well-known/security.txt`, `pgp-key.asc`, `attribution.txt`,
   `attribution.sig`, `/pgp.txt`, `/humans.txt`, `/robots.txt`,
   `/attestations.json`, `/manifest.webmanifest` return `200`. `pgp-key.asc`
   and `pgp.txt` are byte-identical:

   ```bash
   diff <(curl -sS https://trentpower.fr/.well-known/pgp-key.asc) <(curl -sS https://trentpower.fr/pgp.txt)
   ```

8. **Cryptographic integrity** — import the published key into a temp keyring
   and `gpg --verify integrity.json.sig integrity.json` → `Good signature`. The
   `not certified with a trusted signature` warning is expected (temp keyring).

9. **Attribution signature** — same flow for `attribution.sig` /
   `attribution.txt` → `Good signature`.

10. **Fingerprint consistency** — the fingerprint on the integrity page, in
    `attribution.txt`, and from the key itself all match.

11. **Zero network egress** — DevTools → Network: every request is to
    `trentpower.fr`; zero external domains, fonts, scripts, analytics, pixels.

12. **Service worker + offline** — `sw.js` registered and activated; the
    edition-scoped cache exists; homepage + privacy load fully offline; a
    NEVER_CACHE path is not served offline.

13. **Speculation rules** — privacy page prerenders on hover (DevTools →
    Application → Speculative Loads); navigation near-instant.

14. **Print stylesheet** — no blank pages; nav/footer/modal/skip-link hidden;
    `trent@trentpower.fr` in footer; external links show URL in brackets; ~2
    pages; black-on-white, 9–10pt body.

15. **Structured data** — `validator.schema.org` on the homepage: exactly a
    Person block (`@id` `#trent-power`, name, description, image, jobTitle,
    affiliation, `knowsAbout`, `sameAs`) and a WebSite block (author/publisher
    `@id` → `#trent-power`); no errors; `privacyPolicy` must NOT appear.
    Terminal: `curl -sS https://trentpower.fr/ | grep -o '"@type":"[^"]*"'` →
    only `Person` + `WebSite`.

16. **Description alignment** — meta description, OG description, schema
    description, and hero statement are the identical sentence.

17. **OpenGraph / social cards** — LinkedIn Post Inspector + Facebook Sharing
    Debugger: title, description, `og:image` = `trent-power-og.jpg` at
    1200×630, no warnings.

18. **Images** — both portrait (square) and OG (landscape) return `200` +
    `image/jpeg`; neither appears visually in any page layout (schema/OG only).

19. **Sitemap** — lists the editions + governance JSON; `lastmod` is the
    current deploy date; no deprecated `<changefreq>`/`<priority>`.

20. **Accessibility** — Lighthouse Accessibility score **100**; keyboard:
    skip-link first on Tab, logical Tab order, visible focus outlines, modal
    traps focus + Escape closes + focus returns; reduced-motion disables all
    animation.

21. **Mobile** — readable without zoom; touch targets ≥ 24px; no horizontal
    scroll; nothing clipped.

22. **security.txt validation** — `Contact:` present, `Expires:` in the future,
    `Canonical:` matches the fetch URL, `Encryption:` →
    `/.well-known/pgp-key.asc`.

23. **Security scanners** — securityheaders.com grade A/A+; Mozilla Observatory
    A/A+.

24. **`rel="author"` on all pages** — every page has exactly one author link →
    `/.well-known/attribution.txt`.

25. **Print stylesheet on all pages** — every page links `print.css` exactly
    once.

### Online validator summary

| Test                   | URL                                                          |
| ---------------------- | ------------------------------------------------------------ |
| Schema validation      | https://validator.schema.org                                 |
| Rich results           | https://search.google.com/test/rich-results                  |
| LinkedIn preview       | https://www.linkedin.com/post-inspector/inspect/             |
| Facebook OG debug      | https://developers.facebook.com/tools/debug/                 |
| Security headers       | https://securityheaders.com/?q=trentpower.fr                 |
| Mozilla Observatory    | https://observatory.mozilla.org/analyze/trentpower.fr        |
| internet.nl            | https://internet.nl/site/trentpower.fr/                      |
| PageSpeed / Lighthouse | https://pagespeed.web.dev/analysis?url=https://trentpower.fr |
| SSL/TLS                | https://www.ssllabs.com/ssltest/analyze.html?d=trentpower.fr |

> The post-deploy live-site **score ledger** (`tools/score-ledger/`) is a
> separate observational audit tool, not part of this test plan and not a
> deploy gate. See `docs/SCORE-LEDGER.md`.

---

## 11. Service-worker recovery

When a return visitor sees a stale page or offline fails entirely, the fastest
path is to drop the local service worker + its caches by hand. The site itself
never asks visitors to do this; these notes are for the operator.

### How the cache name works

The cache name is `tp-{edition}.{bundle_hash}-{precache_hash}-{release_tag}`.

- `bundle_hash` covers the generated `/js/*.js` bundles, `sw-register.js`,
  `verify/verify.js`, `styles.css`, `print.css` and `fonts-full.css`.
- `precache_hash` covers every PRECACHE entry's bytes (pages, fonts, icons,
  SVGs, scripts, styles).
- `release_tag` is a free-form name set in `generate_sw.py` for the current
  release.

Any change to any precached file changes one of those hashes → `activate`
removes the old cache → returning visitors get the fresh bundle on next
navigation. No manual cache-bust needed.

### Strategy

- **Critical assets** (HTML, CSS, JS): must cache on install — if any fails,
  install fails entirely.
- **Secondary assets** (fonts): cached best-effort.
- **Versioned assets**: cache-first.
- **Navigation**: network-first with cache fallback.

Run `python3 generate_sw.py` instead of editing `sw.js` by hand.

### Per-browser unregister steps

**Chrome / Edge / Brave**

1. DevTools → Application → Service Workers → **Unregister** on
   `https://trentpower.fr/`.
2. Application → Storage → **Clear site data** (untick cookies to keep the
   language preference).
3. Hard reload (Cmd/Ctrl-Shift-R).

**Safari (macOS)**

1. Develop → Service Workers → trentpower.fr → **Unregister Service Worker**.
2. Develop → Empty Caches.
3. Reload.

**Safari (iOS)**

1. Settings → Safari → Advanced → **Website Data**.
2. Edit → remove `trentpower.fr`.
3. Reload the site online once so the new SW installs cleanly.

**Firefox**

1. `about:debugging#/runtime/this-firefox` → Service Workers → trentpower.fr →
   **Unregister**.
2. `about:preferences#privacy` → Manage Data → trentpower.fr → Remove.
3. Hard reload (Cmd/Ctrl-Shift-R).

### Sanity checks before blaming the SW

```bash
# 1. /sw.js is fresh (Cache-Control: no-cache, must-revalidate)
curl -sI https://trentpower.fr/sw.js | grep -iE 'cache-control|content-type'

# 2. A PRECACHE URL serves 200
curl -sI https://trentpower.fr/styles.css | head -1

# 3. Cache name matches the deployed asset version
grep -oE "tp-[^']+" htdocs/sw.js
```

If the gate's service-worker precache check fails, a precache URL is missing on
disk or has an unexpected extension — read the error; it names the URL.

### Offline acceptance test

Run after every `sw.js` change, on iOS Safari and Chrome on Android:

1. Open `https://trentpower.fr/` — wait for full load.
2. Navigate to `/privacy/` — wait for full load.
3. Wait 15 seconds.
4. Enable airplane mode.
5. Reload — should work.
6. Navigate to `/` and `/privacy/` — should work.
7. Force-close the browser, reopen, navigate — should work.

---

## 12. Maintenance mode

A maintenance page is included for quick site-wide downtime.

**Enable** — in `.htaccess`, swap the commented/uncommented lines at the top:

```apache
# Comment out the live lines:
# DirectoryIndex index.html
# ErrorDocument 403 /403.html
# ErrorDocument 404 /404.html

# Uncomment the maintenance lines:
DirectoryIndex maintenance.html index.html
ErrorDocument 403 /maintenance.html
ErrorDocument 404 /maintenance.html
```

Upload the updated `.htaccess`.

**Disable** — reverse the swap and re-upload.

---

## 13. Annual maintenance

Once per year (or after any significant change):

1. **Roll the edition** — update the canonical edition date; confirm all
   identity fields current.
2. **Rebuild** — `bash tools/build/build.sh` (propagates to all surfaces).
3. **Review the privacy page** — confirm claims still match implementation:
   | Claim | Verify |
   |---|---|
   | No cookies | `grep -rn 'cookie' app.v6.js` returns nothing |
   | No storage | `grep -rn 'localStorage\|sessionStorage' app.v6.js` returns nothing |
   | No third-party requests | `grep -rn 'https\?://' app.v6.js` returns nothing |
   | No analytics | no tracking scripts in any HTML file |
   | No AI inference on visitors | no ML/AI libraries loaded |
4. **Update `attestations.json`** — update `last_reviewed` after verifying all
   claims.
5. **Renew `security.txt`** — update the `Expires:` field (RFC 9116 requires a
   future date), re-clearsign.
6. **Run security scanners** — securityheaders.com, Observatory.
7. **Run accessibility audit** — Lighthouse, axe.
8. **Verify HSTS** present on the canonical host.
9. **Regenerate + sign** — `python3 generate_integrity.py`, then sign.

Fonts are self-hosted in `/fonts/` as woff2, no external loading (IBM Plex Mono
300/400/500/600; Newsreader 300/400/500/400i).

---

## 14. Troubleshooting

| Symptom                                | Cause                                                         | Fix                                                                                    |
| -------------------------------------- | ------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Redirect loop after `.htaccess` change | `RewriteRule` for HTTPS; Varnish terminates SSL before Apache | remove all `RewriteRule`/`RewriteCond`                                                 |
| "Server unable to read htaccess file"  | non-ASCII characters or disallowed directives (`AddType`)     | ensure pure ASCII (`grep -P '[^\x00-\x7F]' .htaccess`); use `Header set` not `AddType` |
| Styles/JS not updating after deploy    | browser cached the immutable v{N} asset                       | bump the version number; never use cache-busting query strings                         |
| CSP blocking a resource                | a new resource not covered by CSP                             | check console; if JSON-LD changed, rebuild (auto-updates CSP hashes)                   |
| JSON-LD not detected by Rich Results   | CSP hash mismatch                                             | rebuild — recomputes + updates CSP hashes automatically                                |
| BAD signature on `integrity.json`      | regenerated but not re-signed                                 | `gpg --detach-sign --armor -o integrity.json.sig integrity.json`; deploy both          |
| Privacy page 404                       | missing trailing slash, file/dir conflict, or cached 404      | use trailing slashes; check SFTP; wait or `?bust=1`                                    |
| SW installed but offline fails         | `sw.js` served with global CSP blocking `fetch()`             | ensure `.htaccess` CSP override for `sw.js` has `connect-src 'self'`                   |
