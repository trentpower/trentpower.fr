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

    def test_missing_og_and_icons_dirs_fail(self):
        # neither canonical tree exists -> both dir-existence branches fire.
        r = vi.evaluate(self.repo, [])
        self.assertFalse(r.ok)
        self.assertTrue(any("missing canonical OG dir" in f for f in r.fails), r.fails)
        self.assertTrue(
            any("missing canonical icons dir" in f for f in r.fails), r.fails
        )
        self.assertEqual(r.png_count, 0)

    @unittest.skipUnless(_PILImage is not None, "Pillow not installed")
    def test_oversized_png_hard_limit_fail(self):
        # a seeded defect: a correctly-sized PNG whose byte size exceeds the
        # hard limit -> the FAIL_BYTES branch fires.
        p = self.root / "public/images/og/home-og.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        # noise makes the png incompressible so it clears the 500 KB hard limit.
        import os as _os

        import PIL.Image as _Img

        _Img.frombytes(
            "RGB",
            (vi.CANONICAL_W, vi.CANONICAL_H),
            _os.urandom(vi.CANONICAL_W * vi.CANONICAL_H * 3),
        ).save(p)
        self.assertGreater(self.repo.size("public/images/og/home-og.png"), vi.FAIL_BYTES)
        self._seed_icons()
        _write(
            self.root,
            "public/index.html",
            '<meta property="og:image" content="https://trentpower.fr/images/og/home-og.png">',
        )
        r = vi.evaluate(self.repo, ["index.html"])
        self.assertFalse(r.ok)
        self.assertTrue(any("hard limit" in f for f in r.fails), r.fails)

    @unittest.skipUnless(_PILImage is not None, "Pillow not installed")
    def test_alpha_channel_fail(self):
        # a seeded defect: an RGBA png keeps its alpha channel -> alpha branch.
        p = self.root / "public/images/og/home-og.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        _PILImage.new("RGBA", (vi.CANONICAL_W, vi.CANONICAL_H)).save(p)
        self._seed_icons()
        _write(
            self.root,
            "public/index.html",
            '<meta property="og:image" content="https://trentpower.fr/images/og/home-og.png">',
        )
        r = vi.evaluate(self.repo, ["index.html"])
        self.assertFalse(r.ok)
        self.assertTrue(any("alpha channel present" in f for f in r.fails), r.fails)

    @unittest.skipUnless(_PILImage is not None, "Pillow not installed")
    def test_unreadable_png_fail(self):
        # a seeded defect: a .png that is not actually a png -> the read raises
        # and the cannot-read branch fires.
        _write(self.root, "public/images/og/home-og.png", "not really a png")
        self._seed_icons()
        r = vi.evaluate(self.repo, [])
        self.assertFalse(r.ok)
        self.assertTrue(any("cannot read" in f for f in r.fails), r.fails)

    def test_bad_og_reference_and_legacy_social_fail(self):
        # a seeded defect: html declares an og:image that is neither an
        # /images/og/*.png nor the portrait jpg, and points at legacy social.
        self._seed_icons()
        _write(self.root, "public/images/og", "")  # placeholder so dir exists
        (self.root / "public/images/og").unlink()
        (self.root / "public/images/og").mkdir(parents=True, exist_ok=True)
        _write(
            self.root,
            "public/bad.html",
            '<meta property="og:image" '
            'content="https://trentpower.fr/images/social/old.png">',
        )
        r = vi.evaluate(self.repo, ["bad.html"])
        self.assertFalse(r.ok)
        self.assertTrue(any("must be /images/og/" in f for f in r.fails), r.fails)
        self.assertTrue(any("stale legacy" in f for f in r.fails), r.fails)

    def test_webp_og_reference_fail(self):
        # a seeded defect: an og:image pointing at a .webp -> the explicit
        # webp/avif rejection branch fires.
        self._seed_icons()
        (self.root / "public/images/og").mkdir(parents=True, exist_ok=True)
        _write(
            self.root,
            "public/bad.html",
            '<meta property="og:image" '
            'content="https://trentpower.fr/images/og/home-og.webp">',
        )
        r = vi.evaluate(self.repo, ["bad.html"])
        self.assertFalse(r.ok)
        self.assertTrue(any("must be PNG, not webp" in f for f in r.fails), r.fails)

    def test_missing_active_html_fail(self):
        # a seeded defect: an active html path that does not exist on disk.
        self._seed_icons()
        (self.root / "public/images/og").mkdir(parents=True, exist_ok=True)
        r = vi.evaluate(self.repo, ["ghost.html"])
        self.assertFalse(r.ok)
        self.assertTrue(any("missing active HTML" in f for f in r.fails), r.fails)

    @unittest.skipUnless(_PILImage is not None, "Pillow not installed")
    def test_orphan_canonical_png_warns(self):
        # a correctly-sized png that no html references and is not allowlisted
        # -> a warning (not a fail), exercising the orphan branch.
        _save_png(self.root, "public/images/og/lonely.png", vi.CANONICAL_W, vi.CANONICAL_H)
        self._seed_icons()
        r = vi.evaluate(self.repo, [])
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("not referenced" in w for w in r.warns), r.warns)

    def test_derivative_without_master_fail(self):
        # seeded defects: a .webp and a .avif derivative with no png master.
        self._seed_icons()
        (self.root / "public/images/og").mkdir(parents=True, exist_ok=True)
        _write(self.root, "public/images/og/x.webp", "webp")
        _write(self.root, "public/images/og/y.avif", "avif")
        r = vi.evaluate(self.repo, [])
        self.assertFalse(r.ok)
        self.assertEqual(
            sum("derivative without master PNG" in f for f in r.fails), 2, r.fails
        )

    def test_missing_canonical_icon_fail(self):
        # root copy exists but the /images/icons/ canonical is absent.
        (self.root / "public/images/icons").mkdir(parents=True, exist_ok=True)
        for fn in vi.ROOT_ICON_FILES:
            _write(self.root, f"public/{fn}", f"icon:{fn}")
        r = vi.evaluate(self.repo, [])
        self.assertFalse(r.ok)
        self.assertTrue(
            any("missing canonical icon" in f for f in r.fails), r.fails
        )

    def test_icon_byte_mismatch_fail(self):
        # root and canonical icons exist but differ -> the byte-equality fail.
        for fn in vi.ROOT_ICON_FILES:
            _write(self.root, f"public/{fn}", f"root:{fn}")
            _write(self.root, f"public/images/icons/{fn}", f"canon:{fn}")
        r = vi.evaluate(self.repo, [])
        self.assertFalse(r.ok)
        self.assertTrue(any("differs from /images/icons/" in f for f in r.fails), r.fails)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vi.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_main_returns_1_and_renders_fails_over_failing_fixture(self):
        # main() over a deliberately empty fixture repo: neither canonical tree
        # exists, so evaluate() fails and main() must render the FAIL block to
        # stderr and return 1. this is the dominant uncovered branch.
        import contextlib
        import io
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            out = io.StringIO()
            err = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = vi.main(root)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL:", err.getvalue())
        self.assertIn("✗", err.getvalue())
        self.assertIn("image-system issue", err.getvalue())

    @unittest.skipUnless(_PILImage is not None, "Pillow not installed")
    def test_main_renders_warnings_block(self):
        # main() over a fixture whose only defect is warn-tier (an orphan
        # canonical png) renders the WARNINGS block on stdout and still passes.
        import contextlib
        import io
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _save_png(
                root, "public/images/og/lonely.png", vi.CANONICAL_W, vi.CANONICAL_H
            )
            for fn in vi.ROOT_ICON_FILES:
                body = f"icon:{fn}"
                _write(root, f"public/{fn}", body)
                _write(root, f"public/images/icons/{fn}", body)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = vi.main(root)
        self.assertEqual(rc, 0, msg=out.getvalue())
        self.assertIn("WARNINGS", out.getvalue())
        self.assertIn("!", out.getvalue())


if __name__ == "__main__":
    unittest.main()
