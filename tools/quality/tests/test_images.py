#!/usr/bin/env python3
"""Tests for the image-system gate (tools/quality/validate_images.py).

Cross `evaluate(Repo, active_html)` over a fixture repo: a tiny coherent image
tree exercises the full compute path with no monkeypatching. Assert on the
Result. PIL/Pillow is a direct binary library (not a seam), so tests that must
GENERATE a real PNG are skipped when Pillow is absent — mirroring the validator's
own graceful degrade. Assert on the Result.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import unittest

import _fixture

_fixture.bootstrap()

import validate_images as vi  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

try:
    from PIL import Image as _PILImage
except ImportError:
    _PILImage = None


def _save_png(root: pathlib.Path, rel: str, w: int, h: int) -> None:
    """generate a real PNG at the given dimensions under a repo-relative path."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    _PILImage.new("RGB", (w, h)).save(p)


class Evaluate(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vi.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _seed_icons(self):
        # five root icons byte-equal to their /images/icons/ canonical copies.
        for fn in vi.ROOT_ICON_FILES:
            body = f"icon:{fn}"
            _write(self.root, f"public/{fn}", body)
            _write(self.root, f"public/images/icons/{fn}", body)

    @unittest.skipUnless(_PILImage is not None, "Pillow not installed")
    def test_correct_dims_green(self):
        # one canonical PNG at the expected dimensions, referenced from html,
        # plus matching icon pairs -> green via evaluate().
        _save_png(self.root, "public/images/og/home-og.png", vi.CANONICAL_W, vi.CANONICAL_H)
        self._seed_icons()
        _write(
            self.root,
            "public/index.html",
            '<meta property="og:image" content="https://trentpower.fr/images/og/home-og.png">',
        )
        r = vi.evaluate(self.repo, ["index.html"])
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.png_count, 1)

    @unittest.skipUnless(_PILImage is not None, "Pillow not installed")
    def test_wrong_dimensions_fail(self):
        # a seeded defect: the PNG is the wrong size -> caught via evaluate().
        _save_png(self.root, "public/images/og/home-og.png", 800, 600)
        self._seed_icons()
        _write(
            self.root,
            "public/index.html",
            '<meta property="og:image" content="https://trentpower.fr/images/og/home-og.png">',
        )
        r = vi.evaluate(self.repo, ["index.html"])
        self.assertFalse(r.ok)
        self.assertTrue(
            any("expected 1200×630" in f for f in r.fails), r.fails
        )

    def test_missing_declared_image_fails(self):
        # a seeded defect that needs no PIL: a declared root icon is absent ->
        # caught via evaluate(). icons dir present, root copies missing.
        for fn in vi.ROOT_ICON_FILES:
            _write(self.root, f"public/images/icons/{fn}", f"icon:{fn}")
        # no root /<fn> copies written, and no OG dir.
        r = vi.evaluate(self.repo, [])
        self.assertFalse(r.ok)
        self.assertTrue(
            any("missing root icon" in f for f in r.fails), r.fails
        )


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vi.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
