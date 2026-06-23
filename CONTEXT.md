# trentpower.fr

A static, bilingual publication whose distinguishing property is that every
public promise it makes is checkable from the source. This glossary fixes the
language of that promise model so the website, repository, docs, and pipeline
say the same thing. It is a glossary, not a spec — implementation lives in code.

## Claims & the honesty gate

**Claim**:
A public, verifiable promise the site makes about its supply chain — e.g. SLSA
provenance, a CycloneDX SBOM, a PGP-signed integrity manifest.
_Avoid_: assertion, feature, badge.

**Token**:
The exact case-sensitive word whose appearance on the claim surface signals that
a claim is being made (e.g. `SLSA`, `reproducib`). It is the detection trigger,
not the promise — several tokens may express one underlying claim (`Sigstore`,
`Rekor`, and `attest` all stand for one keyless-attestation claim).
_Avoid_: keyword; and do not call a token a "claim" — the token is how a claim is
detected, not the claim itself.

**Control**:
The executable evidence-collector (`control_*`) that proves a claim true by
gathering real evidence — running gpg, parsing a workflow file, checking a file
on disk. A claim is bound to one or more controls.
_Avoid_: check, validator, rule, policy.

**Check**:
A single entry in the deploy registry (`tools/lib/checks.py`) that the gate runs,
e.g. `claims_parity` or `gpg`. A control is not a check: a control backs a claim;
a check is a registry-run step. One check (`claims_parity`) runs every control.
_Avoid_: control, test, validator.

**Gate**:
The aggregate pass/fail over all blocking checks (`gate.py`); a release is "ready"
only when the gate is green. Distinct from any single check.
_Avoid_: pipeline, suite.

**Claim surface**:
The glob-defined set of public files the gate scans for tokens — it decides where
the gate _looks_. Deliberately wider than any one claim's declared locations, so a
claim added to an unanticipated page is still seen and still must be backed.
_Avoid_: claim source, stated_in.

**stated_in**:
A claim's declared canonical locations, enforced to be a subset of the claim
surface. It records where a claim is _meant_ to appear, not where the gate
searches.
_Avoid_: location, surface.

**Backed**:
Said of a claimed token whose bound controls all pass. An unbacked claim — a token
on the surface with no passing control — blocks the gate.
_Avoid_: verified, validated, satisfied.

**Status**:
A claim's truth-class: `enforced` (a passing control backs it), `goal` (a
documented target — never release-blocking, never worded as achieved), or `manual`
(a human boundary with no automatable control).
_Avoid_: state, level.

**Enforced-at**:
The gate level that binds a claim: `pr-gate` (a blocking check in the registry),
`release` (a control reading the release workflow), or `ruleset` (a required
GitHub status check).
_Avoid_: stage, scope.

**Release-blocking**:
Whether an unmet claim stops a release. Goal-status claims are never
release-blocking; this is independent of severity.
_Avoid_: required, critical.

**Claim ledger**:
The generated human view of every claim and its backing control (`docs/CLAIMS.md`),
rendered from the claims map and drift-gated against it.
_Avoid_: manifest, registry.

## Publication anchors

**Edition**:
A single dated, signed publication of the whole site (`edition/YYYY-MM-DD`); the
unit of release.
_Avoid_: version, build; "release" is the act of publishing an edition, not the
edition itself.

**Integrity manifest**:
The signed list of SHA-256 hashes of every published file (`integrity.json` +
`.sig`); the anchor a reader verifies the live site against.
_Avoid_: checksum file, hash list.

## Trust posture

**Accepted finding**:
A security-scanner reading (OpenSSF Scorecard, code-scanning) the project
consciously declines to chase and instead records as won't-fix-by-design, because
the underlying control is already correct or the gap is structural (e.g. a
single-maintainer review cap, a scanner that misreads `gh release create` as an
over-grant). The honest counterpart to a backed claim — it states plainly what is
_not_ fixed, and why, rather than contorting code to lift a score.
_Avoid_: false positive (only some accepted findings are false positives; others
are real-but-structural), suppression, ignore.

## Build, gate & quality

**Promotion**:
The one-way path a change travels — `feature/* → preprod → main` — where each merge
promotes the _same_ bytes (no rebuild, no rebase) and only re-verifies them.
_Avoid_: deploy, release (deploy is the separate manual publish; release is publishing an edition).

**Coverage surface**:
A named slice of the codebase whose unit-test coverage is measured and floored on its own —
`seal`, `ADR`, and `broad`. A _coverage_ surface, unrelated to a _claim surface_.
_Avoid_: bare "surface" (it collides with claim surface), scope, set.

**Floor**:
The minimum coverage a surface must hold; deploy-blocking, and only ever raised.
_Avoid_: threshold, target, minimum (a target is aspirational; a floor is enforced).

**Ratchet**:
A gate that loosens in one direction only — coverage floors rise as coverage climbs and are
never lowered; the changed-line ratchet holds new code to the bar.
_Avoid_: gate (a gate is pass/fail at a point; "ratchet" names the never-loosens property).

**Seam**:
An injected boundary a validator's compute path crosses to reach the outside world — `Repo`
(filesystem), `Proc` (subprocess), `Env` (interpreter) — so logic runs over fakes with no real
disk, process, or host. See ADR-0002.
_Avoid_: mock, interface, port.

**Fast tier / slow tier**:
The unit-test split: the _fast tier_ runs with real subprocess and network blocked, forcing
tests through the Proc seam; the _slow tier_ is the small allowlist of tests that genuinely
need a real process.
_Avoid_: unit / integration (the line is "needs a real process", not "spans multiple units").

**Seal**:
The point in the build after which no published byte may change before signing; the signature
covers exactly the sealed bytes.
_Avoid_: snapshot, freeze, lock.

**Ceremony**:
The terminal presentation layer (`tools/build/term.sh`) that makes a run legible — wordmark,
stages, panels, tables. Presentation only: it never affects the build, gate, signing, or
verification.
_Avoid_: UI, logging, output.

**Preflight**:
The single local command (`make preflight`) that runs the same checks CI runs, in the same
order, so "green locally" means "green in CI".
_Avoid_: pre-commit, CI (CI is the remote authority; preflight is its local mirror).

**Doctor mode**:
The readiness class `make doctor` assigns a checkout — `full`, `partial`, `archive`, or
`blocked` — naming which checks it can actually run.
_Avoid_: status, state.
