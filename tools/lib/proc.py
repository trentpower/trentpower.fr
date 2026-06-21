"""tools/lib/proc.py — the subprocess evidence seam for the validator fleet.

Some validators collect evidence by running a program rather than reading a
file: gpg verifies a detached signature, git reports what is tracked, the gate
re-runs itself. `Proc` is the single injected seam those crossings go through —
one `run(argv, …)` primitive returning a captured `ProcResult`, the same way
`Repo` (tools/lib/repo.py) is the seam for filesystem reads.

The production adapter is `Proc()`, which shells out via subprocess. A test
adapter is a fake with the same `run` method that returns canned results (see
tools/quality/tests/_fixture.FakeProc), so a validator's whole compute path runs
without a real gpg / git / python on the machine and without touching the
network or the host keyring.

This stays a PURE adapter: it knows nothing about gpg, git or the gate. Which
program to run, which return code means what, how to read the output — that
domain knowledge lives in each validator, exactly as path knowledge lives in the
validator rather than in Repo. Two real adapters already cross it (the gpg
signature checks and the git tracking checks), so the seam earns its keep.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcResult:
    """The captured outcome of one run: exit code plus decoded streams.

    Mirrors the subset of subprocess.CompletedProcess the validators actually
    read — callers branch on `returncode`, parse `stdout`, and quote `stderr` on
    failure. Nothing else of CompletedProcess is exposed.
    """

    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class Proc:
    """Production adapter: run a command and capture it.

    `run` always captures stdout/stderr as text and never raises on a non-zero
    exit (the caller decides what a non-zero code means), matching how the
    validators used subprocess.run directly before the seam existed.
    """

    def run(
        self,
        argv: Sequence[str],
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> ProcResult:
        p = subprocess.run(
            list(argv),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            # tolerant decode: git history (e.g. `git log -p`) can carry non-UTF-8
            # bytes in text-like blobs; strict decoding would raise UnicodeDecodeError
            # and crash the secret/history scan instead of reporting. Matches the
            # errors="replace" the scanners used before this seam existed.
            errors="replace",
        )
        return ProcResult(returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
