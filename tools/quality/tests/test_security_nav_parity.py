#!/usr/bin/env python3
"""Tests for the security-page nav/body parity gate
(tools/quality/validate_security_nav_parity.py).

Cross `evaluate(Repo)` over fixture repos holding the two rendered security
pages. Assert on the Result — no monkeypatching, no real build.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_security_nav_parity as vs  # noqa: E402
from _fixture import write as _write  # noqa: E402

EN = "public/en-au/security/index.html"
FR = "public/fr/securite/index.html"


def _page(nav_ids, body_ids):
    nav = "".join(f'<li><a href="#{i}">label</a></li>' for i in nav_ids)
    body = "".join(
        f'<section class="security-section">'
        f'<h2 class="security-section-heading" id="{i}">label</h2></section>'
        for i in body_ids
    )
    return f'<nav class="security-contents"><ol class="security-contents-list">{nav}</ol></nav>{body}'


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _seed(self, en_nav, en_body, fr_nav, fr_body):
        _write(self.root, EN, _page(en_nav, en_body))
        _write(self.root, FR, _page(fr_nav, fr_body))

    def test_matched_nav_and_body_is_ok(self):
        ids = [f"security-s{i}-heading" for i in range(1, 11)]  # 10 each
        self._seed(ids, ids, ids, ids)
        self.assertTrue(vs.evaluate(vs.Repo(self.root)).ok)

    def test_missing_nav_entry_fails(self):
        body = [f"security-s{i}-heading" for i in range(1, 11)]  # 10 body
        nav = body[:-1]  # nav promises only 9 — the #57 defect
        self._seed(nav, body, nav, body)
        r = vs.evaluate(vs.Repo(self.root))
        self.assertFalse(r.ok)
        self.assertTrue(any("no entry in the contents nav" in e for e in r.errors))

    def test_dead_nav_link_fails(self):
        body = ["security-a-heading", "security-b-heading"]
        nav = ["security-a-heading", "security-ghost-heading"]  # links to nothing
        self._seed(nav, body, nav, body)
        r = vs.evaluate(vs.Repo(self.root))
        self.assertFalse(r.ok)
        self.assertTrue(any("no such body section" in e for e in r.errors))

    def test_duplicate_body_id_fails(self):
        ids = ["security-a-heading", "security-a-heading"]
        self._seed(ids, ids, ids, ids)
        r = vs.evaluate(vs.Repo(self.root))
        self.assertFalse(r.ok)
        self.assertTrue(any("not unique" in e for e in r.errors))

    def test_missing_nav_list_fails(self):
        _write(self.root, EN, "<p>no contents list here</p>")
        _write(self.root, FR, _page(["security-a-heading"], ["security-a-heading"]))
        r = vs.evaluate(vs.Repo(self.root))
        self.assertFalse(r.ok)
        self.assertTrue(any("no .security-contents-list nav" in e for e in r.errors))

    def test_bilingual_count_mismatch_fails(self):
        en = [f"security-s{i}-heading" for i in range(1, 4)]  # 3
        fr = [f"security-s{i}-heading" for i in range(1, 3)]  # 2
        self._seed(en, en, fr, fr)
        r = vs.evaluate(vs.Repo(self.root))
        self.assertFalse(r.ok)
        self.assertTrue(any("bilingual section-count mismatch" in e for e in r.errors))

    def test_missing_file_reported(self):
        _write(self.root, EN, _page(["security-a-heading"], ["security-a-heading"]))
        # FR absent
        r = vs.evaluate(vs.Repo(self.root))
        self.assertFalse(r.ok)
        self.assertTrue(any("missing file" in e for e in r.errors))


class PureHelpers(unittest.TestCase):
    def test_nav_targets_extracts_fragments(self):
        html = _page(["security-x-heading", "security-y-heading"], [])
        self.assertEqual(
            vs.nav_targets(html), ["security-x-heading", "security-y-heading"]
        )

    def test_nav_targets_none_when_absent(self):
        self.assertIsNone(vs.nav_targets("<p>nothing</p>"))

    def test_section_heading_ids_attr_order_independent(self):
        html = '<h2 id="security-z-heading" class="security-section-heading">z</h2>'
        self.assertEqual(vs.section_heading_ids(html), ["security-z-heading"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
