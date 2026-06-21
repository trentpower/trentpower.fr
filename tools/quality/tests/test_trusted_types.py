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


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vtt.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
