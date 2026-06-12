# Security

[![PGP Signed](https://img.shields.io/badge/Signed-PGP%20Verified-blue?logo=gnuprivacyguard&logoColor=white&style=flat-square)](https://trentpower.fr/en-au/verify/)
[![SHA-256 Manifest](https://img.shields.io/badge/Integrity-SHA--256%20Manifest-success?style=flat-square)](https://trentpower.fr/integrity.json)
[![security.txt](https://img.shields.io/badge/security.txt-RFC%209116-informational?style=flat-square)](https://trentpower.fr/.well-known/security.txt)
[![Responsible Disclosure](https://img.shields.io/badge/Disclosure-Responsible-orange?style=flat-square)](#reporting)

## Reporting

Report security issues to the contact published in
[`/.well-known/security.txt`](https://trentpower.fr/.well-known/security.txt),
encrypted if you prefer with the published PGP key at
[`/.well-known/pgp-key.asc`](https://trentpower.fr/.well-known/pgp-key.asc)
(fingerprint `A729 591B 450D 3F59 3694 98BD 8299 1F25 04AE 0263`).

Suspected vulnerabilities can also be reported privately through GitHub:
[open a private vulnerability report](https://github.com/trentpower/trentpower.fr/security/advisories/new).
The report stays between you and the maintainer until a fix is published.

Please do not open a public issue for anything sensitive.

## Posture

The site's security and privacy posture — CSP, cross-origin isolation, HSTS,
the public-exposure allow-list, secret handling — is documented in
[docs/SECURITY-AND-PRIVACY.md](docs/SECURITY-AND-PRIVACY.md). Incident
handling is documented in
[docs/INCIDENT-RESPONSE.md](docs/INCIDENT-RESPONSE.md).

Every release is gated by blocking security checks before deploy; see
[docs/GATES-CHECKS-AND-QUALITY.md](docs/GATES-CHECKS-AND-QUALITY.md).
