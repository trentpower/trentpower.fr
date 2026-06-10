# Third-party notices

The published site ships **no third-party code**: no frameworks, no CDN
resources, no external scripts. Third-party material exists only in the
development and verification tooling, and in the licensed typefaces. This
file is a best-effort inventory, maintained by hand.

## Typefaces — Klim Type Foundry (not licensed by this repository)

**Signifier**, **Söhne**, and **Söhne Mono** are licensed from
[Klim Type Foundry](https://klim.co.nz/) under a commercial agreement that
permits serving them on trentpower.fr and prohibits redistribution.

They are therefore **deliberately absent from this repository's tree** (and
from the downloadable release archives, where `EXCLUDED_FILES.json` records
the same omission). The declared list, with the SRI digest of each live
binary, is `metadata/repo-exclusions.json`; a fresh checkout restores them
locally with `tools/build/fetch_licensed_fonts.py`, verified against the
signed `integrity.json`. No licence in this repository grants any right to
these files.

## Open typefaces (frozen release body)

The sealed 2026-02 release under `public/integrity/releases/2026-02/`
carries **IBM Plex Mono** and **Newsreader**, both licensed under the
[SIL Open Font License 1.1](https://openfontlicense.org/) and freely
redistributable.

## npm development dependencies (not shipped)

Used only for advisory source-quality checks; all MIT-licensed:

| Package                   | Licence |
| ------------------------- | ------- |
| eslint, @eslint/js        | MIT     |
| globals                   | MIT     |
| prettier                  | MIT     |
| stylelint                 | MIT     |
| stylelint-config-standard | MIT     |

`pagedjs-cli` (MIT) is fetched on demand by `docs/pdf/build.sh` to paginate
the editorial PDF; it is never vendored or shipped.

## Python and system tooling (build/verify path, not shipped)

| Tool       | Licence      | Role                                                                                                                |
| ---------- | ------------ | ------------------------------------------------------------------------------------------------------------------- |
| ruff       | MIT          | advisory Python lint                                                                                                |
| jsonschema | MIT          | content schema validation (blocking gate)                                                                           |
| Pillow     | MIT-CMU      | image checks                                                                                                        |
| pymupdf    | AGPL-3.0     | README.pdf layout audit — **CI/local verification only; never distributed, never linked into any shipped artefact** |
| shellcheck | GPL-3.0      | advisory shell lint (external binary)                                                                               |
| shfmt      | BSD-3-Clause | advisory shell formatting (external binary)                                                                         |
| lftp       | GPL-3.0      | CI SFTP mirror (external binary)                                                                                    |
| GnuPG      | GPL-3.0      | signing and verification (external binary)                                                                          |
| gitleaks   | MIT          | full-history secret scan — fetched on demand, never vendored                                                        |

External binaries are invoked as tools; nothing in this repository links
against them or redistributes them.
