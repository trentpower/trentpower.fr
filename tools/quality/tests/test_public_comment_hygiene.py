#!/usr/bin/env python3
"""Tests for the public-comment-hygiene gate
(tools/quality/validate_public_comment_hygiene.py).

Cross `evaluate(Repo)` over a fixture repo. Assert on the Result.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_public_comment_hygiene as vpch  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vpch.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_tree_green(self):
        # an author-voiced deployed page with no internal names is clean.
        _write(self.root, "public/index.html", "<!-- the edition · 2026 -->\n<p>hello</p>\n")
        _write(self.root, "public/styles.css", "/* tokens */\nbody{color:#000}\n")
        r = vpch.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_seeded_generator_name_in_comment_fails(self):
        # a deployed comment naming a generator script is the leak this gate
        # exists to catch.
        _write(
            self.root,
            "public/index.html",
            "<p>hi</p>\n<!-- built by generate_site.py -->\n",
        )
        r = vpch.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("generate_site.py" in f and "index.html:2" in f for f in r.fails),
            r.fails,
        )

    def test_seeded_tools_path_in_comment_fails(self):
        # naming the tools/ machinery in deployed bytes is likewise a leak.
        _write(self.root, "public/app.js", "// see tools/build/generate_sw.py\n")
        r = vpch.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("tools/" in f for f in r.fails), r.fails)

    def test_allowlisted_changelog_is_skipped(self):
        # the editorial changelog archive is allowed to name the machinery.
        _write(self.root, "public/changelog.txt", "ran generate_site.py via tools/\n")
        r = vpch.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_frozen_release_archive_body_is_skipped(self):
        # non-html frozen-archive bodies are not scanned.
        _write(
            self.root,
            "public/integrity/releases/2026-02/manifest.txt",
            "generated_by tools/\n",
        )
        r = vpch.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vpch.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
