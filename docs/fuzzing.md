# Fuzzing

## Scope

trentpower.fr ships static HTML, CSS and JavaScript. Nothing in the
published site parses untrusted input at runtime, so there is no
network-facing surface to fuzz and no place for heavyweight fuzzing
infrastructure (OSS-Fuzz, ClusterFuzzLite) in this repository.

What the repository does contain is build tooling with real parser
surfaces — code that takes text in and produces structured output. Those
are fuzzed with property-based tests using
[Hypothesis](https://hypothesis.readthedocs.io/), which generates
adversarial inputs and shrinks failures to minimal counterexamples.

## What is covered

`tools/quality/tests/test_fuzz_properties.py` drives arbitrary inputs
through four surfaces and asserts the invariant each one promises:

| Surface | Invariant |
| --- | --- |
| `{{ }}` token engine (`tools/build/render_pages.py`) | escaping is total in text and attribute contexts; arbitrary templates fail only with the declared `RenderError`, never anything else |
| i18n slugs (`tools/lib/slugs.py`) | idempotent; lowercased alphanumerics joined by single underscores, edges trimmed |
| locale dates (`tools/lib/dates.py`) | canonical `YYYY-MM-DD` strings render with the right day and year in both locales |
| badge SVG generator (`tools/badges/generate_badges.py`) | `esc()` neutralises markup; generated SVG is always well-formed XML |

The suite runs in the `source-quality` job of `pr-checks.yml` on every
pull request, alongside the existing example-based unit tests.

Note on OpenSSF Scorecard: its Fuzzing check recognises property-based
testing for Erlang, Haskell, Elixir, Gleam, JavaScript and TypeScript —
not Python/Hypothesis (verified against `checks/raw/fuzzing.go` at
Scorecard v5.3). The check therefore reads 0 here and that reading is
accepted; the tests exist for the value they deliver, not the score.
Adding a JavaScript fast-check harness purely to satisfy the detector
was considered and declined as score theatre.

## What it has caught

The first run found that `esc()` in the badge generator passed C0
control characters through into SVG, producing XML that no conformant
parser will read. The generator now drops XML-invalid control characters
before entity-escaping. Curated badge metadata never contained such
characters, so no published artefact changed — but the tool no longer
relies on that assumption.

## What is deliberately not done

- No corpus-driven coverage fuzzing: the parsers are small, pure
  functions; property-based testing reaches their failure modes without
  build-system weight.
- No fuzzing of third-party parsers (PyYAML, json): upstream projects
  fuzz those; this repository pins and verifies them instead.
