# .htaccess plan: bilingual `/en/` + `/fr/` subtrees

When the bilingual split ships, the rewrite gate gains the rules below.
They are kept here — not in `public/.htaccess` — because the production
file should describe what is _live_, not what may ship later.

## Architecture

Each language is a separately-generated static HTML subtree with its
own canonical URL, hreflang alternates, `og:locale`, and structured
metadata. The server stays language-neutral; the build owns language
logic (no runtime translation, no `Accept-Language` redirects, no
varnish behaviour gated on language).

## Allow rules to add

These slot into the `# phase 4 — allow-list` section of the generated
PUBLIC EXPOSURE block (i.e. into `tools/lib/htaccess_config.py` under
`ALLOW_RULE_FAMILIES`):

```python
("bilingual /en/ + /fr/ static trees", [
    r"^(en|fr)/?$",
    r"^(en|fr)/index\.html$",
    r"^(en|fr)/(privacy|security|integrity|verify|source|sw-reset)/?$",
    r"^(en|fr)/(privacy|security|integrity|verify|source|sw-reset)/index\.html$",
    r"^(en|fr)/security/acknowledgments/?$",
    r"^(en|fr)/security/acknowledgments/index\.html$",
    r"^(en|fr)/integrity/(releases|verify-locally)/?$",
    r"^(en|fr)/integrity/(releases|verify-locally)/index\.html$",
    r"^(en|fr)/integrity/releases/[0-9]{4}-[0-9]{2}(-[0-9]{2})?/?$",
    r"^(en|fr)/integrity/releases/[0-9]{4}-[0-9]{2}(-[0-9]{2})?/index\.html$",
]),
```

## Manifest changes

`tools/build/generate_public_exposure_manifest.py` adds `/en/` and `/fr/` to
`LANGUAGE_ROOTS` and emits parallel route + index entries under each
language root. `validate_public_exposure.py` then proves coverage in
both subtrees.

## What to keep in mind

- `RewriteRule` patterns above lose the leading `/` once mod_rewrite
  strips it from the request URI in `.htaccess` context — same as the
  monolingual rules.
- The order across `ALLOW_RULE_FAMILIES` matters; place the bilingual
  family AFTER the monolingual routes so a `/` request still matches
  the existing root rule first (mod_rewrite is first-match-wins).
- Sitemap, robots, and integrity artefacts stay at the root URLs.
  Only HTML pages get language subtree copies.
