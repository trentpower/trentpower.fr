#!/usr/bin/env python3
"""Tests for the source-mirror readability gate
(tools/verify/validate_source_mirror_readability.py).

Cross `evaluate(Repo)` over a fixture repo. Assert on the Result.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_source_mirror_readability as vsmr  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent


def _good_mirror() -> str:
    """A readable authored-source mirror: banner first line + > MIN_LINES."""
    body = "\n".join(f"line {i}" for i in range(vsmr.MIN_LINES + 2))
    return f"// authored source — banner\n{body}\n"


def _pristine(root: pathlib.Path) -> None:
    for name in vsmr.REMAPPED_MIRRORS:
        _write(root, f"{vsmr.SOURCE_DIR_REL}/{name}", _good_mirror())


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vsmr.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pristine_fixture_green(self):
        _pristine(self.root)
        r = vsmr.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_minified_single_line_fails(self):
        _pristine(self.root)
        # overwrite one mirror with a minified one-liner (still carries banner).
        _write(
            self.root,
            f"{vsmr.SOURCE_DIR_REL}/{vsmr.REMAPPED_MIRRORS[0]}",
            "// authored source minified\n",
        )
        r = vsmr.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("likely minified" in f for f in r.fails), r.fails)

    def test_missing_banner_fails(self):
        _pristine(self.root)
        body = "\n".join(f"line {i}" for i in range(vsmr.MIN_LINES + 2))
        _write(
            self.root,
            f"{vsmr.SOURCE_DIR_REL}/{vsmr.REMAPPED_MIRRORS[0]}",
            f"// no banner here\n{body}\n",
        )
        r = vsmr.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("missing 'authored source' banner" in f for f in r.fails), r.fails)

    def test_missing_mirror_fails(self):
        _pristine(self.root)
        (self.root / vsmr.SOURCE_DIR_REL / vsmr.REMAPPED_MIRRORS[0]).unlink()
        r = vsmr.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("missing" in f for f in r.fails), r.fails)

    def test_no_source_dir_fails(self):
        r = vsmr.evaluate(self.repo)
        self.assertFalse(r.ok)


class ExternalInterface(unittest.TestCase):
    def test_main_matches_baseline_rc_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vsmr.main(REPO_ROOT)
        # baseline RC is 0 (see .build/cmig-baseline/...readability.txt).
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    sys.exit(unittest.main())
