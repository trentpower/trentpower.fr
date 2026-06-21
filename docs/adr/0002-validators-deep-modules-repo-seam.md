# Validators are deep modules behind an injected Repo seam

The `validate_*.py` gates are structured as deep modules with one shape: a
`Repo(root)` filesystem seam (`tools/lib/repo.py`: read / is_file / glob / size),
a `load(repo) -> (ctx, errors)` step, a pure `evaluate(repo, …) -> Result`, and a
thin `main()` adapter that is the only place that prints or exits. Non-filesystem
dependencies (the clock, the pre-signature flag) are injected the same way. Tests
cross `evaluate()`/`load()` over a fixture repo and assert on the returned
`Result`.

## Considered Options

The earlier validators read module-global paths and mixed compute with
`print`+`sys.exit` in `main()`, so the only way to test them was to monkeypatch
globals — which tests _past_ the interface and breaks on internal refactors. We
chose to inject the filesystem as a seam (two real adapters: the production repo
and a `tmp` fixture) and split compute from render, rather than (a) keep
monkeypatching, or (b) extract every sub-function as a separately-tested unit
(which would lose locality — the real bugs are in how the checks are wired
together, which only the `evaluate` interface exercises).

`Repo` is a pure adapter on purpose: domain knowledge (which file is "the release
workflow", the public-tree exclusion policy) stays in each validator, so the seam
serves every gate without coupling to one. The per-validator `Result` types are
deliberately _not_ unified — their shapes genuinely differ, and forcing one would
fit the abstraction to a single case.

## Consequences

New or touched validators follow this shape and ship a
`tools/quality/tests/test_<name>.py` in the same form. Migration is incremental:
not every gate is converted yet, but the pattern is the target. See
[GATES-CHECKS-AND-QUALITY.md](../GATES-CHECKS-AND-QUALITY.md) §1 ("Validator
shape").

## Testable by design

This shape is why the measured coverage is high — and why the number is
meaningful. Because `evaluate()` is a pure seam, a test calls it directly over a
fixture repo and asserts on the returned `Result`; the clean-fixture-passes /
seeded-defect-fails pair makes each rule cheap to cover at its decision point. The
CLI stays a thin print/exit adapter, so coverage measures the rule logic, not
stdout scraping. Coverage climbs because the logic is reachable, not because the
tests reach around it — see [COVERAGE.md](../COVERAGE.md).

## Compliance checklist (pattern → standard)

A validator is **ADR-0002 compliant** only if every line below holds. Use this as
the review gate when adding or touching a validator.

- [ ] Receives repository access through the injected `Repo(root)` seam
      (`tools/lib/repo.py`) — never a module-global path or a bare `open()`.
- [ ] All paths are **repo-root-relative** (e.g. `"public/index.html"`), so a
      fixture repo at any root works unchanged.
- [ ] Split into `load()` / `evaluate()` / `main()`. `load(repo)` reads + parses
      inputs (the only impure-IO step besides `Repo`); `evaluate(repo, …)` holds
      the rule decision and **returns a `Result`** (with `ok` + `fails`/`warns`);
      it never prints or exits.
- [ ] `main()` is the **only** adapter that prints or calls `sys.exit`; it builds
      the seam(s), calls `evaluate`, renders, returns the exit code.
- [ ] Unit tests cross `evaluate()` (and `load()`), **not** the CLI — no stdout
      scraping, no subprocess of the validator.
- [ ] Tests include **one pristine fixture that passes** and **one seeded-defect
      fixture that fails** — proving the rule catches the bad case it guards.
- [ ] After migration, CLI **output and exit code are behaviour-identical** to
      the pre-migration validator (capture a baseline first; diff it).
- [ ] Any dependency that is _not_ the filesystem — subprocess, network, a
      binary-only library (PIL, PyMuPDF), or in-place mutation — is taken through
      its **own injected seam** (e.g. `Proc` in `tools/lib/proc.py`) or explicitly
      **deferred** with a noted reason, never reached for directly inside
      `evaluate`.

Two non-filesystem seams already exist and set the precedent: `Repo` (filesystem)
and `Proc` (subprocess, used by `validate_release` + `validate_public_readiness`).
A new kind of dependency earns a new seam only when **two** real adapters cross it
— one adapter is a hypothetical seam, two is a real one.
