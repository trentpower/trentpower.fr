# OpenSSF Best Practices badge — assessment

Self-assessment against the [OpenSSF Best Practices](https://www.bestpractices.dev/en)
**passing** level, with paste-ready questionnaire answers. Registration
is interactive (GitHub OAuth at bestpractices.dev → "Get Your Badge
Now") and must be done by the maintainer; this document is the prepared
input.

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

### Quality

| Criterion | Status | Evidence / answer |
| --- | --- | --- |
| Working build system | **Met** | tools/build/build.sh — deterministic, gated |
| Automated test suite | **Met** | unittest suite (tools/quality/tests/, runs in pr-checks.yml) + the blocking release gate (tools/verify/validate_release.py) executed on every PR, push and deploy |
| New functionality adds tests (policy) | **Met** | declare as policy; fuzz/property tests added with the tooling they cover (docs/fuzzing.md) |
| Warning flags / linters enabled | **Met** | ruff, eslint, stylelint, shellcheck, shfmt in source-quality job; CodeQL default setup |

### Security

| Criterion | Status | Evidence / answer |
| --- | --- | --- |
| Secure development knowledge | **Met** | declare yes — CSP/SRI/signing architecture documented in docs/SECURITY-AND-PRIVACY.md is the demonstration |
| Good cryptographic practices | **Met** | SHA-256 manifests, SHA-384 SRI, Ed25519 SSH commit signing, PGP (RSA-4096 class) detached signatures; no homegrown crypto |
| Secured delivery against MITM | **Met** | HTTPS + HSTS; signed integrity manifest; SRI on assets |
| No unpatched publicly-known vulnerabilities | **Met** | 0 open Dependabot alerts; OSV-checked npm lockfile + hash-pinned CI Python deps (2026-06-12) |
| No leaked credentials | **Met** | secret scanning + push protection + tools/verify/scan_git_history.py --strict in CI |

### Analysis

| Criterion | Status | Evidence / answer |
| --- | --- | --- |
| Static analysis | **Met** | CodeQL (default setup) + ruff/eslint/stylelint |
| Static analysis for vulnerabilities | **Met** | CodeQL security queries |
| Dynamic analysis | **Met via property testing** | Hypothesis property-based tests fuzz the build-tooling parsers (docs/fuzzing.md); declare honestly that the shipped artefact is static HTML with no runtime to dynamically analyse |
| Dynamic analysis on memory-unsafe code | **N/A** | no C/C++/unsafe code in the project |

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
