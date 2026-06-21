# Test coverage

The `Coverage` badge reports **~93%** unit-test coverage of the project's own
unit-testable logic. Like every claim here, it is reproducible from source.

## What the figure is

The deterministic unit suite (`tools/quality/tests/`, stdlib `unittest` +
Hypothesis) crosses each validator's `evaluate()` seam over fixture repos and
unit-tests the library modules, the build/seal guards, and the seamed CLI tools.
Measured over `tools/` — excluding the build *generators* and `score-ledger`
(see below) — that suite covers **~93%** of statements, reproducibly:

```sh
bash tools/quality/coverage.sh   # the three enforced surfaces (below)
```

## Surfaces and floors (enforced in CI)

`tools/quality/coverage.sh` reports three focused surfaces, each with a floor
that `pr-checks.yml` fails below:

| surface | floor | typical |
| --- | --- | --- |
| convergence + seal (signing-critical) | 90% | ~98% |
| ADR-0002 validators | 90% | ~98% |
| broad quality-policy (validators + libs + verify) | 85% | ~94% |

## What the figure excludes, and why

- **The build generators** (`generate_site`, `render_pages`,
  `generate_source_view`, …) are not unit-tested by design — they are
  **integration-tested**: every build runs them and the gate verifies their
  output. `tools/quality/coverage_global.sh` gives a best-effort *combined*
  figure by running a full build under coverage with subprocess capture, but that
  number is **build-environment-dependent** (subprocess coverage capture is not
  reliably reproducible across runs), so the badge uses the stable unit figure.
- **`tools/score-ledger/`** is a live-site network audit tool (W3C / SSL Labs /
  PageSpeed over HTTP). It exists to hit external services against the deployed
  site, so unit-test coverage of it is meaningless.
