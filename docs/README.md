# Documentation

Reference documentation for **trentpower.fr** — a static, bilingual,
source-verifiable personal publication. Start with the root
[`README.md`](../README.md) for the project overview; the documents below go
deeper on each area.

## Map

| Document                                                   | Covers                                                                                                                                            |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| [ARCHITECTURE.md](ARCHITECTURE.md)                         | Static architecture, the `/en-au/` + `/fr/` authored editions, the `/` language gate, YAML-through-templates authoring, generated trust surfaces. |
| [BUILD-AND-DEPLOYMENT.md](BUILD-AND-DEPLOYMENT.md)         | The numbered build pipeline, file-class taxonomy, build/deploy split, CI secrets model, SFTP mirror, post-deploy smoke test.                      |
| [GATES-CHECKS-AND-QUALITY.md](GATES-CHECKS-AND-QUALITY.md) | The two-tier gate (`gate.py` blocking + `lint.py` advisory), the full check registry, and code-quality tooling.                                   |
| [TRUST-AND-VERIFICATION.md](TRUST-AND-VERIFICATION.md)     | `integrity.json` + signature, the published PGP key, source mirrors, frozen release archives, and how to verify the site independently.           |
| [SECURITY-AND-PRIVACY.md](SECURITY-AND-PRIVACY.md)         | Privacy constraints, CSP + cross-origin isolation, the public-exposure allow-list, and local secret handling.                                     |
| [CONTENT-MODEL.md](CONTENT-MODEL.md)                       | The editorial YAML model, the routes registry, English auto-regeneration vs hand-edited French, and the template → generated-JS relationship.     |
| [OPERATIONS.md](OPERATIONS.md)                             | Edition/asset/CSP maintenance procedures, post-deploy tests, service-worker recovery, and caching policy.                                         |
| [INCIDENT-RESPONSE.md](INCIDENT-RESPONSE.md)               | Incident types, detection, and the response playbook.                                                                                             |
| [SCORE-LEDGER.md](SCORE-LEDGER.md)                         | The local-only live-site audit tool (observational, not a deploy gate).                                                                           |
| [PUBLIC-READINESS.md](PUBLIC-READINESS.md)                 | What must never be committed, `.gitignore` policy, the public-release record, and the blocking `public_readiness` gate.                           |

Licensing for the repository lives at the root: [`LICENSE`](../LICENSE) (code,
MIT), [`LICENSE-CONTENT.md`](../LICENSE-CONTENT.md) (authored content,
CC BY-SA 4.0), with [`NOTICE.md`](../NOTICE.md) as the map and
[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) covering tooling and the
licensed typefaces.

## Reference documents (kept standalone)

| Document                                                         | Why standalone                                                                              |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| [authorship-statement.md](authorship-statement.md)               | AI/tool-usage policy; its path is allow-listed by `tools/quality/validate_git_metadata.py`. |
| [public-artefact-conventions.md](public-artefact-conventions.md) | Public-artefact schema referenced by site-metadata validators.                              |
| [htaccess-future-bilingual.md](htaccess-future-bilingual.md)     | Forward-looking `.htaccess` plan (future work, not yet shipped).                            |
