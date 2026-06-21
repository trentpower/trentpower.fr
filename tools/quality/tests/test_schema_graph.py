#!/usr/bin/env python3
"""Tests for the JSON-LD @graph coherence gate
(tools/quality/validate_schema_graph.py).

Cross `evaluate(Repo)` over a fixture repo. Assert on the Result, never on
stdout. ExternalInterface runs the real `main()` against the production repo and
asserts the baseline exit code.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import json
import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_schema_graph as vsg  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent

SITE_BASE = "https://trentpower.fr"
PERSON_ID = f"{SITE_BASE}/#trent-power"
WEBSITE_ID = f"{SITE_BASE}/#website"
GATE_ID = f"{SITE_BASE}/#language-gate"


def _page(jsonld_bodies: list[str]) -> str:
    """wrap one or more raw json-ld block bodies in a minimal html page."""
    head = "".join(
        f'<script type="application/ld+json">{b}</script>' for b in jsonld_bodies
    )
    return f"<!doctype html><html><head>{head}</head><body></body></html>\n"


def _graph_block(*entities: dict) -> str:
    return json.dumps({"@context": "https://schema.org", "@graph": list(entities)})


def _obj_block(obj: dict) -> str:
    obj = {"@context": "https://schema.org", **obj}
    return json.dumps(obj)


# a minimal but coherent language-gate page: WebSite + WebPage(#language-gate),
# WebSite.publisher resolves to the canonical person, no editorial entities.
GATE_PAGE = _page(
    [
        _graph_block(
            {"@type": "WebSite", "@id": WEBSITE_ID, "publisher": {"@id": PERSON_ID}},
            {"@type": "WebPage", "@id": GATE_ID, "isPartOf": {"@id": WEBSITE_ID}},
        )
    ]
)


def _edition_page(lang: str) -> str:
    profile_id = f"{SITE_BASE}/{lang}/#profile-page"
    return _page(
        [
            _graph_block(
                {"@type": "Person", "@id": PERSON_ID, "name": "Trent Power"},
                {"@type": "WebSite", "@id": WEBSITE_ID, "publisher": {"@id": PERSON_ID}},
                {
                    "@type": "ProfilePage",
                    "@id": profile_id,
                    "mainEntity": {"@id": PERSON_ID},
                    "isPartOf": {"@id": WEBSITE_ID},
                },
            )
        ]
    )


# a coherent inner WebPage with a single JSON-LD block referencing the canonical
# website + person.
INNER_PAGE = _page(
    [
        _obj_block(
            {
                "@type": "WebPage",
                "isPartOf": {"@id": WEBSITE_ID},
                "about": {"@id": PERSON_ID},
            }
        )
    ]
)


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vsg.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _seed_coherent(self):
        # a "/" gate, both editions, and one inner page — all coherent.
        _write(self.root, "public/index.html", GATE_PAGE)
        _write(self.root, "public/en-au/index.html", _edition_page("en-au"))
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        _write(self.root, "public/privacy/index.html", INNER_PAGE)

    def test_coherent_tree_green(self):
        self._seed_coherent()
        r = vsg.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertIn("HTML pages", r.summary)

    def test_inner_page_multiple_blocks_fails(self):
        # defect 1: an inner page with more than one inline JSON-LD block.
        self._seed_coherent()
        one = _obj_block({"@type": "WebPage", "isPartOf": {"@id": WEBSITE_ID}})
        _write(self.root, "public/verify/index.html", _page([one, one]))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("at most ONE inline JSON-LD block" in f for f in r.fails), r.fails
        )

    def test_malformed_jsonld_fails(self):
        # defect 2: a page whose JSON-LD block does not parse.
        self._seed_coherent()
        broken = (
            "<!doctype html><html><head>"
            '<script type="application/ld+json">{"@type":"WebPage", not valid json}'
            "</script></head><body></body></html>\n"
        )
        _write(self.root, "public/source/index.html", broken)
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("does not parse" in f for f in r.fails), r.fails)

    def test_gate_with_editorial_entity_fails(self):
        # the root gate must not carry a ProfilePage (editorial entity).
        bad_gate = _page(
            [
                _graph_block(
                    {"@type": "WebSite", "@id": WEBSITE_ID, "publisher": {"@id": PERSON_ID}},
                    {"@type": "WebPage", "@id": GATE_ID, "isPartOf": {"@id": WEBSITE_ID}},
                    {"@type": "ProfilePage", "@id": f"{SITE_BASE}/#profile-page"},
                )
            ]
        )
        _write(self.root, "public/index.html", bad_gate)
        _write(self.root, "public/en-au/index.html", _edition_page("en-au"))
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("editorial entities belong" in f for f in r.fails), r.fails
        )

    def test_edition_missing_required_entity_fails(self):
        # an edition @graph missing the Person entity is a defect.
        _write(self.root, "public/index.html", GATE_PAGE)
        no_person = _page(
            [
                _graph_block(
                    {"@type": "WebSite", "@id": WEBSITE_ID, "publisher": {"@id": PERSON_ID}},
                    {
                        "@type": "ProfilePage",
                        "@id": f"{SITE_BASE}/en-au/#profile-page",
                        "mainEntity": {"@id": PERSON_ID},
                        "isPartOf": {"@id": WEBSITE_ID},
                    },
                )
            ]
        )
        _write(self.root, "public/en-au/index.html", no_person)
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any(f"missing entity with @id {PERSON_ID}" in f for f in r.fails), r.fails
        )

    def test_frozen_release_pages_excluded(self):
        # frozen archive snapshots are not scanned, even if malformed.
        self._seed_coherent()
        _write(
            self.root,
            "public/integrity/releases/2026-02/index.html",
            '<!doctype html><script type="application/ld+json">{bad json}</script>',
        )
        r = vsg.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vsg.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
