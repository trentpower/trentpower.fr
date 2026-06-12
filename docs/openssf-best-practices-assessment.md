# OpenSSF Best Practices badge — assessment

Self-assessment against the [OpenSSF Best Practices](https://www.bestpractices.dev/en)
**passing** level, with paste-ready questionnaire answers. Registration
is interactive (GitHub OAuth at bestpractices.dev → "Get Your Badge
Now") and must be done by the maintainer; this document is the prepared
input.

Registered project: <https://www.bestpractices.dev/en/projects/13182>
(registration in progress, 2026-06-12).

No badge is referenced anywhere in the repository until it is actually
earned. The badge, if earned, is repository-posture evidence — like
Scorecard, it is not part of the site's cryptographic proof chain.

## Verdict

The project meets or can honestly claim **most passing-level criteria
today**. Two structural facts to declare plainly in the questionnaire:
it is a single-maintainer publication (affects the "others can
contribute" narrative, not the criteria themselves), and several
criteria aimed at installable software libraries are **N/A** for a
static publication — bestpractices.dev explicitly supports N/A answers
with justification.

## Per-criterion assessment (passing level)

### Basics

| Criterion | Status | Evidence / answer |
| --- | --- | --- |
| Project website | **Met** | https://trentpower.fr |
| Basic project info (what/why) | **Met** | README.md + https://trentpower.fr/en-au/colophon/ |
| Contribution process described | **Met** | CONTRIBUTING.md — issues welcome, PRs generally declined (personal publication); the policy itself is the documented process |
| Contribution requirements | **Met** | CONTRIBUTING.md + .github/PULL_REQUEST_TEMPLATE.md |
| FLOSS license | **Met** | MIT (code) — LICENSE; content CC BY-SA 4.0 — CONTENT-RIGHTS.md |
| License posted in standard location | **Met** | /LICENSE |
| Documentation: basics | **Met** | docs/ — ARCHITECTURE.md, BUILD-AND-DEPLOYMENT.md, TRUST-AND-VERIFICATION.md |
| Documentation: interface | **Met (N/A flavour)** | no API; the "interface" is the published site + verification surface, documented at /en-au/verify/ and docs/TRUST-AND-VERIFICATION.md |
| HTTPS site | **Met** | HSTS on trentpower.fr; GitHub serves the repo over HTTPS |
| Discussion mechanism | **Met** | GitHub Issues (templates in .github/ISSUE_TEMPLATE/) |
| English supported | **Met** | bilingual EN-AU / FR; English primary for engineering docs |
| Project maintained | **Met** | active weekly cadence; declare honestly that the repo became public 2026-06-10 |

### Change control

| Criterion | Status | Evidence / answer |
| --- | --- | --- |
| Public version-controlled repository | **Met** | github.com/trentpower/trentpower.fr |
| Track changes (what/who/when) | **Met** | git history; signed commits; PR-only main |
| Interim versions available for review | **Met** | feature/* and preprod branches are public |
| Unique version numbering | **Met** | edition dates (`YYYY-MM-DD`) are the version scheme; `edition/<date>` tags + GitHub Releases (docs/github-releases.md) |
| Release notes per release | **Met once first Release is cut** | Release body per docs/github-releases.md; identifies user-visible changes |
| Release notes identify fixed vulnerabilities | **Met (vacuously)** | no public vulnerabilities to date; commit to listing CVEs in release notes if any arise |

### Reporting

| Criterion | Status | Evidence / answer |
| --- | --- | --- |
| Bug reporting process | **Met** | GitHub issue templates (broken page, verification issue, documentation correction) |
| Bug tracker archive | **Met** | GitHub Issues |
| Vulnerability reporting process published | **Met** | SECURITY.md + RFC 9116 security.txt + GitHub private vulnerability reporting |
| Private vulnerability reports supported | **Met** | encrypted mail (published PGP key) or GitHub private advisory |
| Initial response time ≤ 14 days | **Commit** | declare 14 days in the questionnaire; single maintainer, realistic |

### Quality — per-criterion (paste-ready)

| Criterion | Status | Justification (paste) |
| --- | --- | --- |
| `build` | **Met** | tools/build/build.sh deterministically rebuilds the site from source; the CI build-check job rebuilds and compares against the committed record on every promotion. |
| `build_common_tools` | **Met** | Standard tooling only: bash, python3, npm. No bespoke build framework. |
| `build_floss_tools` | **Met** | All build tools are FLOSS (bash, Python, Node/npm, GnuPG). Licensed typefaces are content assets fetched and hash-verified at build time, not build tools. |
| `test` | **Met** | FLOSS unittest suite at tools/quality/tests/ (including Hypothesis property-based tests) runs in CI on every pull request (pr-checks.yml, source-quality job); the 36 blocking release-gate checks run on every PR, push and deploy. Invocation documented in docs/fuzzing.md and the PR template. |
| `test_invocation` | **Met** | Standard Python invocation: python3 -m unittest discover -s tools/quality/tests |
| `test_most` | **Met** | Tests cover the shared library primitives (hashing, dates, slugs, URLs, redaction), the template token engine, the badge generator and the check-report machinery; the blocking release gate exercises the entire published artefact on every build. |
| `test_continuous_integration` | **Met** | GitHub Actions runs the test suite and the blocking gate on every pull request and push (pr-checks.yml, publication-check.yml). |
| `test_policy` | **Met** | Policy: new or changed tooling behaviour adds tests to tools/quality/tests/. Stated in the pull request template checklist and docs/fuzzing.md. |
| `tests_are_added` | **Met** | Most recent major change (OpenSSF posture, PR #17) added property-based tests for the surfaces it touched; the prior library consolidation added test_lib_primitives.py. |
| `tests_documented_added` | **Met** | The pull request template checklist requires tests for new or changed tooling behaviour (.github/PULL_REQUEST_TEMPLATE.md). |
| `warnings` | **Met** | ruff (Python), eslint (JS), stylelint (CSS), shellcheck + shfmt (shell) run in CI; CodeQL default setup on top. |
| `warnings_fixed` | **Met** | eslint and stylelint are at zero findings; ruff is clean; CodeQL fix rounds were shipped before the repository opened. Warnings are addressed, not suppressed. |
| `warnings_strict` | **Met** | Linters run with standard-strict configurations (ruff configured in pyproject.toml, stylelint-config-standard); the quality gate has a documented escalation seam (QUALITY_ENFORCE) to make findings blocking. |

### Security — per-criterion (paste-ready)

| Criterion | Status | Justification (paste) |
| --- | --- | --- |
| `know_secure_design` | **Met** | The maintainer designed the site's defence model — strict CSP, SRI, cross-origin isolation, signed integrity manifests, allow-list public exposure — documented in docs/SECURITY-AND-PRIVACY.md. |
| `know_common_errors` | **Met** | XSS countered by context-aware escaping in the template engine (property-tested) and strict CSP; supply-chain errors countered by hash-pinned dependencies and SHA-pinned actions; credential leaks countered by push protection and a blocking history scan. |
| `crypto_published` | **Met** | Only published, standard primitives: SHA-256 manifests, SHA-384 SRI, Ed25519 (SSH commit signing), RSA-4096 PGP detached signatures via GnuPG. |
| `crypto_call` | **Met** | All cryptography is delegated to GnuPG, OpenSSH and Python's hashlib. Nothing is re-implemented. |
| `crypto_floss` | **Met** | GnuPG, OpenSSH and Python hashlib are FLOSS; every verification step is reproducible with FLOSS tools (documented at /en-au/verify/). |
| `crypto_keylength` | **Met** | RSA-4096 PGP key, Ed25519 signing key, SHA-256/SHA-384 digests — all meet NIST minimums through 2030. No weaker configuration exists to disable. |
| `crypto_working` | **Met** | No broken algorithms anywhere in the trust chain (no MD4/MD5, no SHA-1, no DES/RC4). |
| `crypto_weaknesses` | **Met** | No SHA-1 or other weakened algorithms; digests are SHA-256/SHA-384 throughout. |
| `crypto_pfs` | **N/A** | The project implements no key-agreement protocol. TLS (with PFS ciphersuites) is provided by the hosting platform. |
| `crypto_password_storage` | **N/A** | The software stores no passwords and has no user authentication; the published site is static. |
| `crypto_random` | **N/A** | The software generates no cryptographic keys or nonces at runtime. Signing keys were generated locally with GnuPG/OpenSSH standard CSPRNGs. |
| `delivery_mitm` | **Met** | Site and repository are HTTPS-only (HSTS on trentpower.fr); beyond TLS, every published file is covered by the PGP-signed integrity manifest. |
| `delivery_unsigned` | **Met** | All hashes are served over HTTPS and anchored by detached PGP signatures (integrity.json.sig, SHA256SUMS.sig); nothing is retrieved over http. |
| `vulnerabilities_fixed_60_days` | **Met** | No unpatched publicly-known vulnerabilities. The most recent advisories affecting a committed requirements file were fixed the same day they were flagged (2026-06-12). |
| `vulnerabilities_critical_fixed` | **Met** | Same-day remediation is the demonstrated practice; Dependabot, CodeQL and OSV results are reviewed as part of the promotion checklist. |
| `no_leaked_credentials` | **Met** | GitHub secret scanning with push protection is enabled, and a blocking full-history secret scan (tools/verify/scan_git_history.py --strict) runs in CI on every PR. |

### Analysis — per-criterion (paste-ready)

| Criterion | Status | Justification (paste) |
| --- | --- | --- |
| `static_analysis` | **Met** | CodeQL (default setup) analyses every pull request; ruff, eslint, stylelint and shellcheck run in the same CI gate. |
| `static_analysis_common_vulnerabilities` | **Met** | CodeQL runs its security query suites for Python and JavaScript/TypeScript. |
| `static_analysis_fixed` | **Met** | CodeQL findings were fixed in dedicated rounds before the repository opened; no high/critical alerts are open. Review is a promotion-checklist item. |
| `static_analysis_often` | **Met** | On every pull request and push, plus weekly scheduled runs. |
| `dynamic_analysis` | **Met** | Hypothesis property-based tests execute the build tooling on generated adversarial inputs before every release (docs/fuzzing.md), and post-deploy smoke tests exercise the live site (routes, headers, CSP, signature validation) after every production deploy. |
| `dynamic_analysis_unsafe` | **N/A** | No memory-unsafe language in the project (HTML/CSS/JS/Python/Bash only). |
| `dynamic_analysis_enable_assertions` | **Met** | The property-based suite asserts invariants (total escaping, well-formed XML, idempotence) during analysis runs; the published static artefact contains no runtime assertions, by design. |
| `dynamic_analysis_fixed` | **Met** | The one defect found by dynamic analysis to date (XML-invalid control characters passing through the badge escaper) was fixed the same day (see docs/fuzzing.md). |

## Registration steps (maintainer, interactive)

1. https://www.bestpractices.dev/en → "Get Your Badge Now" → sign in
   with the @trentpower GitHub account.
2. Add project: repository URL `https://github.com/trentpower/trentpower.fr`,
   project URL `https://trentpower.fr`.
3. Work through the form with the tables above; use **N/A with the
   stated justification** wherever the criterion assumes an installable
   software package.
4. Save with status visible even while "in progress" — Scorecard's
   CII-Best-Practices check awards partial credit for in-progress ≥
   passing threshold, full passing credit once 100%.
5. When (and only when) the badge reaches **passing**, revisit badge
   display under the local-SVG badge policy — no shields.io, secondary
   "repository checks" group, wording `OpenSSF · Best Practices`,
   per the badge system rules in metadata/badges/badges.json.
