#!/usr/bin/env python3
"""Tests for the public-surface helpers in tools/lib/public_inventory.py.

page_outputs() / error_page_outputs() are the route-derived disk-path lists
that the integrity-manifest and asset-version gates walk. They were lifted out
of inline_checks.py verbatim; these tests pin their shape so a route-map change
that silently drops a page is caught.

Stdlib unittest — no pytest dep.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import unittest

import _fixture  # noqa: E402

_fixture.bootstrap()

import public_inventory as pi  # noqa: E402
import routes as routes  # noqa: E402


class PageOutputs(unittest.TestCase):
    def test_one_entry_per_route_per_language(self):
        outs = pi.page_outputs()
        self.assertEqual(len(outs), len(routes.route_keys()) * len(routes.languages()))

    def test_paths_are_public_relative_index_html(self):
        for rel in pi.page_outputs():
            self.assertFalse(rel.startswith("/"), rel)
            self.assertTrue(rel.endswith("index.html"), rel)

    def test_both_language_trees_present(self):
        outs = pi.page_outputs()
        self.assertTrue(any(r.startswith("en-au/") for r in outs), outs)
        self.assertTrue(any(r.startswith("fr/") for r in outs), outs)

    def test_deterministic_order(self):
        self.assertEqual(pi.page_outputs(), pi.page_outputs())


class ErrorPageOutputs(unittest.TestCase):
    def test_four_error_docs_per_language(self):
        errs = pi.error_page_outputs()
        self.assertEqual(len(errs), len(routes.languages()) * 4)

    def test_expected_documents(self):
        errs = set(pi.error_page_outputs())
        for lang_seg in ("en-au", "fr"):
            for doc in ("403.html", "404.html", "500.html", "maintenance.html"):
                self.assertIn(f"{lang_seg}/{doc}", errs)


if __name__ == "__main__":
    unittest.main()
