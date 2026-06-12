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

| Field                    | Entry                                                                                                                                                                                                                                                  |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Name                     | trentpower.fr                                                                                                                                                                                                                                          |
| Description              | A bilingual (English/French) personal publication, built as a static site whose every published file can be verified against a signed integrity manifest. The repository is the complete, inspectable record of how it is built, checked and released. |
| Entry language           | English (en)                                                                                                                                                                                                                                           |
| Project URL              | https://trentpower.fr                                                                                                                                                                                                                                  |
| Repository URL           | https://github.com/trentpower/trentpower.fr                                                                                                                                                                                                            |
| License                  | MIT (code; the written content is CC-BY-SA-4.0, noted in CONTENT-RIGHTS.md)                                                                                                                                                                            |
| Implementation languages | HTML, CSS, JavaScript, Python, Shell                                                                                                                                                                                                                   |
| CPE                      | —                                                                                                                                                                                                                                                      |
| Other comments           | This is a single-author publication system, not a library meant to be installed. Where a criterion assumes a software package, I have answered for the build and verification tooling, which is where the executable code lives.                       |

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

The **passing** badge was achieved on 2026-06-12. Per the local-SVG
badge policy, it is displayed as a locally generated badge
(metadata/badges/openssf-best-practices.svg) linking to the project
entry — no external badge service.

---

# Silver level

The complete answer set for the silver-level questionnaire, in form
order. Same voice, same rule: nothing claimed that the repository does
not back.

## Basics (silver)

**achieve_passing — Met.** Passing achieved 2026-06-12.

**contribution_requirements — Met.** (Carried from passing.)

**dco — Unmet.** Every commit is authored and signed by the sole
copyright holder, so a sign-off ritual would certify a fact already
established by the signature on each commit. If outside contributions
were ever accepted, a DCO would come with them.

**governance — Met.** GOVERNANCE.md states the model plainly: the
maintainer decides, the machinery keeps it honest, and declined
alternatives are on the record.
<https://github.com/trentpower/trentpower.fr/blob/main/GOVERNANCE.md>

**code_of_conduct — Met.**
<https://github.com/trentpower/trentpower.fr/blob/main/CODE_OF_CONDUCT.md>

**roles_responsibilities — Met.** GOVERNANCE.md names the roles and who
holds them; CODEOWNERS maps the trust-critical surfaces.
<https://github.com/trentpower/trentpower.fr/blob/main/GOVERNANCE.md>

**access_continuity — Met.** GOVERNANCE.md documents the continuity
arrangement: credentials and key passphrases in a password manager with
emergency access for next of kin, redistributable signed archives, and
licenses (MIT, CC-BY-SA-4.0) that let anyone continue or fork the
record without permission.
<https://github.com/trentpower/trentpower.fr/blob/main/GOVERNANCE.md>

**bus_factor — Unmet.** The bus factor is 1 and I say so rather than
inflate it. GOVERNANCE.md documents what survives me: the verifiable
record, the archives, and the rights to fork.
<https://github.com/trentpower/trentpower.fr/blob/main/GOVERNANCE.md>

**documentation_roadmap — Met.** docs/ROADMAP.md covers the next year —
including, deliberately, what the project will not do.
<https://github.com/trentpower/trentpower.fr/blob/main/docs/ROADMAP.md>

**documentation_architecture — Met.**
<https://github.com/trentpower/trentpower.fr/blob/main/docs/ARCHITECTURE.md>

**documentation_security — Met.** What a reader can and cannot expect is
written down: integrity and authenticity guaranteed and verifiable,
privacy by absence of tracking, availability explicitly not promised.
<https://github.com/trentpower/trentpower.fr/blob/main/docs/ASSURANCE-CASE.md>

**documentation_quick_start — Met.** The fastest useful thing a new
user can do is verify the record; the guide walks it end to end.
<https://trentpower.fr/en-au/verify/>

**documentation_current — Met.** Keeping docs aligned with the
architecture is a line item in the public-readiness checklist, and doc
drift is treated as a defect.

**documentation_achievements — Met.** The README links the badge entry
via a locally generated badge.
<https://github.com/trentpower/trentpower.fr#trentpowerfr>

**accessibility_best_practices — Met.** Semantic HTML with landmarks,
sufficient contrast, and accessibility findings from the live-site
audits are tracked and resolved; every badge SVG carries title and
description for assistive tech.

**internationalization — Met.** The site is fully bilingual (EN-AU and
FR), localized at build time from a curated string set.

**sites_password_security — N/A.** No project site stores passwords;
there is no authentication anywhere.

## Change Control (silver)

**maintenance_or_update — Met.** Editions are additive: every previous
edition's frozen archive remains published under /integrity/releases/
with its own manifest and signature, permanently. Nothing is purged.

## Reporting (silver)

**report_tracker — Met.** GitHub Issues.

**vulnerability_report_credit — N/A.** No vulnerabilities have been
resolved; reporters will be credited in release notes unless they ask
otherwise.

**vulnerability_response_process — Met.** SECURITY.md sets the channel
and the 14-day window; docs/INCIDENT-RESPONSE.md sets what happens
next.
<https://github.com/trentpower/trentpower.fr/blob/main/docs/INCIDENT-RESPONSE.md>

## Quality (silver)

**coding_standards — Met.** The style is codified in tool
configuration — ruff in pyproject.toml, eslint and stylelint configs,
shfmt — and docs/GATES-CHECKS-AND-QUALITY.md explains the two-tier
gate that applies them.
<https://github.com/trentpower/trentpower.fr/blob/main/docs/GATES-CHECKS-AND-QUALITY.md>

**coding_standards_enforced — Met.** The source-quality CI job runs the
full lint set in enforcing mode (QUALITY_ENFORCE=1): findings fail the
job.

**build_standard_variables — N/A.** No native binaries are built.

**build_preserve_debug — N/A.** Nothing is compiled or stripped; the
published files are their own source, mirrored byte-for-byte under
/source/.

**build_non_recursive — Met.** One top-level build script orchestrates
ordered stages; there are no recursive sub-builds.

**build_repeatable — Met.** The CI build-check job independently repeats
the build and compares it against the committed record on every
promotion.

**installation_common — N/A.** The product is a published website;
there is nothing to install. Release archives are plain tar/zip.

**installation_standard_variables — N/A.** No installation system.

**installation_development_quick — Met.** git clone, npm ci, pip install
the hash-pinned requirements, then bash tools/build/build.sh --check —
documented in docs/BUILD-AND-DEPLOYMENT.md.

**external_dependencies — Met.** package-lock.json and the compiled
requirements files under .github/requirements/ list every dependency
with exact versions and hashes, machine-readably.
<https://github.com/trentpower/trentpower.fr/tree/main/.github/requirements>

**dependency_monitoring — Met.** Weekly Dependabot across npm, pip and
GitHub Actions, OSV checks, and nothing merges without review.

**updateable_reused_components — Met.** Everything external arrives
through a lockfile or a hash-pinned requirements file; updating a
component is a one-line bump that Dependabot usually proposes first.

**interfaces_current — Met.** The enforced linters flag deprecated
usage, and the stack is deliberately small and current.

**automated_integration_testing — Met.** Every push and pull request
runs the suite and the gate; results are reported on the commit and the
run summary.

**regression_tests_added50 — Met.** Every bug fixed since the suite
existed has a regression property in the test suite (most recently the
badge escaper defect — see docs/fuzzing.md).

**test_statement_coverage80 — Met.** 80% statement coverage of the
release-path tooling, measured with coverage.py across the unit suite
plus a full gated build (the local-only score-ledger audit utility is
excluded as outside the release path). The measurement procedure is
recorded in docs/ASSURANCE-CASE.md.

**test_policy_mandated — Met.** The policy is written and binding: the
pull request template requires tests for new or changed tooling
behaviour, and the enforced CI job runs them.

**tests_documented_added — Met.** (Carried from passing.)

**warnings_strict — Met.** The lint set now runs in enforcing mode;
findings block.

## Security (silver)

**implement_secure_design — Met.** The assurance case walks the
principles — economy of mechanism, fail-closed gates, least privilege,
open design, complete mediation — and where each is implemented.
<https://github.com/trentpower/trentpower.fr/blob/main/docs/ASSURANCE-CASE.md>

**crypto_weaknesses — Met.** (Carried from passing.)

**crypto_algorithm_agility — Met.** Digests are algorithm-prefixed in
the manifests (sha256-…), so migrating to another member of the SHA-2
family or SHA-3 is a field change in a new edition, not a redesign; the
PGP layer likewise supports re-keying with a published successor key.

**crypto_credential_agility — Met.** Signing keys live exclusively in
the local GnuPG and OpenSSH keyrings, entirely outside the repository
and the deployed site; rotation is a key swap plus a published
announcement, with no code change.

**crypto_used_network — Met.** Everything is HTTPS/TLS — the site, the
repository, every fetch the tooling makes. No insecure protocol exists
to enable.

**crypto_tls12 — Met.** TLS 1.2+ with HSTS on the site; tooling uses
the platform TLS stack with no downgrade path.

**crypto_certificate_verification — Met.** The tooling uses standard
clients (python urllib/requests, curl) with default certificate
verification; nothing disables it anywhere in the repository.

**crypto_verification_private — Met.** Certificate verification happens
before any request is sent, and no request carries private data in any
case — there are no cookies or credentials in the system.

**signed_releases — Met.** Every release is PGP-signed (manifest,
archives, SHA256SUMS), the public key is published at a well-known URL
with its fingerprint in SECURITY.md, and the verification walk-through
is public. The private key has never been on any distribution site.
<https://trentpower.fr/en-au/verify/>

**version_tags_signed — Met.** edition/\* tags are signed and protected
by a tag ruleset against moving or deletion.

**input_validation — Met.** Allow-lists are the house style: the
public-exposure manifest decides what the server may serve and refuses
the rest; the verification-data validators accept only declared paths,
hash shapes and dates; the template engine rejects unknown tokens
outright.

**hardening — Met.** Strict CSP, SRI on every linked asset,
cross-origin isolation headers, HSTS — documented in
docs/SECURITY-AND-PRIVACY.md.

**assurance_case — Met.** docs/ASSURANCE-CASE.md: threat model, trust
boundaries, the secure-design argument, countered weaknesses, and the
residual risks stated rather than hidden.
<https://github.com/trentpower/trentpower.fr/blob/main/docs/ASSURANCE-CASE.md>

## Analysis (silver)

**static_analysis_common_vulnerabilities — Met.** (Carried from
passing.)

**dynamic_analysis_unsafe — N/A.** (Carried from passing.)

---

# Gold level — recorded position

Gold is out of reach for a single-author project, by design of its
criteria, and no wording changes that. Four gold MUSTs require more
than one person: achieve_silver as prerequisite aside, bus_factor ≥ 2,
two unassociated significant contributors, and two-person review of
50% of changes. These are answered Unmet, honestly, and the remaining
gold criteria that the repository does meet (reproducible build,
hardened site, security review, 2FA, code-review standards) are
answered Met so the entry reads true at every level.
