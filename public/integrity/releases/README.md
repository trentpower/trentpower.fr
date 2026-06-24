# Edition archives

Historical edition archive **binaries** (`trentpower-fr-<edition>.zip` and
`trentpower-fr-<edition>.tar.gz`) are **not stored in this Git repository**.

The canonical archive store is the live site:

  https://trentpower.fr/integrity/releases/

Git is kept deliberately lightweight so the GitHub source download stays small
enough to unzip and build locally. What remains in Git for every edition is the
**verification record**, not the payload:

- `trentpower-fr-<edition>.zip.sha256` / `.tar.gz.sha256` — the immutable hash
  of each archive (this is what you verify a downloaded archive against)
- `*.sig` — detached signatures over the archives and their checksums
- `SHA256SUMS` / `SHA256SUMS.sig` — aggregate checksums
- `integrity-redistributable.json` (+ `.sig`) — the manifest describing the
  archive contents
- `release.json`, `builds.json`, `EXCLUDED_FILES.*`, `TESTRESULTS.txt`, the
  per-edition `index.html`

Because the checksums and signatures live in Git, you can verify a
server-downloaded archive without trusting the server: the bytes must match a
hash that was committed and signed here.

## Verifying a server archive

    ed=2026-06-21
    base="https://trentpower.fr/integrity/releases/$ed"
    curl -fLO "$base/trentpower-fr-$ed.zip"
    # compare against the checksum committed in this repo:
    sha256sum trentpower-fr-$ed.zip
    cat trentpower-fr-$ed.zip.sha256   # (from this repo)

See `docs/REPRODUCIBILITY.md` and `docs/TRUST-AND-VERIFICATION.md` for the full
verification procedure, and `index.json` in this directory for the
machine-readable archive policy.
