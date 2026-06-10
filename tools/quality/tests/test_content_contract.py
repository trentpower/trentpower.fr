#!/usr/bin/env python3
"""Tests for the content contract: page schemas,
generate_routes_json drift gate, and validate_content_schemas. Stdlib
unittest -- no pytest dep.

Run:
    python3 -m unittest discover -s tools/tests
"""

import contextlib
import io
import json
import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
for _sub in ("lib", "build", "quality"):
    sys.path.insert(0, str(TOOLS / _sub))

import generate_routes_json as grj  # noqa: E402
import validate_content_schemas as vcs  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402

SCHEMA_DIR = TOOLS.parent / "schemas" / "content"


class Schemas(unittest.TestCase):
    def test_all_schemas_are_valid_jsonschema(self):
        files = list(SCHEMA_DIR.glob("*.schema.json"))
        self.assertTrue(files, "expected schema files under schemas/content/")
        for sf in files:
            schema = json.loads(sf.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)  # raises if malformed

    def test_good_home_instance_passes_and_bad_fails(self):
        registry = vcs._registry()
        home_schema = json.loads((SCHEMA_DIR / "home.schema.json").read_text())
        v = Draft202012Validator(home_schema, registry=registry)

        good = {"meta": {"home": {"title": "T", "description": "D"}}, "hero": {}}
        self.assertEqual(list(v.iter_errors(good)), [])

        # missing description in the required meta.home SEO entry -> rejected
        bad = {"meta": {"home": {"title": "T"}}, "hero": {}}
        self.assertTrue(list(v.iter_errors(bad)))

        # missing the required meta.home key entirely -> rejected
        bad2 = {"meta": {"other": {"title": "T", "description": "D"}}}
        self.assertTrue(list(v.iter_errors(bad2)))

        # unknown field inside a meta SEO entry -> rejected (additionalProperties false)
        bad3 = {"meta": {"home": {"title": "T", "description": "D", "bogus": 1}}}
        self.assertTrue(list(v.iter_errors(bad3)))


class RoutesJsonDrift(unittest.TestCase):
    def test_committed_routes_json_in_sync(self):
        with contextlib.redirect_stdout(io.StringIO()):
            rc = grj.main(["--check"])
        self.assertEqual(rc, 0, "content/routes.json drifted from routes.yml")

    def test_build_is_deterministic(self):
        self.assertEqual(grj._serialize(grj.build()), grj._serialize(grj.build()))

    def test_every_route_has_both_languages(self):
        data = grj.build()
        # 10 bilingual routes x 2 languages
        self.assertEqual(len(data["routes"]), 20)
        self.assertEqual(set(data["languages"]), {"en-AU", "fr"})


class ContentValidator(unittest.TestCase):
    def test_real_content_passes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            rc = vcs.main([])
        self.assertEqual(rc, 0, "current content failed the schema contract")

    def test_parity_ignores_translation_key(self):
        en = {"meta", "hero", "translation"}
        fr = {"meta", "hero"}
        self.assertEqual(en - vcs.PARITY_IGNORE_KEYS, fr - vcs.PARITY_IGNORE_KEYS)


if __name__ == "__main__":
    unittest.main()
