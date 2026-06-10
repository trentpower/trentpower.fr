# Public artefact conventions

internal reference. lives under `docs/`, never deployed to the
public site, never bundled into the release archive.

this file captures the naming, casing, and signing-status rules
that the public artefacts of trentpower.fr observe. three
validators enforce these rules at build time (`validate_signing_status.py`,
`validate_site_metadata.py`, `validate_archive_text_casing.py`).

## Naming convention

| Class                       | Filename casing                            | Example                                                                           |
| --------------------------- | ------------------------------------------ | --------------------------------------------------------------------------------- |
| Public-served               | lowercase, hyphenated                      | `ai-usage.txt`, `site-metadata.json`, `manifest.webmanifest`                      |
| Release-archive orientation | ALLCAPS.txt (convention inside zip/tar.gz) | `README.txt`, `VERIFY.txt`, `RELEASE.txt`, `FILES.txt`, `FONT-LICENSE-NOTICE.txt` |
| Signed-prose declarations   | lowercase                                  | `assertion.txt`, `statement.txt`                                                  |
| Identity / well-known       | lowercase                                  | `.well-known/person.json`, `.well-known/webfinger`, `.well-known/security.txt`    |

filenames are invariant once shipped. renaming any of the above
requires a cross-tree migration: integrity manifest, source mirrors,
release archives, sitemap, robots.txt, links from html.

## Casing matrix (content inside each file)

| File                            | Body prose                            | Labels (before `:`) | Section headers                   |
| ------------------------------- | ------------------------------------- | ------------------- | --------------------------------- |
| `VERIFY.txt` (ZIP)              | lowercase                             | Title Case          | Title Case                        |
| `RELEASE.txt` (ZIP)             | lowercase                             | Title Case          | n/a                               |
| `README.txt` (ZIP)              | lowercase                             | Title Case          | Title Case (under `------` rules) |
| `FILES.txt` (ZIP)               | lowercase                             | Title Case          | n/a                               |
| `FONT-LICENSE-NOTICE.txt` (ZIP) | lowercase                             | n/a                 | n/a                               |
| `ai-usage.txt`                  | lowercase                             | Title Case          | n/a                               |
| `llms.txt`                      | lowercase                             | Capital Case        | Capital Case                      |
| `humans.txt`                    | lowercase                             | n/a                 | `/* TEAM */` markers preserved    |
| `assertion.txt`                 | lowercase (body, inside clear-sign)   | Title Case          | n/a                               |
| `statement.txt`                 | lowercase (body, inside clear-sign)   | Title Case          | n/a                               |
| `.well-known/attribution.txt`   | lowercase                             | Title Case          | n/a                               |
| `.well-known/security.txt`      | RFC 9116 protocol — left as published | Title Case          | n/a                               |

preserve tokens (case-invariant inside any prose line):
urls, paths, identifiers with `.` / `-` / `_` / `:` / `/`, camelCase,
pure hex hashes of 8+ chars.

## Signing-status table

| Class                 | Definition                                      | Verifier                                                                 |
| --------------------- | ----------------------------------------------- | ------------------------------------------------------------------------ |
| `directly_signed`     | inline PGP clearsigned block, or paired `.sig`  | `gpg --verify file`                                                      |
| `covered_by_manifest` | file path is a key in signed `integrity.json`   | `gpg --verify integrity.json.sig integrity.json` then check key presence |
| `signature_carrier`   | detached signature whose target is also covered | n/a (verifier for the target file)                                       |
| `archive_only`        | generated inside ZIP, never served publicly     | release archive `.sig` and SHA256SUMS chain                              |

per-artefact assignment (current — also encoded in
`tools/verify/validate_signing_status.py`):

| Artefact                                                                                       | Class                                                                                                                   |
| ---------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `integrity.json`                                                                               | self-evidencing (covered by `.sig`)                                                                                     |
| `integrity.json.sig`                                                                           | signature_carrier                                                                                                       |
| `.well-known/pgp-key.asc`                                                                      | covered_by_manifest                                                                                                     |
| `pgp.txt`                                                                                      | covered_by_manifest                                                                                                     |
| `assertion.txt`                                                                                | directly_signed                                                                                                         |
| `statement.txt`                                                                                | directly_signed                                                                                                         |
| `.well-known/security.txt`                                                                     | directly_signed (RFC 9116 clearsign)                                                                                    |
| `ai-usage.txt`, `humans.txt`, `llms.txt`, `robots.txt`, `changelog.txt`                        | covered_by_manifest                                                                                                     |
| `.well-known/attribution.txt`                                                                  | covered_by_manifest                                                                                                     |
| `site-metadata.json`                                                                           | covered_by_manifest (self-evidencing; excluded from integrity.json by intent — see generate_integrity.py EXCLUDE_FILES) |
| `attestations.json`, `manifest.webmanifest`                                                    | covered_by_manifest                                                                                                     |
| `.well-known/person.json`, `publication.json`, `webfinger`, `build.json`                       | covered_by_manifest                                                                                                     |
| ZIP archive + `.sig` + `.sha256`                                                               | directly_signed                                                                                                         |
| `SHA256SUMS{,.sig}`                                                                            | directly_signed (top-level mirror + release-dir original)                                                               |
| `integrity-redistributable.json{,.sig}`                                                        | directly_signed (inside release dir)                                                                                    |
| `VERIFY.txt`, `RELEASE.txt`, `FILES.txt`, `README.txt`, `FONT-LICENSE-NOTICE.txt` (inside ZIP) | archive_only                                                                                                            |

## Schema rules — `site-metadata.json`

required top-level keys:
`type`, `schema_version`, `name`, `description`, `url`,
`canonical_url`, `language`, `edition`, `author`, `publisher`,
`information_classes`, `trust_order`, `integrity`, `privacy`,
`citation`, `license`, `machine_readable`, `asset_version`.

forbidden top-level keys:
`asset_bundle` — the build inventory belongs to `integrity.json`
and to the `ASSET_BUNDLE` constant in `tools/build/generate_site.py`.
it must not duplicate into the editorial / identity record.

nested shapes:

- `edition.{id, label, date}`
- `integrity.{manifest, signature, public_key, checksums}`
- `privacy.{tracking, analytics, cookies, third_party_requests, attestations}`
- `citation.{text, format}`
- `license.{content, portrait}`
- `machine_readable.{person, webfinger, security, attestations}`
- `information_classes.{declared, attested}`

`integrity.checksums` must resolve to `/SHA256SUMS` on disk.

## Tone

precise. calm. archival. privacy-first. signed-publication oriented.

avoid: hype, defensive explanations, developer-dashboard language,
excessive legalism, crypto theatre, startup SaaS voice, uppercase
shouting inside prose.

a line at a time: if removing the line would not weaken the trust
or identity claim, remove it.
