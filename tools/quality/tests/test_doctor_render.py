#!/usr/bin/env python3
"""Light behavioural tests for tools/quality/doctor.sh — the ceremony.

Deliberately NOT pinned to exact box characters or spacing (that would be
brittle). We assert the contract the renderer must keep: plain transcripts carry
no escape codes, a verdict is always reported, expected-missing pieces still exit
0, and a missing python3 exits non-zero with a clean blocked message rather than
a stack trace. Visual fidelity (panels, colour) is the job of term.sh, already
exercised by the build ceremony.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[2]
_DOCTOR_SH = _TOOLS / "quality" / "doctor.sh"
_ESC = "\033"


def _run(args, env_extra=None, path=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    if path is not None:
        env["PATH"] = path
    bash = shutil.which("bash")
    return subprocess.run(
        [bash, str(_DOCTOR_SH), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


class PlainTranscript(unittest.TestCase):
    def test_explicit_plain_flag_has_no_escapes_and_exits_clean(self):
        r = _run(["--plain"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(_ESC, r.stdout)
        self.assertIn("CAPABILITY", r.stdout)
        self.assertIn("Mode", r.stdout)

    def test_no_color_env_produces_plain(self):
        r = _run([], env_extra={"NO_COLOR": "1"})
        self.assertNotIn(_ESC, r.stdout)
        self.assertEqual(r.returncode, 0)

    def test_term_dumb_produces_plain(self):
        r = _run([], env_extra={"TERM": "dumb"})
        self.assertNotIn(_ESC, r.stdout)
        self.assertEqual(r.returncode, 0)

    def test_reports_a_known_mode(self):
        r = _run(["--plain"])
        self.assertRegex(r.stdout, r"Mode\s+(full|partial|archive|blocked)")


class PythonMissing(unittest.TestCase):
    def test_missing_python3_exits_nonzero_without_traceback(self):
        # a PATH that resolves `dirname` (needed before the python3 probe) but
        # not python3 — the script must fail plainly, not source-crash.
        dirname = shutil.which("dirname")
        if not dirname:
            self.skipTest("dirname not available to build the stripped PATH")
        with tempfile.TemporaryDirectory() as tmp:
            os.symlink(dirname, os.path.join(tmp, "dirname"))
            r = _run([], path=tmp)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("python3 not found", r.stderr)
            self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
