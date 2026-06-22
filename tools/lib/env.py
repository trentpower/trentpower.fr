"""tools/lib/env.py — the interpreter-environment evidence seam.

Some diagnostics ask questions that are neither a filesystem read (Repo,
tools/lib/repo.py) nor a subprocess run (Proc, tools/lib/proc.py): is a binary
on PATH, is a Python module importable, what interpreter is running. `Env` is
the single injected seam those crossings go through, so a diagnostic's whole
compute path runs over a fake environment with no monkeypatching of
shutil/importlib/platform.

Deliberately tiny — three primitives, no more. This is testability, not a
general environment framework: the value is that a `FakeEnv`
(tools/quality/tests/_fixture.FakeEnv) can make "node missing" / "hypothesis
absent" deterministic, exactly as FakeProc does for subprocesses. Two real
adapters cross it (the production Env below and the test fake), so the seam
earns its keep; anything richer belongs in the caller, like path knowledge
lives in the caller rather than in Repo.
"""

from __future__ import annotations

import importlib.util
import platform
import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class Env:
    """Production adapter: query the live interpreter environment."""

    def which(self, name: str) -> str | None:
        """Absolute path of an executable on PATH, or None if absent."""
        return shutil.which(name)

    def has_module(self, name: str) -> bool:
        """True iff `name` is an importable top-level module. Uses the import
        SYSTEM name, which is not always the pip distribution name (pyyaml
        installs the `yaml` module); callers pass the import name."""
        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            # a half-installed namespace package can raise rather than return
            # None; treat any probe failure as "not importable" here.
            return False

    def python_version(self) -> str:
        """The running interpreter's version, e.g. "3.11.7"."""
        return platform.python_version()
