#!/usr/bin/env python3
"""Tests for the documentation-links gate (validate_docs_links.py).

Cross the module interface `evaluate(repo, tracked) -> Result` over a fixture
repo with the git-tracked SET injected directly (no real git). Assert on the
Result, never on stdout.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_docs_links as vl  # noqa: E402
from _fixture import write as _write  # noqa: E402


def _tracked(root: pathlib.Path, *extra: str) -> set[str]:
    files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    return files | set(extra)


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vl.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _eval(self, *extra):
        return vl.evaluate(self.repo, _tracked(self.root, *extra))

    def test_pristine_all_green(self):
        _write(self.root, "README.md", "# T\n\nSee [coverage](docs/COVERAGE.md).\n")
        _write(self.root, "docs/COVERAGE.md", "# Coverage\n")
        r = self._eval()
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.warns, [])

    def test_broken_relative_link_fails(self):
        _write(self.root, "README.md", "# T\n\nSee [gone](docs/GONE.md).\n")
        r = self._eval()
        self.assertFalse(r.ok)
        self.assertTrue(any("docs/GONE.md" in f for f in r.fails))

    def test_broken_image_svg_fails(self):
        _write(self.root, "README.md", "# T\n\n![badge](badges/missing.svg)\n")
        r = self._eval()
        self.assertFalse(r.ok)
        self.assertTrue(any("badges/missing.svg" in f for f in r.fails))

    def test_link_inside_code_block_ignored(self):
        _write(
            self.root,
            "README.md",
            "# T\n\n```sh\n[![x](metadata/badges/gone.svg)](https://x)\n```\n",
        )
        r = self._eval()
        self.assertTrue(r.ok, msg=r.fails)

    def test_indented_code_link_ignored(self):
        _write(self.root, "README.md", "# T\n\nExample:\n\n    [x](docs/GONE.md)\n")
        r = self._eval()
        self.assertTrue(r.ok, msg=r.fails)

    def test_external_link_skipped(self):
        _write(self.root, "README.md", "# T\n\n[site](https://trentpower.fr/) and [m](mailto:x@y).\n")
        r = self._eval()
        self.assertTrue(r.ok, msg=r.fails)

    def test_directory_link_resolves_via_prefix(self):
        _write(self.root, "README.md", "# T\n\nSee the [tests](tools/quality/tests/).\n")
        # a tracked file lives under the directory, so the dir link ships.
        r = self._eval("tools/quality/tests/test_x.py")
        self.assertTrue(r.ok, msg=r.fails)

    def test_good_same_doc_anchor_no_warn(self):
        _write(self.root, "README.md", "# Title\n\n## Big Section\n\njump to [it](#big-section).\n")
        r = self._eval()
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.warns, [])

    def test_bad_anchor_warns_not_fails(self):
        _write(self.root, "README.md", "# Title\n\njump to [it](#no-such-heading).\n")
        r = self._eval()
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("anchor" in w for w in r.warns))

    def test_cross_doc_anchor_warns(self):
        _write(self.root, "README.md", "# T\n\nSee [x](docs/COVERAGE.md#missing).\n")
        _write(self.root, "docs/COVERAGE.md", "# Coverage\n\n## Real Heading\n")
        r = self._eval()
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("docs/COVERAGE.md#missing" in w for w in r.warns))

    def test_double_hyphen_slug_matches(self):
        # GitHub maps "A & B" -> "a--b"; our slugger must agree (no warn).
        _write(self.root, "README.md", "# Title\n\n## A & B\n\n[go](#a--b)\n")
        r = self._eval()
        self.assertEqual(r.warns, [], msg=r.warns)


class ExternalInterface(unittest.TestCase):
    """main() over the real repo — exercises the git adapter and asserts the
    live documentation has no broken internal links."""

    def test_main_passes_against_the_real_repo(self):
        self.assertEqual(vl.main(TOOLS.parent), 0)


if __name__ == "__main__":
    unittest.main()
