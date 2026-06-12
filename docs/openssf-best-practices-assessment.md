# OpenSSF Best Practices badge — questionnaire answers

The complete answer set for the [OpenSSF Best Practices](https://www.bestpractices.dev/en)
**passing**-level questionnaire, in form order, in the maintainer's own
voice. Each entry gives the criterion id, the selected status, and the
justification text as entered.

Registered project: <https://www.bestpractices.dev/en/projects/13182>

No badge is referenced anywhere in the repository until it is actually
earned. The badge, if earned, is repository-posture evidence — like
Scorecard, it is not part of the site's cryptographic proof chain.

## General

| Field | Entry |
| --- | --- |
| Name | trentpower.fr |
| Description | A bilingual (English/French) personal publication, built as a static site whose every published file can be verified against a signed integrity manifest. The repository is the complete, inspectable record of how it is built, checked and released. |
| Entry language | English (en) |
| Project URL | https://trentpower.fr |
| Repository URL | https://github.com/trentpower/trentpower.fr |
| License | MIT (code; the written content is CC-BY-SA-4.0, noted in CONTENT-RIGHTS.md) |
| Implementation languages | HTML, CSS, JavaScript, Python, Shell |
| CPE | — |
| Other comments | This is a single-author publication system, not a library meant to be installed. Where a criterion assumes a software package, I have answered for the build and verification tooling, which is where the executable code lives. |

## Basics

**description_good — Met.** The README and the site itself say what this
is: a personal publication where every published file can be checked
against a signed manifest. The problem it solves is trust — a reader
never has to take the content's integrity on faith.

**interact — Met.** The README links the site, the repository and the
issue templates. Issues are open for bug reports and corrections;
SECURITY.md and security.txt cover the private route.

**contribution — Met.** CONTRIBUTING.md is candid about the process:
issues are welcome, pull requests are generally declined because this is
an authored publication. That policy is the contribution process, stated
up front. <https://github.com/trentpower/trentpower.fr/blob/main/CONTRIBUTING.md>

**contribution_requirements — Met.** CONTRIBUTING.md and the pull
request template set out what an acceptable change looks like: signed
commits, the build check passing, no attribution trailers, tests for
tooling changes. <https://github.com/trentpower/trentpower.fr/blob/main/.github/PULL_REQUEST_TEMPLATE.md>

**floss_license — Met.** All code and tooling are MIT. The prose content
is CC-BY-SA-4.0, recorded separately in CONTENT-RIGHTS.md.

**floss_license_osi — Met.** MIT is OSI-approved.

**license_location — Met.** <https://github.com/trentpower/trentpower.fr/blob/main/LICENSE>

**documentation_basics — Met.** docs/ carries the architecture, build,
deployment and trust-model documentation; the README is the front door.

**documentation_interface — Met.** There is no API. The external
interface is the published site and its verification surface, documented
at <https://trentpower.fr/en-au/verify/> and in
docs/TRUST-AND-VERIFICATION.md.

**sites_https — Met.** The site is HTTPS-only with HSTS; the repository
is served by GitHub over HTTPS.

**discussion — Met.** GitHub Issues, with structured templates.
Searchable, URL-addressable, no proprietary client needed.

**english — Met.** The site is bilingual, but all engineering
documentation is in English and I take bug reports in English.

**maintained — Met.** Actively maintained — weekly dependency review,
scheduled security scans, and editions published on an ongoing cadence.
The repository became public on 2026-06-10; the private history before
that was just as alive.

## Change Control

**repo_public — Met.** <https://github.com/trentpower/trentpower.fr>

**repo_track — Met.** Full git history, every commit signed and
attributed to me. Main only moves by pull request.

**repo_interim — Met.** Work lands on feature branches, graduates to a
preprod branch, and is promoted to main. All three stages are public;
nothing appears as a finished release out of nowhere.

**repo_distributed — Met.** git.

**version_unique — Met.** Each release is an edition, identified by its
date. Editions are tagged (edition/YYYY-MM-DD) and their frozen archives
live under /integrity/releases/ permanently.

**version_semver — Met.** Calendar versioning: the edition date is the
version. For a publication, the date is the honest version number —
there is no API surface for semver to describe.

**version_tags — Met.** Signed annotated tags, edition/YYYY-MM-DD,
protected by a tag ruleset so they cannot be moved or deleted.

**release_notes — Met.** Each GitHub Release describes the edition in
prose and points at the canonical signed record.
<https://github.com/trentpower/trentpower.fr/releases>

**release_notes_vulns — N/A.** No publicly known vulnerability has
existed in this project. If one ever does, the release notes for the
fixing edition will name it.

## Reporting

**report_process — Met.** GitHub Issues with templates for broken pages,
verification problems and documentation corrections.
<https://github.com/trentpower/trentpower.fr/issues>

**report_tracker — Met.** GitHub Issues is the tracker.

**report_responses — Met.** I am the sole maintainer and I respond to
what arrives. The repository is young and low-traffic; nothing has gone
unanswered.

**enhancement_responses — Met.** Same answer — enhancement requests get
a response, even when the response is a polite no, since this is an
authored publication.

**report_archive — Met.** <https://github.com/trentpower/trentpower.fr/issues>
— open and closed issues stay public.

**vulnerability_report_process — Met.** SECURITY.md and the RFC 9116
security.txt at <https://trentpower.fr/.well-known/security.txt> both
publish the route.
<https://github.com/trentpower/trentpower.fr/blob/main/SECURITY.md>

**vulnerability_report_private — Met.** Two private routes: encrypted
mail using the published PGP key, or GitHub private vulnerability
reporting. <https://github.com/trentpower/trentpower.fr/security/advisories/new>

**vulnerability_report_response — Met.** No vulnerability reports have
been received. My committed initial-response window is 14 days, stated
in SECURITY.md, and as sole maintainer I expect to beat it comfortably.

## Quality

**build — Met.** tools/build/build.sh rebuilds the whole site from
source, deterministically. CI rebuilds it independently on every
promotion and compares the result against the committed record.

**build_common_tools — Met.** bash, python3 and npm. Nothing exotic.

**build_floss_tools — Met.** Every build tool is FLOSS. The licensed
typefaces are content, not tooling — the build fetches them and verifies
every byte against the signed manifest.

**test — Met.** A unittest suite under tools/quality/tests/ — including
Hypothesis property-based tests — runs in CI on every pull request,
alongside 36 blocking release-gate checks. How to run it is in
docs/fuzzing.md and the PR template:
`python3 -m unittest discover -s tools/quality/tests`

**test_invocation — Met.** The standard Python way:
`python3 -m unittest discover -s tools/quality/tests`

**test_most — Met.** The tests cover the shared library primitives, the
template token engine, the badge generator and the check-report
machinery; the blocking release gate then exercises the entire published
artefact on every build. Between the two, little ships unexamined.

**test_continuous_integration — Met.** GitHub Actions runs the suite and
the gate on every pull request and push.

**test_policy — Met.** The policy is written into the pull request
template: new or changed tooling behaviour brings tests with it.

**tests_are_added — Met.** The most recent significant change added
property-based tests for exactly the surfaces it touched — and the first
run of those tests found and fixed a real escaping bug, which is the
policy doing its job.

**tests_documented_added — Met.** It is a checklist line in
.github/PULL_REQUEST_TEMPLATE.md, so every change proposal restates it.

**warnings — Met.** ruff for Python, eslint for JavaScript, stylelint
for CSS, shellcheck and shfmt for shell — all in CI, with CodeQL on top.

**warnings_fixed — Met.** The linters run at zero findings and I keep
them there. CodeQL's findings were fixed in dedicated rounds before the
repository opened.

**warnings_strict — Met.** Standard-strict configurations, and the
quality gate has a documented switch (QUALITY_ENFORCE) to turn any
finding into a blocker.

## Security

**know_secure_design — Met.** I designed the site's defence model
myself — strict CSP, subresource integrity, cross-origin isolation,
signed manifests, an allow-list of what the server may expose — and
wrote it up in docs/SECURITY-AND-PRIVACY.md.

**know_common_errors — Met.** The mitigations show the awareness:
context-aware escaping in the template engine (property-tested) against
XSS, hash-pinned dependencies and SHA-pinned actions against
supply-chain drift, push protection and a blocking history scan against
leaked credentials.

**crypto_published — Met.** Standard, published primitives only:
SHA-256 manifests, SHA-384 subresource integrity, Ed25519 commit
signing, RSA-4096 PGP signatures via GnuPG.

**crypto_call — Met.** Everything cryptographic is delegated to GnuPG,
OpenSSH and Python's hashlib. I have re-implemented nothing.

**crypto_floss — Met.** GnuPG, OpenSSH and hashlib are all FLOSS, and
the published verification guide walks through the whole chain using
only those tools.

**crypto_keylength — Met.** RSA-4096, Ed25519 and SHA-256/384 all clear
the NIST 2030 minimums. There is no weaker mode to configure.

**crypto_working — Met.** Nothing in the trust chain touches a broken
algorithm — no MD5, no SHA-1, no DES or RC4.

**crypto_weaknesses — Met.** Digests are SHA-256 and SHA-384 throughout;
SHA-1 appears nowhere.

**crypto_pfs — N/A.** I implement no key-agreement protocol. TLS, with
its forward-secret ciphersuites, belongs to the hosting layer.

**crypto_password_storage — N/A.** There are no users to authenticate
and no passwords to store; the published site is static.

**crypto_random — N/A.** The software generates no keys or nonces at
runtime. My signing keys were generated locally by GnuPG and OpenSSH
with their standard CSPRNGs.

**delivery_mitm — Met.** HTTPS with HSTS on the site, HTTPS at GitHub —
and beneath TLS, every published file is covered by the PGP-signed
integrity manifest, so tampering is detectable even past the transport.

**delivery_unsigned — Met.** Hashes are served over HTTPS and anchored
by detached PGP signatures; there is no http anywhere in the chain.

**vulnerabilities_fixed_60_days — Met.** None outstanding. The last
advisories that touched a committed requirements file were fixed the
same day the scanner raised them.

**vulnerabilities_critical_fixed — Met.** Same-day turnaround is the
demonstrated practice, and reviewing Dependabot, CodeQL and OSV results
is a written step in the promotion checklist.

**no_leaked_credentials — Met.** GitHub secret scanning with push
protection, plus my own blocking scan of the full git history on every
pull request. Signing keys have never been in the repository — that
boundary is part of the design.

## Analysis

**static_analysis — Met.** CodeQL analyses every pull request; ruff,
eslint, stylelint and shellcheck run in the same gate.

**static_analysis_common_vulnerabilities — Met.** CodeQL runs its
security query suites for Python and JavaScript.

**static_analysis_fixed — Met.** CodeQL's findings were fixed in
dedicated rounds before the repository went public, and no high or
critical alerts are open. Reviewing them stays on the promotion
checklist.

**static_analysis_often — Met.** Every pull request, every push, plus a
weekly scheduled run.

**dynamic_analysis — Met.** Two kinds: Hypothesis property-based tests
drive the build tooling with generated adversarial input before every
release, and post-deploy smoke tests exercise the live site — routes,
headers, CSP, signature validation — after every production deploy.

**dynamic_analysis_unsafe — N/A.** Nothing here is written in a
memory-unsafe language — HTML, CSS, JavaScript, Python and shell only.

**dynamic_analysis_enable_assertions — Met.** The property tests are
built from assertions — escaping must be total, generated SVG must stay
well-formed, slugs must be idempotent. The published static site carries
no runtime assertions, deliberately.

**dynamic_analysis_fixed — Met.** Dynamic analysis has found one defect
so far — control characters slipping through the badge escaper into
SVG — and it was fixed the same day. docs/fuzzing.md tells that story.

## After the badge

When (and only when) the entry reaches **passing**, badge display
follows the local-SVG badge policy: no external badge service, secondary
"repository checks" group, wording `OpenSSF · Best Practices` — tracked
in issue #18.
