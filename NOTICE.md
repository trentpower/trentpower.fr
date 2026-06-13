# Notice

This repository carries two licences, applied by kind of material, plus one
deliberate exception. This file is the map.

## Code — MIT

The software is licensed under the [MIT License](LICENSE):

- `tools/` — build pipeline, gates, validators, release and verify tooling
- `templates/` — JS build inputs and page templates
- `styles/` — authored CSS source
- `schemas/` — JSON Schema definitions
- `.github/` — deployment workflow
- generated CSS/JS under `public/` (derived from the sources above)

## Authored content — CC BY-SA 4.0

The authored content is licensed under
[Creative Commons Attribution-ShareAlike 4.0 International](CONTENT-RIGHTS.md):

- `content/` — the editorial source (YAML)
- the published page prose under `public/` (`/en-au/`, `/fr/`)
- the prose documentation under `docs/` and `README.pdf`

Attribution format: **Trent Power, trentpower.fr**, with the canonical URL of
the reused page where one exists. Adaptations carry the same licence.

## The exception — licensed typefaces

The Klim Type Foundry fonts (Signifier, Söhne, Söhne Mono) are commercially
licensed for serving on trentpower.fr only. They are **not** included in this
repository's tree and **no licence in this repository applies to them**. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
`metadata/repo-exclusions.json`.

## Not licensed

- The author's name, identity, likeness, and signature artwork.
- Private keys, credentials, and operational secrets — none are included in
  this repository, and nothing here grants any.

## Verification artefacts

The public verification artefacts (`integrity.json`, detached signatures,
release manifests, checksums) may be freely reused for verification and
citation purposes.

## Third-party material

Third-party dependencies retain their own licences; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Machine-readable licensing (REUSE)

This map is also machine-readable. The repository follows the
[REUSE Specification](https://reuse.software): every tracked file resolves to a
licence and copyright through [`REUSE.toml`](REUSE.toml) (bulk annotations, so
source files stay clean) and the full licence texts live in
[`LICENSES/`](LICENSES/). The author likeness/identity assets carry
`LicenseRef-trentpower-personal` (the "not licensed" status above, made
explicit). Compliance is checked in CI (`reuse lint`).
