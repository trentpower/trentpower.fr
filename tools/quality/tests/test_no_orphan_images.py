#!/usr/bin/env python3
"""Tests for the orphan-image gate
(tools/quality/validate_no_orphan_images.py).

Cross `load()`/`evaluate(Repo, Ctx)` over a fixture repo. Assert on the Result.
The ExternalInterface case runs the real `main()` against this repo and asserts
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

import validate_no_orphan_images as vnoi  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent

# the live LANGS list the generator declares; fixtures stamp the same source so
# load() resolves the same two-language ctx the real repo carries.
_ARCH_GENERATOR_SRC = 'LANGS = ["en", "fr"]\n'


def _seed_arch_generator(root: pathlib.Path) -> None:
    _write(root, "tools/build/_generate_architecture_svgs.py", _ARCH_GENERATOR_SRC)


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vnoi.Repo(self.root)
        _seed_arch_generator(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _ctx(self):
        ctx, errors = vnoi.load(self.repo)
        self.assertEqual(errors, [])
        self.assertIsNotNone(ctx)
        return ctx

    def test_every_image_referenced_is_green(self):
        # one image referenced by its web path, one by basename via CSS.
        _write(self.root, "public/images/og/home-og.png", "\x89PNG")
        _write(self.root, "public/images/logo.svg", "<svg/>")
        _write(
            self.root,
            "public/index.html",
            '<meta property="og:image" content="/images/og/home-og.png">\n',
        )
        _write(self.root, "public/styles.css", "body{background:url(images/logo.svg)}\n")
        r = vnoi.evaluate(self.repo, self._ctx())
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(
            any("every image under /images/ is referenced" in o for o in r.oks), r.oks
        )

    def test_seeded_orphan_image_is_caught(self):
        # referenced image keeps the corpus non-trivial; orphan is referenced
        # nowhere — not in HTML, CSS, JS, JSON, or templates.
        _write(self.root, "public/images/logo.svg", "<svg/>")
        _write(self.root, "public/images/orphan.png", "\x89PNG")
        _write(self.root, "public/index.html", '<img src="/images/logo.svg">\n')
        r = vnoi.evaluate(self.repo, self._ctx())
        self.assertFalse(r.ok)
        self.assertTrue(any("/images/orphan.png" in f for f in r.fails), r.fails)
        self.assertTrue(any("1 orphan image(s)" in f for f in r.fails), r.fails)

    def test_manifest_only_reference_does_not_save_image(self):
        # an image cited only by a disk-describing manifest is still an orphan.
        _write(self.root, "public/images/lonely.png", "\x89PNG")
        _write(
            self.root,
            "public/integrity.json",
            '{"files":{"images/lonely.png":"abc"}}\n',
        )
        r = vnoi.evaluate(self.repo, self._ctx())
        self.assertFalse(r.ok)
        self.assertTrue(any("/images/lonely.png" in f for f in r.fails), r.fails)


class Load(unittest.TestCase):
    def test_missing_langs_surfaces_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            _write(root, "tools/build/_generate_architecture_svgs.py", "# no langs here\n")
            ctx, errors = vnoi.load(vnoi.Repo(root))
            self.assertIsNone(ctx)
            self.assertTrue(any("cannot read LANGS" in e for e in errors), errors)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vnoi.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
