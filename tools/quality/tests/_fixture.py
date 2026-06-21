"""Shared test-fixture helpers for tools/quality/tests.

Every fixture-using validator test built the same three things by hand: a
`_write(root, rel, text)` that creates parent dirs, the `sys.path` bootstrap that
puts the tools/ pillars on the import path, and (for a couple) an mtime / bytes
writer. They are collected here so a test imports them instead of re-spelling
them — one definition, not eighteen.

Per-test `_make_fixture_repo` builders stay in their own files: those are
domain-specific (each validator needs a different coherent repo), and centralising
them would couple this helper to every caller.

Usage:
    import _fixture
    _fixture.bootstrap()                       # or bootstrap("release", "badges")
    import validate_x as vx                     # resolvable after bootstrap
    from _fixture import write as _write        # keeps existing _write(...) calls
"""

from __future__ import annotations

import os
import pathlib
import sys

# tools/quality/tests/_fixture.py -> parents[2] is the tools/ directory.
_TOOLS = pathlib.Path(__file__).resolve().parents[2]
_DEFAULT_SUBS = ("lib", "build", "quality", "verify")


def bootstrap(*extra_subs: str) -> None:
    """Insert the tools/ pillars on sys.path so a test can import the validator
    modules by bare name. Pass extras (e.g. "release", "badges") for tests that
    need them; the default four cover almost every validator."""
    for sub in (*_DEFAULT_SUBS, *extra_subs):
        p = str(_TOOLS / sub)
        if p not in sys.path:
            sys.path.insert(0, p)


def write(root: pathlib.Path, rel: str, text: str = "") -> None:
    """Write text to a repo-relative path, creating parent dirs."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def write_bytes(root: pathlib.Path, rel: str, data: bytes) -> None:
    """Write bytes to a repo-relative path, creating parent dirs."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def set_mtime(root: pathlib.Path, rel: str, mtime: float) -> None:
    """Set the atime+mtime of a repo-relative file (for freshness tests)."""
    os.utime(root / rel, (mtime, mtime))


def proc_result(returncode: int = 0, stdout: str = "", stderr: str = ""):
    """Build a ProcResult for a FakeProc handler. Lazily imports from
    tools/lib/proc, so call bootstrap() first."""
    from proc import ProcResult

    return ProcResult(returncode=returncode, stdout=stdout, stderr=stderr)


class FakeProc:
    """Test double for tools.lib.proc.Proc — the subprocess seam.

    Construct with a handler `(argv, cwd, env) -> ProcResult`; every call is
    recorded in `.calls` (a list of (argv, cwd, env) tuples) so a test can also
    assert WHICH commands ran. The handler decides each command's outcome, so a
    validator's compute path runs with no real gpg/git/python and no host
    keyring or network.

        proc = FakeProc(lambda argv, cwd, env:
            proc_result(0) if argv[:2] == ["gpg", "--verify"] else proc_result(1))
    """

    def __init__(self, handler):
        self._handler = handler
        self.calls: list[tuple] = []

    def run(self, argv, cwd=None, env=None):
        argv = list(argv)
        self.calls.append((argv, cwd, env))
        return self._handler(argv, cwd, env)
