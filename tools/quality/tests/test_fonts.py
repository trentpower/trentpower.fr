#!/usr/bin/env python3
"""Tests for the font-existence gate (tools/quality/validate_fonts.py).

Cross `evaluate(Repo)` over a fixture repo. Assert on the Result. A separate
ExternalInterface test crosses `main()` against the real repo for the RC
contract.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_fonts as vf  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent


def _seed_pristine(root: pathlib.Path) -> None:
    """A small coherent fixture: one font on disk, referenced from CSS, the SW
    manifest, and the integrity manifest. No preloads. Resolves green."""
    _write(root, "public/fonts/plex.woff2", "FONTBYTES")
    _write(
        root,
        "public/styles.css",
        "@font-face{src:url('/fonts/plex.woff2') format('woff2')}\n",
    )
    _write(root, "public/index.html", "<html><head></head><body></body></html>\n")
    _write(
        root,
        "public/sw-cache-manifest.json",
        '{"critical": ["/fonts/plex.woff2"], "optional": []}\n',
    )
    _write(root, "public/integrity.json", '{"files": {"fonts/plex.woff2": "sha256-x"}}\n')


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vf.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pristine_fixture_green(self):
        _seed_pristine(self.root)
        r = vf.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(len(r.css_refs), 1)
        self.assertEqual(len(r.html_refs), 0)
        self.assertEqual(len(r.sw_refs), 1)
        self.assertEqual(len(r.integ_refs), 1)

    def test_declared_font_missing_on_disk_fails(self):
        # CSS references a weight that was never shipped.
        _seed_pristine(self.root)
        _write(
            self.root,
            "public/styles.css",
            "@font-face{src:url('/fonts/plex.woff2') format('woff2')}\n"
            "@font-face{src:url('/fonts/plex-bold.woff2') format('woff2')}\n",
        )
        r = vf.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("MISSING: /fonts/plex-bold.woff2" in f for f in r.fails), r.fails
        )

    def test_orphan_font_on_disk_fails(self):
        # A font ships but nothing references it.
        _seed_pristine(self.root)
        _write(self.root, "public/fonts/orphan.woff2", "ORPHANBYTES")
        r = vf.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("ORPHAN: /fonts/orphan.woff2" in f for f in r.fails), r.fails
        )


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vf.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
