# A changed-line coverage ratchet, computed in-house from data the pipeline already emits

The surface floors (`tools/quality/coverage.sh`) gate the whole-tree average, so a weak new
module hides in it. `tools/quality/diff_coverage.py` adds a second gate: every changed,
executable line in an in-scope file must be covered at or above `DIFF_MIN`. It reads the
per-file map `coverage.sh` already writes to `.build/coverage/coverage.json` and the `git diff`
against the merge-base — no second measurement pass.

## Considered Options

We compute diff coverage in-house rather than add `diff-cover` as a pinned dependency: the data
(executed / missing lines per file) is already emitted by the coverage run, so a dependency
would add supply-chain surface (hashed-pip sets, OpenSSF posture) only to re-derive what we
have. We gate _changed lines_ — the diff's added lines intersected with coverage's missing set —
rather than whole changed files, and diff the working tree against the merge-base so the gate
judges exactly what was measured (and equals the PR diff in CI). `# pragma: no cover` is the
escape hatch (coverage.py drops those lines, so they never count).

## Consequences

A PR that adds uncovered lines to an in-scope file fails even when the broad floor still passes.
The gate is PR-only (a diff needs two points) and needs `fetch-depth: 0` on the CI checkout.
Out-of-scope files (build generators, tests, `gate.py`/`lint.py`) are reported and skipped,
mirroring the surface floors.
