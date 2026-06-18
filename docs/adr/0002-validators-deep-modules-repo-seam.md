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
globals — which tests *past* the interface and breaks on internal refactors. We
chose to inject the filesystem as a seam (two real adapters: the production repo
and a `tmp` fixture) and split compute from render, rather than (a) keep
monkeypatching, or (b) extract every sub-function as a separately-tested unit
(which would lose locality — the real bugs are in how the checks are wired
together, which only the `evaluate` interface exercises).

`Repo` is a pure adapter on purpose: domain knowledge (which file is "the release
workflow", the public-tree exclusion policy) stays in each validator, so the seam
serves every gate without coupling to one. The per-validator `Result` types are
deliberately *not* unified — their shapes genuinely differ, and forcing one would
fit the abstraction to a single case.

## Consequences

New or touched validators follow this shape and ship a
`tools/quality/tests/test_<name>.py` in the same form. Migration is incremental:
not every gate is converted yet, but the pattern is the target. See
[GATES-CHECKS-AND-QUALITY.md](../GATES-CHECKS-AND-QUALITY.md) §1 ("Validator
shape").
