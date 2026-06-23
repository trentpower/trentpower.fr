# The fast unit tier blocks real subprocess and network; an allowlist holds the integration tests

`tools/quality/tests/run_suite.py --fast` installs a guard
(`_fixture.block_real_processes`) that replaces `subprocess.run`/`Popen` and `socket.socket`
with raisers, then runs the unit suite. A test that shells out to real git/gpg or opens a socket
— bypassing the injected Proc seam (ADR-0002) — fails loudly instead of silently depending on
the host. The few tests that genuinely need a real process (the Proc adapter's own test, the
doctor.sh ceremony test, the real-repo `ExternalInterface` smokes) are named in an explicit
`SLOW_ALLOWLIST` and run unblocked in the slow tier / `make coverage`.

## Considered Options

We block at the tier with a file allowlist rather than tag every real-process test with a
marker: the allowlist is one short, reviewable list, and the _default_ is safe — a new test is
guarded unless deliberately exempted. Test modules are imported BEFORE the guard is installed:
some pull in `ssl`/`asyncio`, which subclass `socket` at import time and would crash under a
patched `socket.socket`; loading first and blocking second avoids it. The guard turns ADR-0002's
"cross the seam" rule from aspiration into something enforced.

## Consequences

A unit test that needs a real process must either use the Proc seam (preferred) or join
`SLOW_ALLOWLIST` with a reason. The full suite (`make coverage`, CI's coverage job) runs
everything unblocked, so allowlisted tests still execute and count; `make test-fast` / the CI
fast-tier step is the cheap, fast-failing guard.
