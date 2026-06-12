# Local trust marks

These trust marks are local SVG labels for the GitHub README and the
governance documents. They are generated from repository metadata and
stored under `metadata/badges` so the repository does not depend on an
external badge service. They are descriptive labels, not proof. Proof
remains in the signed manifest, source mirrors and release archives.

Design follows the Trust Marks badge brief: Option 2 colophon marks for
the trust rows, Option 3 proof strip once under the README title. Warm
paper, iron ink, one oxblood hairline, system monospace, no icons. Each
mark carries its own paper surface, so a single SVG reads identically on
GitHub light and dark.

## Model

| Piece | Path |
| --- | --- |
| Source data | `metadata/badges/badges.json` |
| Generator | `tools/badges/generate_badges.py` |
| Validator | `tools/badges/validate_badges.py` (blocking gate `local_badges`) |

Regenerate after editing `badges.json`:

    python3 tools/badges/generate_badges.py
    python3 tools/badges/validate_badges.py

Each mark keeps its destination through the markdown link wrapper, for
example:

    [![Signed: PGP](metadata/badges/signed-pgp.svg)](https://trentpower.fr/en-au/verify/)

The `href` field in `badges.json` records the intended destination per
mark. The validator blocks stale SVGs, scripts or remote references
inside the SVGs, and any return of an external badge service to the
governance files.
