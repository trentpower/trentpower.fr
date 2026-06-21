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
    head = "".join(f'<script type="application/ld+json">{b}</script>' for b in jsonld_bodies)
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
        self.assertTrue(any("at most ONE inline JSON-LD block" in f for f in r.fails), r.fails)

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
        self.assertTrue(any("editorial entities belong" in f for f in r.fails), r.fails)

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
        self.assertTrue(any(f"missing entity with @id {PERSON_ID}" in f for f in r.fails), r.fails)

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

    def test_edition_no_page_level_block(self):
        # an edition page carrying only a FAQPage block has no @graph block.
        _write(self.root, "public/index.html", GATE_PAGE)
        faq_only = _page([_obj_block({"@type": "FAQPage"})])
        _write(self.root, "public/en-au/index.html", faq_only)
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("no @graph / page-level JSON-LD found" in f for f in r.fails), r.fails)

    def test_edition_two_non_faq_blocks_fails(self):
        # an edition with two separate non-FAQ page blocks violates the
        # one-consolidated-@graph rule.
        _write(self.root, "public/index.html", GATE_PAGE)
        blk = _graph_block(
            {"@type": "Person", "@id": PERSON_ID, "name": "Trent Power"},
            {"@type": "WebSite", "@id": WEBSITE_ID, "publisher": {"@id": PERSON_ID}},
            {
                "@type": "ProfilePage",
                "@id": f"{SITE_BASE}/en-au/#profile-page",
                "mainEntity": {"@id": PERSON_ID},
                "isPartOf": {"@id": WEBSITE_ID},
            },
        )
        _write(self.root, "public/en-au/index.html", _page([blk, blk]))
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("expected ONE consolidated @graph block" in f for f in r.fails),
            r.fails,
        )

    def test_edition_malformed_block_fails(self):
        # an edition whose first json-ld block does not parse.
        _write(self.root, "public/index.html", GATE_PAGE)
        broken = (
            "<!doctype html><html><head>"
            '<script type="application/ld+json">{"@graph": [ , ]}</script>'
            "</head><body></body></html>\n"
        )
        _write(self.root, "public/en-au/index.html", broken)
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("does not parse" in f for f in r.fails), r.fails)

    def test_edition_missing_graph_array_fails(self):
        # an edition top-level block that is not an @graph array.
        _write(self.root, "public/index.html", GATE_PAGE)
        no_graph = _page([_obj_block({"@type": "ProfilePage", "@id": PERSON_ID})])
        _write(self.root, "public/en-au/index.html", no_graph)
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("missing `@graph` array" in f for f in r.fails), r.fails)

    def test_edition_profilepage_wrong_mainentity_and_ispartof(self):
        # ProfilePage with mainEntity / isPartOf pointing at the wrong ids.
        _write(self.root, "public/index.html", GATE_PAGE)
        bad = _page(
            [
                _graph_block(
                    {"@type": "Person", "@id": PERSON_ID, "name": "Trent Power"},
                    {"@type": "WebSite", "@id": WEBSITE_ID, "publisher": {"@id": PERSON_ID}},
                    {
                        "@type": "ProfilePage",
                        "@id": f"{SITE_BASE}/en-au/#profile-page",
                        "mainEntity": {"@id": "https://wrong/#x"},
                        "isPartOf": {"@id": "https://wrong/#y"},
                    },
                )
            ]
        )
        _write(self.root, "public/en-au/index.html", bad)
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("ProfilePage: mainEntity.@id should be" in f for f in r.fails), r.fails)
        self.assertTrue(any("ProfilePage: isPartOf.@id should be" in f for f in r.fails), r.fails)

    def test_edition_website_wrong_publisher(self):
        # WebSite.publisher pointing at the wrong id on an edition page.
        _write(self.root, "public/index.html", GATE_PAGE)
        bad = _page(
            [
                _graph_block(
                    {"@type": "Person", "@id": PERSON_ID, "name": "Trent Power"},
                    {
                        "@type": "WebSite",
                        "@id": WEBSITE_ID,
                        "publisher": {"@id": "https://wrong/#nope"},
                    },
                    {
                        "@type": "ProfilePage",
                        "@id": f"{SITE_BASE}/en-au/#profile-page",
                        "mainEntity": {"@id": PERSON_ID},
                        "isPartOf": {"@id": WEBSITE_ID},
                    },
                )
            ]
        )
        _write(self.root, "public/en-au/index.html", bad)
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("WebSite: publisher.@id should be" in f for f in r.fails), r.fails)

    def test_edition_duplicate_entity_type(self):
        # two Person entities in the same @graph is a duplicate-definition defect.
        _write(self.root, "public/index.html", GATE_PAGE)
        dup = _page(
            [
                _graph_block(
                    {"@type": "Person", "@id": PERSON_ID, "name": "Trent Power"},
                    {"@type": "Person", "@id": f"{PERSON_ID}-2", "name": "Doppel"},
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
        _write(self.root, "public/en-au/index.html", dup)
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("Person defined 2 times" in f for f in r.fails), r.fails)

    def test_inner_webpage_wrong_ispartof_and_about(self):
        # an inner WebPage referencing the wrong website + person ids.
        self._seed_coherent()
        bad = _page(
            [
                _obj_block(
                    {
                        "@type": "WebPage",
                        "isPartOf": {"@id": "https://wrong/#site"},
                        "about": {"@id": "https://wrong/#person"},
                    }
                )
            ]
        )
        _write(self.root, "public/verify/index.html", bad)
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("WebPage: isPartOf.@id should reference" in f for f in r.fails), r.fails
        )
        self.assertTrue(
            any("WebPage: about/author.@id should reference" in f for f in r.fails),
            r.fails,
        )

    def test_inner_techarticle_defects(self):
        # a TechArticle missing publisher/headline/dates trips the techarticle
        # branch fully.
        self._seed_coherent()
        bad = _page(
            [
                _obj_block(
                    {
                        "@type": "TechArticle",
                        "isPartOf": {"@id": WEBSITE_ID},
                        "author": {"@id": PERSON_ID},
                        "publisher": {"@id": "https://wrong/#pub"},
                    }
                )
            ]
        )
        _write(self.root, "public/integrity/index.html", bad)
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("TechArticle: publisher.@id should reference" in f for f in r.fails),
            r.fails,
        )
        self.assertTrue(any("TechArticle: missing headline" in f for f in r.fails), r.fails)
        self.assertTrue(any("missing datePublished/dateModified" in f for f in r.fails), r.fails)

    def test_inner_malformed_block_fails(self):
        # an inner page whose single block does not parse (continue path).
        self._seed_coherent()
        broken = (
            "<!doctype html><html><head>"
            '<script type="application/ld+json">{nope}</script>'
            "</head><body></body></html>\n"
        )
        _write(self.root, "public/sw-reset/index.html", broken)
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("does not parse" in f for f in r.fails), r.fails)

    def test_gate_no_jsonld_fails(self):
        # a "/" gate with no json-ld at all.
        _write(self.root, "public/index.html", "<!doctype html><html></html>\n")
        _write(self.root, "public/en-au/index.html", _edition_page("en-au"))
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("no JSON-LD found" in f for f in r.fails), r.fails)

    def test_gate_malformed_block_fails(self):
        # a "/" gate whose block does not parse.
        broken = (
            "<!doctype html><html><head>"
            '<script type="application/ld+json">{,}</script>'
            "</head></html>\n"
        )
        _write(self.root, "public/index.html", broken)
        _write(self.root, "public/en-au/index.html", _edition_page("en-au"))
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("does not parse" in f for f in r.fails), r.fails)

    def test_gate_only_faq_block_fails(self):
        # a "/" gate carrying only a FAQPage block has no page-level @graph.
        _write(self.root, "public/index.html", _page([_obj_block({"@type": "FAQPage"})]))
        _write(self.root, "public/en-au/index.html", _edition_page("en-au"))
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("no @graph / page-level JSON-LD found" in f for f in r.fails), r.fails)

    def test_gate_missing_graph_array_fails(self):
        # a "/" gate top-level block that is not an @graph array.
        _write(self.root, "public/index.html", _page([_obj_block({"@type": "WebSite"})]))
        _write(self.root, "public/en-au/index.html", _edition_page("en-au"))
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("missing `@graph` array" in f for f in r.fails), r.fails)

    def test_gate_missing_website_and_gate_entities(self):
        # a "/" gate @graph missing both the WebSite and the language-gate page.
        _write(self.root, "public/index.html", _page([_graph_block({"@type": "Thing"})]))
        _write(self.root, "public/en-au/index.html", _edition_page("en-au"))
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any(f"missing WebSite with @id {WEBSITE_ID}" in f for f in r.fails), r.fails
        )
        self.assertTrue(any(f"missing WebPage with @id {GATE_ID}" in f for f in r.fails), r.fails)

    def test_gate_languagegate_wrong_ispartof(self):
        # gate WebPage isPartOf points at the wrong website id.
        bad = _page(
            [
                _graph_block(
                    {"@type": "WebSite", "@id": WEBSITE_ID, "publisher": {"@id": PERSON_ID}},
                    {"@type": "WebPage", "@id": GATE_ID, "isPartOf": {"@id": "https://wrong"}},
                )
            ]
        )
        _write(self.root, "public/index.html", bad)
        _write(self.root, "public/en-au/index.html", _edition_page("en-au"))
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("WebPage(language-gate): isPartOf.@id should be" in f for f in r.fails),
            r.fails,
        )

    def test_gate_website_wrong_publisher(self):
        # gate WebSite.publisher points at the wrong person id.
        bad = _page(
            [
                _graph_block(
                    {
                        "@type": "WebSite",
                        "@id": WEBSITE_ID,
                        "publisher": {"@id": "https://wrong/#nope"},
                    },
                    {"@type": "WebPage", "@id": GATE_ID, "isPartOf": {"@id": WEBSITE_ID}},
                )
            ]
        )
        _write(self.root, "public/index.html", bad)
        _write(self.root, "public/en-au/index.html", _edition_page("en-au"))
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("WebSite: publisher.@id should be" in f for f in r.fails), r.fails)

    def test_inner_block_other_type_is_tolerated(self):
        # an inner page whose single block is neither WebPage nor TechArticle
        # (e.g. BreadcrumbList) is not flagged — the relationship checks skip it.
        self._seed_coherent()
        ok_other = _page([_obj_block({"@type": "BreadcrumbList"})])
        _write(self.root, "public/colophon/index.html", ok_other)
        r = vsg.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_gate_graph_with_non_dict_entry_tolerated(self):
        # a stray non-dict entry in the gate @graph is skipped, not crashed on.
        with_noise = _page(
            [
                _graph_block(
                    {"@type": "WebSite", "@id": WEBSITE_ID, "publisher": {"@id": PERSON_ID}},
                    {"@type": "WebPage", "@id": GATE_ID, "isPartOf": {"@id": WEBSITE_ID}},
                    "a-bare-string-entry",
                )
            ]
        )
        _write(self.root, "public/index.html", with_noise)
        _write(self.root, "public/en-au/index.html", _edition_page("en-au"))
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_gate_person_with_nonstub_keys(self):
        # a full Person (sameAs/jobTitle) on the gate is forbidden — only the
        # name+url stub is allowed.
        bad = _page(
            [
                _graph_block(
                    {"@type": "WebSite", "@id": WEBSITE_ID, "publisher": {"@id": PERSON_ID}},
                    {"@type": "WebPage", "@id": GATE_ID, "isPartOf": {"@id": WEBSITE_ID}},
                    {
                        "@type": "Person",
                        "@id": PERSON_ID,
                        "name": "Trent Power",
                        "url": SITE_BASE,
                        "jobTitle": "Builder",
                        "sameAs": ["https://example.test"],
                    },
                )
            ]
        )
        _write(self.root, "public/index.html", bad)
        _write(self.root, "public/en-au/index.html", _edition_page("en-au"))
        _write(self.root, "public/fr/index.html", _edition_page("fr"))
        r = vsg.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("carries" in f and "non-stub keys" in f for f in r.fails), r.fails)


class EntityIdsHelper(unittest.TestCase):
    def test_collects_nested_ids(self):
        # _entity_ids_in walks dicts and lists, gathering every @id string.
        graph = [
            {"@id": "a", "child": {"@id": "b"}},
            {"@id": "c", "list": [{"@id": "d"}, "noise", 7]},
        ]
        self.assertEqual(vsg._entity_ids_in(graph), {"a", "b", "c", "d"})

    def test_ignores_non_string_id(self):
        # a non-string @id is not collected.
        self.assertEqual(vsg._entity_ids_in({"@id": 123}), set())


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vsg.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_main_fails_over_a_broken_fixture(self):
        # the fail-render branch: main() over a repo whose "/" gate has no
        # json-ld returns 1 and prints the failure summary + a bullet to stderr.
        import contextlib
        import io

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        _write(root, "public/index.html", "<!doctype html><html></html>\n")
        _write(root, "public/en-au/index.html", _edition_page("en-au"))
        _write(root, "public/fr/index.html", _edition_page("fr"))

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = vsg.main(root)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL:", err.getvalue())
        self.assertIn("schema-graph issue(s)", err.getvalue())
        self.assertIn("✗", err.getvalue())

    def test_main_truncates_long_failure_list(self):
        # more than 30 failures triggers the "… and N more" truncation line.
        import contextlib
        import io

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        _write(root, "public/index.html", GATE_PAGE)
        _write(root, "public/en-au/index.html", _edition_page("en-au"))
        _write(root, "public/fr/index.html", _edition_page("fr"))
        # seed 40 inner pages each carrying two json-ld blocks (one fail apiece).
        two = _page(
            [
                _obj_block({"@type": "WebPage", "isPartOf": {"@id": WEBSITE_ID}}),
                _obj_block({"@type": "WebPage", "isPartOf": {"@id": WEBSITE_ID}}),
            ]
        )
        for i in range(40):
            _write(root, f"public/p{i}/index.html", two)

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = vsg.main(root)
        self.assertEqual(rc, 1)
        self.assertIn("more", err.getvalue())


if __name__ == "__main__":
    unittest.main()
