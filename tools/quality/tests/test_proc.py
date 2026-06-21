#!/usr/bin/env python3
"""Tests for the subprocess seam (tools/lib/proc.py) and its FakeProc double.

The production Proc is exercised against tiny real commands; FakeProc is checked
for the record-and-delegate contract validators rely on.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import unittest

import _fixture

_fixture.bootstrap()

from proc import Proc, ProcResult  # noqa: E402


class ProductionProc(unittest.TestCase):
    def test_captures_stdout_and_zero_exit(self):
        r = Proc().run(["printf", "hello"])
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "hello")

    def test_nonzero_exit_does_not_raise(self):
        r = Proc().run(["false"])
        self.assertNotEqual(r.returncode, 0)

    def test_stderr_captured(self):
        # sh writes the message to stderr; we should capture it, not raise.
        r = Proc().run(["sh", "-c", "echo oops 1>&2; exit 3"])
        self.assertEqual(r.returncode, 3)
        self.assertIn("oops", r.stderr)

    def test_non_utf8_output_decodes_tolerantly(self):
        # git history (e.g. `git log -p`) can carry non-UTF-8 bytes; the seam must
        # decode tolerantly rather than raising UnicodeDecodeError, which would
        # crash the secret/history scan instead of reporting findings.
        r = Proc().run(["sh", "-c", r"printf '\377'"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("�", r.stdout)  # the 0xff byte became U+FFFD, not a crash


class Fake(unittest.TestCase):
    def test_handler_decides_outcome_and_calls_recorded(self):
        def handler(argv, cwd, env):
            if argv[:2] == ["git", "ls-files"]:
                return _fixture.proc_result(0, "a\nb\n")
            return _fixture.proc_result(1, "", "unknown")

        fp = _fixture.FakeProc(handler)
        self.assertEqual(fp.run(["git", "ls-files", "-z"]).stdout, "a\nb\n")
        self.assertEqual(fp.run(["gpg", "--verify"]).returncode, 1)
        self.assertEqual(len(fp.calls), 2)
        self.assertEqual(fp.calls[0][0], ["git", "ls-files", "-z"])

    def test_cwd_and_env_recorded(self):
        fp = _fixture.FakeProc(lambda argv, cwd, env: _fixture.proc_result(0))
        fp.run(["x"], cwd="/tmp", env={"K": "V"})
        _, cwd, env = fp.calls[0]
        self.assertEqual(cwd, "/tmp")
        self.assertEqual(env, {"K": "V"})

    def test_proc_result_shape(self):
        self.assertIsInstance(_fixture.proc_result(0), ProcResult)


if __name__ == "__main__":
    unittest.main()
