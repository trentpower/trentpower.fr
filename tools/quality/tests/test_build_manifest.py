#!/usr/bin/env python3
"""Tests for the C2PA manifest builder (tools/c2pa/build_manifest.py).

Pure: build_manifest(asset, policy, identity) is exercised with inline dicts (no
c2pa, no signing material), and manifest_for_path is run over the real committed
policy + identity files (reading, not signing). Stdlib unittest.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import unittest

import _fixture  # noqa: E402

_fixture.bootstrap("c2pa")

import build_manifest as bm  # noqa: E402


def _identity(**over):
    base = {"edition": "2026-06-14", "person": {"name": "Trent Power", "orcid": "0009-0002-2652-7188"}}
    base.update(over)
    return base


def _policy():
    return {"publisher": {"name": "trentpower.fr", "url": "https://trentpower.fr"}, "assets": []}


def _asset(**over):
    base = {
        "path": "public/images/architecture/architecture.en.svg",
        "canonical_url": "https://trentpower.fr/images/architecture/architecture.en.svg",
        "ai_involvement": "no-ai-in-release-path",
    }
    base.update(over)
    return base


class BuildManifest(unittest.TestCase):
    def test_three_assertions_in_order(self):
        m = bm.build_manifest(_asset(), _policy(), _identity())
        labels = [a["label"] for a in m["assertions"]]
        self.assertEqual(
            labels,
            ["stds.schema-org.CreativeWork", "com.trentpower.ai-involvement", "com.trentpower.integrity"],
        )

    def test_title_is_basename(self):
        self.assertEqual(bm.build_manifest(_asset(), _policy(), _identity())["title"], "architecture.en.svg")

    def test_author_publisher_url(self):
        cw = bm.build_manifest(_asset(), _policy(), _identity())["assertions"][0]["data"]
        self.assertEqual(cw["author"][0]["name"], "Trent Power")
        self.assertEqual(cw["publisher"]["name"], "trentpower.fr")
        self.assertEqual(cw["url"], "https://trentpower.fr/images/architecture/architecture.en.svg")

    def test_orcid_threaded_when_present(self):
        cw = bm.build_manifest(_asset(), _policy(), _identity())["assertions"][0]["data"]
        self.assertEqual(cw["author"][0]["identifier"], "https://orcid.org/0009-0002-2652-7188")

    def test_no_orcid_no_identifier(self):
        cw = bm.build_manifest(_asset(), _policy(), _identity(person={"name": "Trent Power"}))["assertions"][0]["data"]
        self.assertNotIn("identifier", cw["author"][0])

    def test_ai_meaning_resolved_for_known_value(self):
        ai = bm.build_manifest(_asset(), _policy(), _identity())["assertions"][1]["data"]
        self.assertEqual(ai["value"], "no-ai-in-release-path")
        self.assertIn("no AI system participates", ai["meaning"])

    def test_integrity_assertion_strips_public_prefix(self):
        integ = bm.build_manifest(_asset(), _policy(), _identity())["assertions"][2]["data"]
        self.assertEqual(integ["path"], "images/architecture/architecture.en.svg")
        self.assertEqual(integ["manifest"], bm.INTEGRITY_URL)

    def test_asset_author_overrides_identity(self):
        cw = bm.build_manifest(_asset(author="Someone Else"), _policy(), _identity())["assertions"][0]["data"]
        self.assertEqual(cw["author"][0]["name"], "Someone Else")


class FindAsset(unittest.TestCase):
    def test_found(self):
        pol = {"assets": [{"path": "public/a.svg"}, {"path": "public/b.svg"}]}
        self.assertEqual(bm.find_asset(pol, "public/b.svg")["path"], "public/b.svg")

    def test_missing_returns_none(self):
        self.assertIsNone(bm.find_asset({"assets": []}, "public/x.svg"))


class ManifestForPath(unittest.TestCase):
    """Cross the real committed policy + identity files (read-only)."""

    def test_real_declared_svg(self):
        m = bm.manifest_for_path("public/images/architecture/architecture.en.svg")
        self.assertEqual(m["title"], "architecture.en.svg")
        self.assertEqual(m["assertions"][0]["data"]["author"][0]["name"], "Trent Power")

    def test_undeclared_path_raises(self):
        with self.assertRaises(SystemExit):
            bm.manifest_for_path("public/not/declared.svg")

    def test_excluded_asset_without_canonical_raises(self):
        # README.pdf is declared but excluded (no canonical_url) -> clear failure.
        with self.assertRaises(SystemExit):
            bm.manifest_for_path("public/documentation/README.pdf")


if __name__ == "__main__":
    unittest.main()
