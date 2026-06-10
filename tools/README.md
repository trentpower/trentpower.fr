# tools/

The build, validation, signing, and verification pipeline for trentpower.fr.
Not deployed to the live host: `/tools/` is 403'd at the Apache layer and the
SFTP mirror only uploads `public/`.

Each directory answers one question.

| Directory       | Question it answers              | Holds                                                                                                                                                                                                                                                                                          |
| --------------- | -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `build/`        | What creates the website?        | generators, renderers, the SRI/integrity/source-mirror writers, the build cockpit, and `build.sh`. Sub-dirs: `copy/` (bilingual copy → `strings.json`), `fonts/` (subset glyph lists), `assets/` (editorial reference docx).                                                                   |
| `quality/`      | What stops a bad release?        | `gate.py` (blocking) and `lint.py` (advisory), every `validate_*` policy/content/hygiene check, `inline_checks.py` (inline cross-cutting check functions, registered via `lib/checks.py`), `quality.sh`, `csp-hashes.sh`. Sub-dirs: `pdf/` (PDF layout gate), `tests/` (toolchain unit tests). |
| `verify/`       | How do I know it's genuine?      | read-only integrity, signature, source-mirror, release, and git-history verification.                                                                                                                                                                                                          |
| `release/`      | How does it become public?       | `build_release_archives.py`, `seal_edition.py`, `deploy.sh`, `deploy.sftp.lftp`, and `server/` (server-only files, never deployed).                                                                                                                                                            |
| `config/`       | What does the pipeline read?     | the declared facts: `identity_canonical.json`, `public-exposure.json`, `source-mirror-exclusions.json`, `date_overrides.json`.                                                                                                                                                                 |
| `lib/`          | What is shared across pillars?   | `paths.py`, `checks.py`, `minify.py`, `htaccess_config.py`, `sizes.py`, `public_inventory.py`, `public_tree.py`, `check_report.py`, `routes.py`.                                                                                                                                              |
| `score-ledger/` | What merely observes?            | a local-only live-site audit. Never a build gate. See [`docs/SCORE-LEDGER.md`](../docs/SCORE-LEDGER.md).                                                                                                                                                                                       |
| `_retired/`     | What is kept for reference only? | superseded one-offs, out of the release path. See [`_retired/README.md`](_retired/README.md).                                                                                                                                                                                                  |

Authored design source CSS lives in repo-root [`styles/`](../styles), a peer of
`templates/`, not under `tools/`.

## Entry points

```sh
bash tools/build/build.sh --check       # build + run the deploy gate (no re-signing)
bash tools/build/build.sh               # full signed release build
bash tools/quality/quality.sh --check   # source format + lint
python3 tools/quality/gate.py           # blocking checks
python3 tools/quality/lint.py           # advisory checks
python3 tools/verify/validate_release.py  # verify the signed release archive
```

Every script resolves its own absolute paths through `tools/lib/paths.py`, so the
pipeline runs from any working directory.

## Canonical reference

The full pipeline — numbered stages, the file-class taxonomy, the two-tier gate
(`gate.py` blocking + `lint.py` advisory, driven by `checks.py`), and the
build/deploy split — is documented in
[`docs/BUILD-AND-DEPLOYMENT.md`](../docs/BUILD-AND-DEPLOYMENT.md).

## Signing boundary

The private signing key is local only. `build.sh` signs `integrity.json` on the
maintainer's machine; CI verifies that signature against the published public key
in an isolated keyring and never holds or needs the private key.

## Conventions

- New scripts import directory roots from `lib/paths.py` rather than recomputing
  them inline (`REPO_ROOT`, `PUBLIC_DIR`, `TOOLS_DIR`, `STYLES_DIR`, `CONFIG_DIR`).
- A bare script invoked by the gate is resolved to its pillar by `checks.py`; new
  validators only need to land in the correct directory.
