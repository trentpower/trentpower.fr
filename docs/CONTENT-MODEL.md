# Content model — trentpower.fr

How editorial copy, routes, and the public JavaScript are produced. The site
is a static bilingual publication: authored editions live under `/en-au/`
(English) and `/fr/` (French); `/` is a language gate. There is no runtime
i18n — all copy is baked into HTML at build time.

---

## Editorial YAML source model

All editorial copy lives in `content/` as YAML. You never edit generated HTML
or generated `strings.json` directly — you edit the YAML source and run the
build, which regenerates the derived surfaces.

```
content/
  routes.json            registry of every published route (generated)
  shared/
    routes.yml           source of truth for routes.json
    gate.yml             language-gate copy
  en/
    shared.yml           repeated English language used across the site
    pages/
      home.yml           one file per main page; top-level keys map to
      privacy.yml          the strings.json surfaces that page owns
      integrity.yml
      source.yml
      verify.yml
      security.yml
      system.yml
      local.yml
  fr/
    shared.yml           French equivalents (hand-edited — see below)
    pages/
      home.yml
      privacy.yml
      integrity.yml
      source.yml
      verify.yml
      security.yml
      system.yml
```

### Page YAML structure

- Each `pages/<name>.yml` maps its top-level keys to the `strings.json`
  surfaces owned by that page.
- The `meta:` block holds `<title>`, OpenGraph, and social-preview copy for
  that page.

### shared.yml

`shared.yml` holds repeated language used across the site:

- **Aliases** (`site`, `actions`, `verification`) are referenced from page
  YAMLs by `{{ ... }}` reference (see "Single-substitution reference rules").
- **Cross-page chrome surfaces** (`footer`, `modal`, `cite`, `copy`,
  `trust_routes`) are emitted directly to the matching `{surface}` keys for
  that language.

After editing any YAML, run the build (`tools/build/build.sh`) to regenerate the
derived copy. Direct edits to a generated `strings.json` subtree are
overwritten on the next build.

---

## routes.json registry

`content/routes.json` is the machine-readable registry of every published
route. It is **generated** from `content/shared/routes.yml` (the source of
truth) — regenerate with `tools/build/generate_routes_json.py`; never hand-edit
`routes.json`.

Top-level fields: `schema_version`, `generated_from`, `note`, `languages`
(`["en-AU", "fr"]`), and `routes`.

Each route entry carries:

| Field                 | Meaning                                                                    |
| --------------------- | -------------------------------------------------------------------------- |
| `id`                  | unique route id, e.g. `home.en-au`, `privacy.fr`                           |
| `route_key`           | logical page key shared across languages, e.g. `home`                      |
| `path`                | published URL path, e.g. `/en-au/`, `/fr/confidentialite/`                 |
| `language` / `locale` | `en-AU` / `en_AU`, or `fr` / `fr_FR`                                       |
| `template`            | page template id                                                           |
| `content`             | YAML source path, e.g. `content/fr/pages/home.yml`                         |
| `schema`              | JSON Schema validating the content, e.g. `schemas/content/home.schema.json` |
| `canonical`           | self-canonical URL                                                         |
| `alternate`           | hreflang alternates (the other edition + `x-default` → `/`)                |
| `editable`            | content is hand-editable YAML (vs generated)                               |
| `preview`             | route can be rendered standalone for preview                               |
| `trust_surface`       | route is a trust/governance surface (integrity, verify, source, security)  |

There are 20 routes (each logical page in both `en-AU` and `fr`). French
paths use localized slugs (`/fr/confidentialite/`, `/fr/securite/`,
`/fr/integrite/`, `/fr/verifier/`, `/fr/source/voir/`), with the English
edition under the corresponding `/en-au/...` paths.

---

## English auto-regenerated vs French hand-edited

The two editions are produced differently, and this asymmetry is intentional:

- **`content/en/*.yml` is AUTO-REGENERATED from source on every build.** The
  English subtree of the generated copy (`tools/build/copy/strings.json` `en`
  subtree) is rebuilt from these YAML files by the build; the English copy is
  the authored source of record and edits flow English → derived surfaces.
- **`content/fr/*.yml` is HAND-EDITED.** The French edition is curated by
  hand — translations are deliberate editorial work, not machine output. The
  build consumes the French YAML as authored; it does not auto-generate or
  overwrite it from the English.

Practical rule: to change English copy, edit `content/en/...` and rebuild. To
change French copy, edit `content/fr/...` by hand and rebuild. Never expect the
build to translate or backfill the French from the English.

> Ancillary English-only pages (maintenance, sw_reset, error 403/404/500) and
> the other-language subtrees that are not yet migrated to YAML stay in
> `strings.json` for now; they migrate in a later pass.

---

## Single-substitution reference rules

References between YAML files use exactly one form — no conditionals, loops,
or expressions:

```yaml
'{{ shared.site.proof_line }}'
```

Lint rules (enforced by `tools/build/copy/build_copy.py`):

- An unresolved `{{ ... }}` remaining after substitution → **build error**.
- A reference to a key not present in `shared.yml` → **build error**.
- A string ≥ 30 chars appearing more than 3 times outside `shared.yml` →
  **build warning**, suggesting promotion into `shared.yml`.

Keep references to a single dotted path into `shared.yml`. The substitution
engine is deliberately dumb: one reference resolves to one shared string.

---

## Templates → generated JavaScript

The public JavaScript is generated at build time from `*.template.js` files in
`templates/`. **Edit the `*.template.js` source; never edit the generated
`*.js`** — the generated files are overwritten on every build and direct edits
are silently lost.

- `templates/app.template.js` → the generated public app script.
- `templates/cite.template.js` → the generated public cite script.
- The `templates/` directory also holds behaviour-scoped templates
  (`copy`, `edition`, `fonts`, `language-gate`, `local`,
  `micro-interactions`, `overlay`, `reveal`, `source-view`, `sw-register`,
  `theme`, `verify-modal`) plus a `templates/pages/` subtree.

The relationship is one-directional: template (source, edited) → generated JS
(public artefact, never edited). If you find yourself editing a generated
`*.js` under the public tree, stop — locate the corresponding
`*.template.js` and edit that instead, then rebuild.

---

## Build invariants

- One edit to the YAML source propagates to all derived copy surfaces on the
  next build; do not edit derived surfaces by hand.
- `routes.json` is generated from `content/shared/routes.yml`; regenerate with
  `tools/build/generate_routes_json.py`.
- English copy is authored in `content/en/` and auto-regenerated into the
  derived `en` subtree; French copy is authored by hand in `content/fr/`.
- Generated public JS comes from `templates/*.template.js`; never edit the
  generated files.
