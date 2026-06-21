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

    def test_signature_sidecar_suffix_is_skipped(self):
        # detached signatures and digests are not scanned by scan_file. these
        # suffixes never match SCAN_SUFFIXES, so drive scan_file directly.
        _write(self.root, "public/release.txt.asc", "signed over tools/\n")
        self.assertEqual(vpch.scan_file(self.repo, "release.txt.asc"), [])

    def test_binary_file_is_skipped_on_decode_error(self):
        # bytes that aren't valid utf-8 are skipped rather than crashing.
        _fixture.write_bytes(self.root, "public/blob.json", b"\xff\xfetools/\xff")
        r = vpch.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_token_on_last_line_without_trailing_newline(self):
        # a leak on the final line (no trailing "\n") still reports.
        _write(self.root, "public/tail.txt", "ok\nleaked generate_sri.py")
        r = vpch.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("generate_sri.py" in f and "tail.txt:2" in f for f in r.fails),
            r.fails,
        )

    def test_prefix_allowlist_skips_a_subtree(self):
        # exercise the path-prefix allowlist branch by seeding a prefix.
        original = vpch.ALLOWLIST_PREFIXES
        vpch.ALLOWLIST_PREFIXES = ("vendor/",)
        try:
            _write(self.root, "public/vendor/lib.js", "// tools/ build artefact\n")
            r = vpch.evaluate(self.repo)
            self.assertTrue(r.ok, msg=r.fails)
        finally:
            vpch.ALLOWLIST_PREFIXES = original


class ExternalInterface(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_main(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vpch.main(self.root)
        return rc, buf.getvalue()

    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vpch.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_main_missing_public_dir_fails(self):
        # a fixture root with no public/ tree fails before evaluate().
        rc, out = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("public root not found", out)

    def test_main_renders_fail_on_seeded_leak(self):
        # the dominant gap: a seeded defect drives main() through the
        # fail-render branch — nonzero exit and a printed FAIL line.
        _write(
            self.root,
            "public/index.html",
            "<p>hi</p>\n<!-- built by generate_site.py -->\n",
        )
        rc, out = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("FAIL: public-comment-hygiene", out)
        self.assertIn("generate_site.py", out)

    def test_main_truncates_to_forty_leaks(self):
        # more than 40 leaks render the "… N more" tail line.
        body = "\n".join(f"<!-- leak {i} generate_site.py -->" for i in range(45))
        _write(self.root, "public/index.html", body + "\n")
        rc, out = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("more", out)

    def test_main_clean_tree_passes(self):
        # a public tree with no leaks exits 0 with the OK line.
        _write(self.root, "public/index.html", "<!-- the edition -->\n<p>hi</p>\n")
        rc, out = self._run_main()
        self.assertEqual(rc, 0)
        self.assertIn("OK: public-comment-hygiene", out)


if __name__ == "__main__":
    unittest.main()
