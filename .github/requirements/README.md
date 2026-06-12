# CI requirements

Hash-pinned Python dependency sets for GitHub-hosted runners. One file per CI
job surface, so privileged jobs install only what they use:

| File | Consumed by |
| --- | --- |
| `release-gate.txt` | `pr-checks.yml` (release-gate), `publication-check.yml` (release-gate-main), `deploy.yml`, `preprod-deploy.yml` |
| `build-check.txt` | `publication-check.yml` (build-check) |
| `visual-qa.txt` | `publication-check.yml` (visual-qa) |
| `source-quality.txt` | `pr-checks.yml` (source-quality) |

The `.in` files are the human-edited sources; the `.txt` files are compiled
with per-artifact SHA-256 hashes and installed with `pip install
--require-hashes`. Dependabot regenerates the compiled files weekly.

Regenerate after editing an `.in` file:

```sh
pip-compile --generate-hashes --strip-extras --allow-unsafe -o <name>.txt <name>.in
```

These pins exist for CI reproducibility (OpenSSF Pinned-Dependencies). The
loosely pinned `tools/requirements.txt` files are a separate, deliberate
choice for portability on the local build machine.
