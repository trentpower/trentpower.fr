# Code review

How changes are reviewed before they reach the public record, what every change is
checked against, and what makes a change acceptable.

This is a single-maintainer publication. There is no second reviewer, and that is
stated plainly rather than dressed up (see [../GOVERNANCE.md](../GOVERNANCE.md) and
[ASSURANCE-CASE.md](ASSURANCE-CASE.md), Residual risks). Review is therefore a
disciplined self-review against a fixed checklist, backed by automation that does
not depend on the reviewer's attention: the blocking gate, the secret scans, CodeQL
and the dependency (SCA) gate all run on every pull request and must pass.

## What every change is checked against

A change is not merged until all of the following hold. The same list is the
[pull request template](../.github/PULL_REQUEST_TEMPLATE.md).

- **Gate is green.** The full blocking gate passes
  (`python3 tools/quality/gate.py --all`), and the source-quality and secret-scan
  CI jobs pass. See [GATES-CHECKS-AND-QUALITY.md](GATES-CHECKS-AND-QUALITY.md).
- **Tests cover the change.** Behaviour-changing tooling adds or updates a test
  under `tools/quality/tests/` ([../CONTRIBUTING.md](../CONTRIBUTING.md)).
- **Commit is signed and signed off.** Cryptographic signature plus `Signed-off-by`
  (`git commit -s`), authored `Trent Power <trent@trentpower.fr>`.
- **No attribution trailers.** No `Co-authored-by`, `Generated-by` or tool-vendor
  trailers; enforced by `tools/quality/validate_git_metadata.py`.
- **Generated files are sourced, never hand-edited.** `*.js`/`*.css` under `public/`
  come from their templates and regenerate byte-identically.
- **Integrity manifest is coherent.** Any change to published bytes is reflected in a
  freshly sealed, signed `integrity.json`; no licensed font binaries enter version
  control.
- **Scope is honest.** The change does only what its description says, and the
  documentation that describes the affected surface is updated in the same change.

## What makes a change worth merging

Beyond passing the checklist: the change is necessary (the tooling changes only when
the publication needs it to), it is the simplest version that holds, and it leaves
the record more verifiable, not less.
