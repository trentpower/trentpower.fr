#!/usr/bin/env python3
"""Tests for the Trusted Types gate
(tools/quality/validate_trusted_types.py).

Cross `evaluate(Repo)` over a fixture repo and assert on the Result; one
ExternalInterface case runs `main(REPO_ROOT)` against the real repo to pin
the baseline exit code.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_trusted_types as vtt  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent


def _clean_repo(root: pathlib.Path) -> None:
    """populate every SCAN_FILE with clean JS so evaluate() goes green."""
    for rel in vtt.SCAN_FILES:
        _write(root, rel, "const x = document.querySelector('.x');\n")


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vtt.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_fixture_green(self):
        _clean_repo(self.root)
        r = vtt.evaluate(self.repo)
        self.assertTrue(r.ok, msg=(r.fails, r.stale))
        self.assertTrue(r.oks and r.oks[0].startswith("OK: Trusted Types"))

    def test_innerhtml_sink_caught(self):
        _clean_repo(self.root)
        _write(self.root, "public/js/copy.js", "el.innerHTML = userInput;\n")
        r = vtt.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("innerHTML assignment" in f and "public/js/copy.js:1" in f for f in r.fails),
            msg=r.fails,
        )

    def test_retired_tp_i18n_policy_caught(self):
        _clean_repo(self.root)
        # seed the retired policy name in an in-scope retired-scan file.
        _write(self.root, "public/.htaccess", "# tp-i18n policy reference\n")
        r = vtt.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertEqual(r.fails, [])  # not a sink failure
        self.assertIn("public/.htaccess", r.stale)


    def test_missing_scan_file_caught(self):
        # leave one SCAN_FILE absent; _scan_file reports it as missing rather
        # than reading it (covers the FILE MISSING early return).
        _clean_repo(self.root)
        (self.root / vtt.SCAN_FILES[0]).unlink()
        r = vtt.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any(f.startswith(f"FILE MISSING: {vtt.SCAN_FILES[0]}") for f in r.fails),
            msg=r.fails,
        )


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vtt.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


class MainOverFixture(unittest.TestCase):
    """drive main() over fixture repos so its side-effecting render branches
    (fail / stale) are exercised, not only the green real-repo path."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_main(self):
        import contextlib
        import io

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = vtt.main(self.root)
        return rc, out.getvalue(), err.getvalue()

    def test_main_returns_1_and_renders_sink_failure(self):
        # seed one unsafe sink so evaluate() returns fails; main() must exit 1
        # and print the FAIL header plus the per-finding line to stderr.
        _clean_repo(self.root)
        _write(self.root, "public/js/copy.js", "el.innerHTML = userInput;\n")
        rc, out, err = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("Trusted Types sink violation(s)", err)
        self.assertIn("public/js/copy.js:1", err)
        self.assertIn("Wrap unsafe sinks via the tp-app policy", err)
        self.assertEqual(out, "")

    def test_main_truncates_when_over_thirty_fails(self):
        # one sink per scan file is not enough; pack >30 sink lines into a
        # single file so main() renders the "… and N more" truncation tail.
        _clean_repo(self.root)
        many = "".join(f"el.innerHTML = v{i};\n" for i in range(35))
        _write(self.root, "public/js/copy.js", many)
        rc, _out, err = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("… and 5 more", err)

    def test_main_returns_1_and_renders_stale_policy(self):
        # clean sinks but a retired tp-i18n reference: main() takes the stale
        # branch, exits 1, and lists the offending file on stderr.
        _clean_repo(self.root)
        _write(self.root, "public/.htaccess", "# tp-i18n policy reference\n")
        rc, out, err = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("retired `tp-i18n`", err)
        self.assertIn("public/.htaccess", err)
        self.assertEqual(out, "")

    def test_main_returns_0_and_prints_ok_on_clean_fixture(self):
        # green fixture: main() prints the OK line to stdout and exits 0.
        _clean_repo(self.root)
        rc, out, err = self._run_main()
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith("OK: Trusted Types"), msg=out)
        self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
