# Documentation

Reference documentation for **trentpower.fr** — a static, bilingual,
source-verifiable personal publication. Start with the root
[`README.md`](../README.md) for the project overview; the documents below go
deeper on each area.

## Map

| Document                                                       | Covers                                                                                                                                            |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| [ARCHITECTURE.md](ARCHITECTURE.md)                             | Static architecture, the `/en-au/` + `/fr/` authored editions, the `/` language gate, YAML-through-templates authoring, generated trust surfaces. |
| [BUILD-AND-DEPLOYMENT.md](BUILD-AND-DEPLOYMENT.md)             | The numbered build pipeline, file-class taxonomy, build/deploy split, CI secrets model, SFTP mirror, post-deploy smoke test.                      |
| [GATES-CHECKS-AND-QUALITY.md](GATES-CHECKS-AND-QUALITY.md)     | The two-tier gate (`gate.py` blocking + `lint.py` advisory), the full check registry, and code-quality tooling.                                   |
| [TRUST-AND-VERIFICATION.md](TRUST-AND-VERIFICATION.md)         | `integrity.json` + signature, the published PGP key, source mirrors, frozen release archives, and how to verify the site independently.           |
| [SECURITY-AND-PRIVACY.md](SECURITY-AND-PRIVACY.md)             | Privacy constraints, CSP + cross-origin isolation, the public-exposure allow-list, and local secret handling.                                     |
| [CONTENT-MODEL.md](CONTENT-MODEL.md)                           | The editorial YAML model, the routes registry, English auto-regeneration vs hand-edited French, and the template → generated-JS relationship.     |
| [OPERATIONS.md](OPERATIONS.md)                                 | Edition/asset/CSP maintenance procedures, post-deploy tests, service-worker recovery, and caching policy.                                         |
| [INCIDENT-RESPONSE.md](INCIDENT-RESPONSE.md)                   | Incident types, detection, and the response playbook.                                                                                             |
| [SCORE-LEDGER.md](SCORE-LEDGER.md)                             | The local-only live-site audit tool (observational, not a deploy gate).                                                                           |
| [PUBLIC-READINESS.md](PUBLIC-READINESS.md)                     | What must never be committed, `.gitignore` policy, the public-release record, and the blocking `public_readiness` gate.                           |
| [GITHUB-ENVIRONMENTS.md](GITHUB-ENVIRONMENTS.md)               | The GitHub environment model: branches, `production`/`preproduction` secret scoping, the promotion process, and the verify-never-sign boundary.   |
| [GITHUB-RULESETS.md](GITHUB-RULESETS.md)                       | Branch/tag rulesets protecting the public record, GitHub Releases as secondary pointers, commit attribution, and the manual-settings checklist.   |
| [PROVENANCE.md](PROVENANCE.md)                                 | Release provenance: the GitHub build-provenance attestation cut on edition tags, Sigstore/Rekor, and how a third party verifies it.               |
| [REPRODUCIBILITY.md](REPRODUCIBILITY.md)                       | How to rebuild an edition from source, what is byte-deterministic, and the deliberate non-determinism (PGP salt, licensed fonts).                 |
| [SECRETS-AND-KEY-MANAGEMENT.md](SECRETS-AND-KEY-MANAGEMENT.md) | Where the few secrets and keys live, who can access them, and the rotation, revocation and re-keying policy.                                      |
| [CODE-REVIEW.md](CODE-REVIEW.md)                               | What every change is checked against before it reaches the public record; the maintainer self-review checklist.                                   |
| [RELEASE.md](RELEASE.md)                                       | Map of the release path (build → gate → promote → tag → deploy), the local `make` commands, and what each artefact proves.                        |
| [SECURITY-PIPELINE.md](SECURITY-PIPELINE.md)                   | Map of the supply-chain controls and the `claims_parity` honesty gate that binds public claims to passing automated checks.                       |

Licensing for the repository lives at the root: [`LICENSE`](../LICENSE) (code,
MIT), [`CONTENT-RIGHTS.md`](../CONTENT-RIGHTS.md) (authored content,
CC BY-SA 4.0), with [`NOTICE.md`](../NOTICE.md) as the map and
[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) covering tooling and the
licensed typefaces.

Machine-readable security artefacts (the VEX) live under
[`../security/`](../security/); the dependency (SCA) and static-analysis (SAST)
policies they support are in [SECURITY-AND-PRIVACY.md](SECURITY-AND-PRIVACY.md).

## Reference documents (kept standalone)

| Document                                                         | Why standalone                                                                              |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| [AUTHORSHIP-STATEMENT.md](AUTHORSHIP-STATEMENT.md)               | AI/tool-usage policy; its path is allow-listed by `tools/quality/validate_git_metadata.py`. |
| [PUBLIC-ARTEFACT-CONVENTIONS.md](PUBLIC-ARTEFACT-CONVENTIONS.md) | Public-artefact schema referenced by site-metadata validators.                              |
| [HTACCESS-FUTURE-BILINGUAL.md](HTACCESS-FUTURE-BILINGUAL.md)     | Forward-looking `.htaccess` plan (future work, not yet shipped).                            |
