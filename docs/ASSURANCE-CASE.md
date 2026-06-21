# Assurance case

Why the security requirements of trentpower.fr are met: the threat
model, the trust boundaries, the design principles applied, and the
common weaknesses countered. Companion documents:
[SECURITY-AND-PRIVACY.md](SECURITY-AND-PRIVACY.md) (mechanisms in
detail), [TRUST-AND-VERIFICATION.md](TRUST-AND-VERIFICATION.md) (the
proof chain), [GATES-CHECKS-AND-QUALITY.md](GATES-CHECKS-AND-QUALITY.md)
(the enforcement machinery).

## Security requirements

The product is a published record. Its security requirements, in order:

1. **Integrity** — a reader must be able to prove that what they
   received is what was published, without trusting the transport, the
   host, or GitHub.
2. **Authenticity** — a reader must be able to prove the record was
   published by its author.
3. **Privacy** — reading must leak nothing: no trackers, no third-party
   requests, no cookies.
4. **Availability is explicitly _not_ guaranteed** — the record may go
   offline; it may not be silently altered. Redistributable signed
   archives make the record survivable independent of the site.

## Threat model

| Threat                             | Counter                                                                                                                                                                                                                            |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tampering in transit               | TLS + HSTS; beneath that, every file's SHA-256 in a PGP-signed manifest, SRI (SHA-384) on linked assets                                                                                                                            |
| Tampering at the host              | The host holds no signing key. Any modified byte fails verification against `integrity.json` + `integrity.json.sig`; post-deploy smoke tests check routes, headers and signature after every deploy                                |
| Tampering at the repository        | Signed commits, protected branches (no force push, no deletion, PR-only main with required checks), signed `edition/*` tags, and the signed record as the final arbiter — if GitHub and the signature disagree, the signature wins |
| Supply-chain compromise of CI      | Actions pinned to full commit SHAs; pip installs hash-pinned (`--require-hashes`); npm via lockfile; workflow permissions least-privilege; GitHub verifies and deploys but **never signs**                                         |
| Injected content (XSS)             | Build-time template engine escapes by context (text, attribute, URL), property-tested to be total; strict CSP (`default-src 'none'` baseline) so even a missed escape has nothing to talk to                                       |
| Credential leak                    | Push protection + secret scanning + a blocking full-history scan in CI; signing keys have never existed inside the repository                                                                                                      |
| Malicious or vulnerable dependency | Weekly Dependabot review (nothing auto-merges), OSV checks, hash pins that make substitution detectable                                                                                                                            |

## Trust boundaries

```text
[local signing machine]──signs──▶ [GitHub: verifies, never signs] ──deploys──▶ [host: serves, holds no keys] ──▶ [reader: verifies]
```

- The **private keys** exist only on the local machine. Crossing this
  boundary is forbidden by design and checked by the secret scans.
- **GitHub** is a verifier and conveyor. Environment secrets (SFTP) are
  scoped to deploy environments; production requires manual approval.
- The **host** is untrusted for integrity: it can withhold the record,
  never alter it undetected.
- The **reader** needs only FLOSS tools (gpg, sha256sum) and the
  published key to verify everything, offline.

## Secure design principles applied

- **Economy of mechanism** — static files; no server runtime, no
  database, no sessions, no authentication surface at all.
- **Fail-closed** — 36 blocking checks gate every release; a failed
  check stops publication, not the other way round.
- **Least privilege** — workflow tokens read-only by default; deploy
  secrets live only in their environment; the public-exposure manifest
  is an allow-list, and anything unmatched is refused.
- **Open design** — the entire mechanism is public; verification
  assumes an adversary who has read all of it.
- **Complete mediation** — every published byte passes the gate; every
  byte on the host is accounted for in the signed manifest.

## Common weaknesses countered

Injection and XSS by total context-aware escaping (property-tested) plus
strict CSP; path traversal by allow-list path validation in the
validators; insecure transport by HTTPS/HSTS everywhere with no http
fallback; weak cryptography excluded by construction (SHA-256/384,
Ed25519, RSA-4096 only); secrets in history by layered scanning.

## Verification depth

The claim above is exercised, not asserted: the unit and property test
suite plus a full gated build execute at **80% statement coverage** of
the release-path tooling (measured with coverage.py over `tools/`,
excluding the local-only score-ledger audit utility):

```sh
coverage run -m unittest discover -s tools/quality/tests
COVERAGE_PROCESS_START=.coveragerc bash tools/build/build.sh --check
coverage combine && coverage report --omit='*/score-ledger/*'
```

The assurance documentation is itself verified, not just asserted: the blocking
`docs_freshness` and `docs_links` gates (`tools/quality/validate_docs_freshness.py`,
`tools/quality/validate_docs_links.py`) fail the build and CI when the docs make a
stale machine-checkable claim — a repo path that no longer exists, a coverage or
test-inventory figure out of lock-step with the measurement, a canonical command
that drifts from `metadata/docs/commands.json`, or a broken internal link. A claim
in this file or its siblings cannot quietly rot while the repository moves on.

## Residual risks, stated

- **Single maintainer.** One person writes and reviews everything.
  Compensated by automation (the gate, CodeQL, the scans) — not
  equivalent to a second reviewer, and not claimed to be. See
  GOVERNANCE.md for continuity.
- **Host compromise is detectable, not preventable.** The design
  accepts this: integrity over availability.
- **Key compromise.** A stolen signing key forges the record. Keys are
  local-only, passphrase-protected; revocation and re-keying would be
  announced via the site and repository.
