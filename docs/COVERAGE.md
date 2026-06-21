# Test coverage

The `TEST COVERAGE` badge reports unit-test coverage of the project's own
**unit-testable logic** — not a global all-scripts figure. The number is
**measured by the build, not hand-set**, and is reproducible from source.

> **Current figure: 94%** — auto-derived by the pipeline from the
> unit-testable-logic surface (defined below). The build writes this figure into
> the badge and this page; CI fails a PR that leaves it stale.

Documentation freshness is build-blocking. Public claims about tests, coverage,
badges, gates, signing, integrity, byte convergence and deployment must match the
repository state. The quality gate checks key documentation for stale paths, stale
badge/coverage values, broken internal links and contradictory claims.

## What the figure is

The deterministic unit suite (`tools/quality/tests/`, stdlib `unittest` +
Hypothesis) crosses each validator's `evaluate()` seam over fixture repos and
unit-tests the library modules, the build/seal guards, and the seamed CLI tools.
The published headline figure is coverage of the **unit-testable-logic surface** —
`tools/quality`, `tools/lib`, `tools/verify`, excluding the test files themselves,
`gate.py` and `lint.py` — the same set as the enforced "broad" floor below. It
**excludes** the build _generators_ and `score-ledger` (see exclusions).
Reproduce it:

```sh
bash tools/quality/coverage.sh   # three enforced surfaces + the published figure
```

This is **not** a global `tools/` percentage and should never be read as one — the
global number is dragged down by one-shot build generators that earn integration
tests, not unit tests (see exclusions).

## Test inventory

The suite is currently **67** unit-test files / **1,063** test functions under
`tools/quality/tests/`, run with stdlib `unittest` and property-based cases on
Hypothesis. These two counts are **source-derived**: `coverage.sh` recounts the
directory in the same run that measures coverage and writes the numbers into
`.build/coverage/coverage-summary.json`; `sync_coverage.py` propagates them into
this page and CI fails a PR that changes the suite size but leaves the counts here
stale (same machinery as the percentage above).

The suite is grouped by file and purpose rather than by a formal taxonomy, so the
per-category figures below are descriptive, not separately gated — only the totals
are enforced:

| group                          | what it covers                                                              |
| ------------------------------ | --------------------------------------------------------------------------- |
| validator fixture tests        | each `validate_*.py` over fixture repos — clean fixture passes, seeded defect fails |
| seam / integration tests       | `Repo(root)` and process seams, `evaluate()` boundaries over temp trees     |
| convergence + seal             | byte-fixpoint guard and post-seal immutability (`assert_seal_immutable`, `validate_sri_coherence`) |
| badge + coverage sync          | the published figure and inventory stay in lock-step with the measurement   |
| library / helper               | shared parsing, hashing, path and minify logic in `tools/lib`               |
| property / fuzz                 | Hypothesis-generated inputs against parsing and policy invariants           |
| score-ledger                   | the local export path only — its live-network audit is intentionally not unit-tested |

## What the tests protect

The tests cover the parts of the repository that can silently weaken trust:
validators, path and seam handling, public-readiness checks, byte-convergence
guards, badge synchronisation and post-seal immutability.

The goal is not coverage for its own sake. It is to stop a future edit from making
a trust claim stale while the repository still looks healthy — a validator that no
longer fails on the defect it was written for, a badge that no longer matches the
measurement, a generator that mutates bytes after the seal.

## Source of truth, and where reports land

- The authoritative measurement is the **coverage.py JSON** at
  `.build/coverage/coverage.json`. The HTML report's internal `status.json` is a
  rendering detail, **not** the source of truth.
- `coverage.sh` writes both the JSON and the HTML report
  (`.build/coverage/html/index.html`) under `.build/coverage/`. That tree is
  **gitignored, local-only, reproducible from source, and deliberately not
  deployed** — there is no published `/tests/coverage/` route. The trust story is
  reproducibility, not a hosted report.

## Surfaces and floors (enforced in CI)

`tools/quality/coverage.sh` reports three focused surfaces, each with a floor
that `pr-checks.yml` fails below (via the hash-pinned `coverage==7.14.1` in
`.github/requirements/coverage.txt`):

| surface                                           | floor | typical | why it matters                                      |
| ------------------------------------------------- | ----- | ------- | --------------------------------------------------- |
| convergence + seal (signing-critical)             | 90%   | ~98%    | protects the build behaviour a signature commits to |
| ADR-0002 validators                               | 90%   | ~98%    | protects the policy-as-code rule decisions          |
| broad quality-policy (validators + libs + verify) | 85%   | ~94%    | protects validators, libraries and verify helpers   |

The floors are a ratchet: raise them as coverage climbs, never lower them.

### The floor is deploy-blocking — enforced in both the build and CI

The same `coverage.sh` ratchet runs in two places, so a coverage regression (or a
failing unit test) cannot reach the live site:

1. **The build** — `build.sh` runs `coverage.sh` as a required step in stage 02
   (RENDER), right after the source-quality gate and **before** any public byte is
   generated. A surface below its floor exits non-zero and halts the build
   fail-fast, leaving `public/` untouched. (`--skip-coverage` skips it for local
   inner-loop iteration only and is refused for `--public-check` / `--public-release`.
   Where coverage.py is not installed — e.g. the publication-check/release build
   jobs — the step is skipped with a warning, since the `source-quality` CI job
   below is the authoritative gate.)
2. **CI** — the **`source-quality`** job of `pr-checks.yml` re-runs it
   ("Coverage ratchet (enforced)"). Below floor → the job fails; because merges to
   `preprod`/`main` require the PR checks green and a deploy ships from `main`,
   **a coverage regression blocks the merge a deploy would ship from.**

So the threshold gates deployment both at build time and at merge time. The
deploy workflow's own `readiness` job re-asserts the release gate (`gate.py`, not
the coverage ratchet) on the merge commit — coverage has already been enforced
upstream, at the build and on the PR.

### Failure behaviour

The enforcement is mechanical, and each failure mode has one outcome:

- A unit test fails → the build stops and `public/` is left untouched.
- An enforced coverage surface drops below its floor → the build stops.
- The badge value or the test-inventory counts drift from the measured summary →
  CI's `sync_coverage.py --check` fails the PR.
- A badge SVG does not match its `badges.json` entry → the blocking `local_badges`
  gate (`validate_badges.py`) fails, so a hand-edited badge cannot ship.
- A public build (`--public-check` / `--public-release`) is asked to skip coverage
  → the build refuses and exits.

## How the figure is published and kept honest

The figure is **derived, not hand-set**. `coverage.sh` writes the measured
percentage — and the source-derived test-inventory counts — to
`.build/coverage/coverage-summary.json`; `tools/badges/sync_coverage.py` propagates
the percentage to the four places it lives (the `coverage` mark in
`metadata/badges/badges.json`, the rendered `metadata/badges/coverage.svg`, the
README badge alt text, and the `Current figure:` line above) and the counts to the
test-inventory line on this page. `build.sh` runs `sync_coverage.py --write` in
stage 02 (so a local build keeps them current); CI runs `sync_coverage.py --check`
(so a PR that shifts coverage or suite size but leaves a stale badge or inventory
fails). The blocking `local_badges` gate (`validate_badges.py`) independently checks
that every badge SVG matches `badges.json`, so a hand-edited badge cannot ship.

## Why not global all-scripts coverage?

A raw `tools/` percentage would mix two different kinds of evidence — unit-tested
logic and integration-tested generators — into one number. The headline stays on
the deterministic unit-testable-logic surface because it is stable, reproducible
and enforceable; the two excluded categories earn their assurance elsewhere.

- **The build generators** (`generate_site`, `render_pages`,
  `generate_source_view`, …) are not unit-tested by design — they are
  **integration-tested**: every build runs them and the gate verifies their
  output. Counting them drags the measured number down to ~66% (the raw global),
  which is exactly why the published figure is the unit-testable-logic surface and
  not the global. `tools/quality/coverage_global.sh` can produce a best-effort
  _combined_ figure by running a full build under coverage with subprocess capture,
  but that number is **build-environment-dependent** (subprocess coverage capture
  is not reliably reproducible across runs), so it is never the published figure.
- **`tools/score-ledger/`** is a live-site network audit tool (W3C / SSL Labs /
  PageSpeed over HTTP). It exists to hit external services against the deployed
  site, so unit-test coverage of it is meaningless. It is retained by decision and
  documented separately in [SCORE-LEDGER.md](SCORE-LEDGER.md) — only its local
  export path is unit-tested.

## Why this matters

The coverage system is part of the publication trust model, not a cosmetic badge.
The same repository that publishes signed, integrity-recorded static output also
tests the code that decides whether that output is ready to publish.
