#!/usr/bin/env python3
"""Tests for the pure route-map validation in tools/lib/routes.py.

`_check_slug` and `_validate` are the allowlist that keeps a malformed or unsafe
route map (path traversal, absolute slugs, missing languages) out of every
generated path, canonical URL and public file. They take plain args, so each
rejection is asserted directly — no real routes.yml, no repo.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

from __future__ import annotations

import unittest

import _fixture

_fixture.bootstrap()

import routes  # noqa: E402


def _valid_map():
    return {
        "site": {"languages": ["en", "fr"], "default_language": "en"},
        "routes": {"home": {"slug": {"en": "", "fr": ""}}},
        "error_routes": {},
        "root_routes": {},
        "legacy_redirects": {},
    }


class CheckSlug(unittest.TestCase):
    def test_non_string_rejected(self):
        with self.assertRaises(ValueError):
            routes._check_slug("home", "en", 123)

    def test_empty_is_the_home_route(self):
        self.assertIsNone(routes._check_slug("home", "en", ""))

    def test_malformed_forms_rejected(self):
        for bad in (" leading", "trailing ", "a\\b", "/abs", "abs/"):
            with self.assertRaises(ValueError):
                routes._check_slug("k", "en", bad)

    def test_unsafe_segment_rejected(self):
        for bad in ("..", "../etc", "UPPER", "a/../b", "spa ce"):
            with self.assertRaises(ValueError):
                routes._check_slug("k", "en", bad)

    def test_valid_multi_segment_ok(self):
        self.assertIsNone(routes._check_slug("k", "en", "a/b-c/d2"))


class Validate(unittest.TestCase):
    def test_missing_top_level_key(self):
        d = _valid_map()
        del d["routes"]
        with self.assertRaises(ValueError):
            routes._validate(d)

    def test_languages_must_be_nonempty_list(self):
        d = _valid_map()
        d["site"]["languages"] = []
        with self.assertRaises(ValueError):
            routes._validate(d)

    def test_default_language_must_be_listed(self):
        d = _valid_map()
        d["site"]["default_language"] = "de"
        with self.assertRaises(ValueError):
            routes._validate(d)

    def test_slug_must_be_a_map(self):
        d = _valid_map()
        d["routes"]["home"]["slug"] = "not-a-dict"
        with self.assertRaises(ValueError):
            routes._validate(d)

    def test_missing_slug_for_a_language(self):
        d = _valid_map()
        d["routes"]["home"]["slug"] = {"en": ""}  # no fr
        with self.assertRaises(ValueError):
            routes._validate(d)

    def test_valid_map_passes(self):
        self.assertIsNone(routes._validate(_valid_map()))


class CounterpartPath(unittest.TestCase):
    def test_requires_exactly_two_languages(self):
        saved = routes.languages
        routes.languages = lambda: ["en", "fr", "de"]
        try:
            with self.assertRaises(ValueError):
                routes.counterpart_path("home", "en")
        finally:
            routes.languages = saved


if __name__ == "__main__":
    unittest.main()
