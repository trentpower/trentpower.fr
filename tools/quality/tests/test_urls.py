#!/usr/bin/env python3
"""Tests for tools/lib/urls.py — host matching that resists substring spoofing.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

from __future__ import annotations

import unittest

import _fixture

_fixture.bootstrap()

import urls  # noqa: E402


class UrlHost(unittest.TestCase):
    def test_lowercased_hostname(self):
        self.assertEqual(urls.url_host("https://GitHub.com/x"), "github.com")

    def test_no_host_returns_empty(self):
        self.assertEqual(urls.url_host("not-a-url"), "")

    def test_malformed_url_returns_empty(self):
        # an unterminated IPv6 literal makes urlparse raise ValueError; the
        # function must swallow it and return "".
        self.assertEqual(urls.url_host("http://[::1"), "")


class HostMatches(unittest.TestCase):
    def test_exact_and_subdomain(self):
        self.assertTrue(urls.host_matches("https://github.com/a", "github.com"))
        self.assertTrue(urls.host_matches("https://api.github.com/a", "github.com"))

    def test_substring_spoof_rejected(self):
        self.assertFalse(urls.host_matches("https://github.com.evil.com/", "github.com"))
        self.assertFalse(urls.host_matches("https://evil.com/github.com", "github.com"))


if __name__ == "__main__":
    unittest.main()
