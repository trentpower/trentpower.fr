# Architecture — trentpower.fr

A conceptual map of how the site is put together and why. This is the
"shape of the thing" document; for the step-by-step pipeline and deploy
procedure see [`BUILD-AND-DEPLOYMENT.md`](BUILD-AND-DEPLOYMENT.md).

trentpower.fr is a personal website that is **static, editorial, finite,
and cryptographically attested**. Every design choice below follows from
those four words.

---

## Static by default

The live site is plain files: HTML, CSS, and a small amount of vanilla
JavaScript, served by Apache on managed shared hosting (Varnish cache in
front, TLS managed by the host, Brotli/gzip negotiated). There is:

- **No runtime CMS.** Pages are produced at build time, not assembled
  per request.
- **No database.** There is no server-side state to query, migrate, or
  back up.
- **No analytics, no tracking, no cookies**, and no `localStorage` /
  `sessionStorage`.
- **No third-party runtime assets.** No frameworks, bundlers,
  transpilers, CDNs, third-party scripts, or external fonts. Fonts are
  self-hosted woff2; every asset is same-origin.

JavaScript is strictly an enhancement: language switching, scroll
reveal, a project modal, a citation overlay, and service-worker
registration. The page means the same thing with JavaScript disabled —
nothing client-side defines content. A service worker provides offline
support (cache-first for frozen archive assets, network-first for
navigations), but it caches only the same static bytes the server ships.

The benefit of static-by-default is that the entire attack and
maintenance surface collapses to "a directory of files." There is no
request-time code path to exploit, and the bytes a visitor receives are
exactly the bytes that were authored, built, and signed.

---

## Two authored editions plus a language gate

The site ships **two authored editions**, each a complete tree:

- `/en-au/` — the English (Australian) edition.
- `/fr/` — the French edition (with localised path segments, e.g.
  `confidentialite`, `securite`, `integrite`, `verifier`).

`/` itself is a **lightweight language gate**: a small landing page that
routes a visitor into one of the two editions. It carries no editorial
content of its own — it exists only to direct the reader to the right
tree. Both `public/en-au/` and `public/fr/` are real, shipped
directories; the gate is the only thing at the root.

This is a deliberately flat model: rather than a single tree with
runtime locale negotiation, each language is a fully-rendered static tree
that can be verified, archived, and served independently.

---

## Content authored in YAML, rendered through templates

Editorial copy is not written directly into HTML. It lives as structured
**YAML** under `content/`:

- `content/en/shared.yml` and `content/en/pages/*.yml` — the English
  source (cross-page shared copy plus per-page copy).
- `content/fr/…` — the French source.
- `content/routes.json` — the route map binding copy to output paths.

At build time the YAML is compiled and rendered through templates into
the two static page trees. Shared fragments are referenced (e.g.
`{{ shared.x.y }}`) and resolved at compile time, so a phrase that
appears on several pages has one source. The English copy additionally
feeds the `en` subtree of the inlined i18n string table; the other
languages are translated alongside it. The result is that copywriters
edit prose in one structured place and the build sweeps it into every
surface — page bodies, footer edition strings, citation strings,
metadata — in lockstep, with no manual synchronisation.

Identity data follows the same single-source discipline: everything
(edition date, name, `sameAs` links, and so on) flows from
`tools/config/identity_canonical.json`, and the generators sweep it into every
file that mentions it.

---

## Generated trust surfaces

On top of the authored content, the build produces a set of **generated
trust surfaces** whose whole purpose is to let anyone verify that the
bytes they received are the bytes that were authored and signed:

- **Integrity manifest.** `integrity.json` is a SHA-256 manifest of
  every public file, accompanied by a detached PGP signature
  `integrity.json.sig`. The public key is published at
  `/.well-known/pgp-key.asc` (and `/pgp.txt`). Anyone can re-verify the
  live manifest against the live signature with a standard `gpg --verify`
  recipe.
- **Per-route verification records.** `/verify/` exposes a per-page
  route → expected-SHA-256 map, so an individual page can be checked
  without downloading the whole manifest.
- **Source mirrors.** `/source/` carries byte-equal `*.txt` mirrors of
  every active HTML/CSS/JS file — the bytes you read are demonstrably the
  bytes that were signed.
- **Release archives.** Each edition is published under
  `/integrity/releases/<YYYY-MM-DD>/` as a signed ZIP + TAR.GZ with a
  standalone `SHA256SUMS` and an `integrity-redistributable.json`, each
  with its own detached signature. Older editions are **byte-frozen**:
  an immutability gate checks every byte of past release directories
  against a committed baseline, so the historical record cannot drift.
- **Machine-readable identity and posture.** `/.well-known/person.json`
  (JSON-LD), `/.well-known/webfinger`, `/llms.txt`, `/attestations.json`,
  and the clearsigned `assertion.txt` / `statement.txt` /
  `attribution.txt` make both identity and the privacy/security posture
  checkable by machines, not just humans.

These surfaces are generated, never hand-edited; the build rewrites them
each time and the deploy-blocking gate refuses to ship if any of them is
stale or unsigned.

---

## Deterministic build, no LLM in the release path

The build is **deterministic**: two consecutive runs with no source
change produce byte-identical output (modulo the PGP signature
timestamp, which carries a rotating salt). There is no build-time
non-determinism — no network fetches, no clock-dependent content beyond
the UTC-day edition stamp, and crucially **no LLM dependency in the
release path**. The bytes that get signed and shipped are a pure,
reproducible function of the YAML content, the identity source, and the
templates. (Optional editorial-export tooling can produce review
documents, but it is gated off the default build and never feeds the
signed artefact.)

Determinism is what makes the trust surfaces meaningful: because the
build is reproducible, the integrity manifest is a stable, checkable
claim rather than a per-run accident, and the frozen release archives can
be guaranteed immutable.

---

## The shape, end to end

```
content/*.yml  +  identity_canonical.json  +  templates/
        │
        ▼  deterministic build (generators)
   public/  ── two authored editions (/en-au/, /fr/) + language gate (/)
        │     + generated trust surfaces (integrity, verify, source, releases)
        ▼  blocking gate + local PGP signing
   signed artefact
        ▼  non-deleting SFTP mirror + smoke test
   live host (Apache + Varnish), same-origin static bytes
```

Everything upstream of `public/` is repo-only build input or machinery;
everything in `public/` is the deployable, verifiable surface. No
request-time code, no database, no third party — just authored content,
turned deterministically into signed static files.
