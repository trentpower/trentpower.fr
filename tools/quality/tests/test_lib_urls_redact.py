#!/usr/bin/env python3
"""Tests for tools/lib/urls.py and tools/lib/redact.py."""

import unittest

import _fixture  # noqa: E402

_fixture.bootstrap("release")

from redact import mask_secret  # noqa: E402
from urls import host_matches, url_host  # noqa: E402


class HostMatches(unittest.TestCase):
    def test_exact_and_subdomain(self):
        self.assertTrue(host_matches("https://linkedin.com/in/x", "linkedin.com"))
        self.assertTrue(host_matches("https://www.linkedin.com/in/x", "linkedin.com"))
        self.assertTrue(host_matches("https://commons.wikimedia.org/wiki/F", "wikimedia.org"))

    def test_rejects_substring_lookalikes(self):
        # the exact shapes the old `"x" in url` checks wrongly accepted.
        self.assertFalse(host_matches("https://linkedin.com.evil.com/", "linkedin.com"))
        self.assertFalse(host_matches("https://evil.com/linkedin.com", "linkedin.com"))
        self.assertFalse(host_matches("https://notlinkedin.com/", "linkedin.com"))

    def test_case_and_garbage(self):
        self.assertTrue(host_matches("https://GitHub.com/trentpower", "github.com"))
        self.assertFalse(host_matches("not a url", "github.com"))
        self.assertEqual(url_host("not a url"), "")


class MaskSecret(unittest.TestCase):
    # fake values are assembled at runtime so the repo's own secret
    # scanners never see a pattern-shaped literal in this source file.
    def test_never_contains_any_of_value(self):
        value = "ghp" + "_" + "abcdefghijklmnopqrstuvwxyz0123456789"
        masked = mask_secret(value)
        self.assertNotIn(value, masked)
        # no prefix of the value either — only length + fingerprint.
        self.assertFalse(masked.startswith(value[:3]))

    def test_stable_fingerprint(self):
        value = "AKIA" + "IOSFODNN7" + "EXAMPLE"
        self.assertEqual(mask_secret(value), mask_secret(value))

    def test_shape_is_metadata_only(self):
        masked = mask_secret("tok" + "_" + "secretvalue")
        self.assertIn("chars, sha256:", masked)
        self.assertTrue(masked.startswith("["))


if __name__ == "__main__":
    unittest.main()
