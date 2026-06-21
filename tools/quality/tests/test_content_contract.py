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
import tempfile
import unittest
from unittest import mock

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


@contextlib.contextmanager
def seeded_repo():
    """Yield a SeededRepo whose layout the validator reads via patched globals.

    the validator functions read module-level paths (SCHEMA_DIR, ROUTES_JSON,
    PAGES_DIRS, TEMPLATE_PAGES, REPO_ROOT). we point them all at a throwaway
    tree so each test can plant exactly one defect and assert the real failure.
    """
    with tempfile.TemporaryDirectory() as td:
        yield SeededRepo(pathlib.Path(td))


class SeededRepo:
    """A throwaway repo tree the validator can be pointed at."""

    def __init__(self, root):
        self.root = root
        self.schema_dir = root / "schemas" / "content"
        self.en_pages = root / "content" / "en" / "pages"
        self.fr_pages = root / "content" / "fr" / "pages"
        self.template_pages = root / "templates" / "pages"
        self.routes_json = root / "content" / "routes.json"
        for d in (self.schema_dir, self.en_pages, self.fr_pages, self.template_pages):
            d.mkdir(parents=True, exist_ok=True)

    def patch(self):
        # rebind every module global the validator reads to this tree.
        return mock.patch.multiple(
            vcs,
            REPO_ROOT=self.root,
            SCHEMA_DIR=self.schema_dir,
            ROUTES_JSON=self.routes_json,
            PAGES_DIRS={"en": self.en_pages, "fr": self.fr_pages},
            TEMPLATE_PAGES=self.template_pages,
        )

    def write_schema(self, stem, schema=None):
        schema = schema or {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://example/{stem}.schema.json",
            "type": "object",
            "required": ["title"],
            "additionalProperties": True,
        }
        (self.schema_dir / f"{stem}.schema.json").write_text(json.dumps(schema), encoding="utf-8")

    def write_page(self, lang, stem, body):
        d = self.en_pages if lang == "en" else self.fr_pages
        (d / f"{stem}.yml").write_text(body, encoding="utf-8")

    def write_template(self, name):
        (self.template_pages / f"{name}.html").write_text("<html></html>", encoding="utf-8")

    def write_routes(self, routes):
        self.routes_json.write_text(json.dumps({"routes": routes}), encoding="utf-8")


class ContentBranches(unittest.TestCase):
    def test_missing_pages_dir_is_skipped(self):
        # en dir removed -> _validate_content's `is_dir()` guard continues (line 92).
        with seeded_repo() as repo:
            repo.en_pages.rmdir()
            repo.write_schema("home")
            repo.write_page("fr", "home", "title: T\n")
            with repo.patch():
                results = vcs._validate_content(vcs._registry())
        # only the fr page is evaluated; en is skipped silently.
        ids = [r["id"] for r in results]
        self.assertEqual(ids, ["content:fr/home"])
        self.assertEqual(results[0]["status"], "passed")

    def test_page_without_schema_fails(self):
        # a yml with no matching schema -> "has no schema" failed entry (lines 98-107).
        with seeded_repo() as repo:
            repo.write_page("en", "orphan", "title: T\n")
            with repo.patch():
                results = vcs._validate_content(vcs._registry())
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r["id"], "schema:en/orphan")
        self.assertEqual(r["status"], "failed")
        self.assertIn("has no schema", r["label"])

    def test_content_schema_violation_reports_detail(self):
        # required key absent -> validator errors -> failed with detail (lines 113-117).
        with seeded_repo() as repo:
            repo.write_schema("home")
            repo.write_page("en", "home", "description: only\n")  # missing required `title`
            with repo.patch():
                results = vcs._validate_content(vcs._registry())
        r = next(r for r in results if r["id"] == "content:en/home")
        self.assertEqual(r["status"], "failed")
        self.assertIn("violates", r["label"])
        self.assertIn("title", r["stdout"])


class ReferenceBranches(unittest.TestCase):
    def test_missing_routes_json_fails(self):
        # routes.json absent -> single failed entry (line 143).
        with seeded_repo() as repo:
            repo.routes_json.unlink(missing_ok=True)
            with repo.patch():
                results = vcs._validate_references()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "routes_json")
        self.assertEqual(results[0]["status"], "failed")

    def test_unresolved_content_schema_template_all_reported(self):
        # all three refs dangle -> missing list carries content, schema, template
        # (lines 157, 160, 162).
        with seeded_repo() as repo:
            repo.write_routes(
                [
                    {
                        "id": "ghost",
                        "content": "content/en/pages/ghost.yml",
                        "schema": "schemas/content/ghost.schema.json",
                        "template": "ghost",
                    }
                ]
            )
            with repo.patch():
                results = vcs._validate_references()
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r["id"], "ref:ghost")
        self.assertEqual(r["status"], "failed")
        self.assertIn("content=content/en/pages/ghost.yml", r["stdout"])
        self.assertIn("schema=schemas/content/ghost.schema.json", r["stdout"])
        self.assertIn("template=", r["stdout"])

    def test_failed_refs_suppress_all_resolve_entry(self):
        # when a ref fails, the trailing "all resolve" passed entry is NOT added
        # (branch 172->181 stays on the failure path).
        with seeded_repo() as repo:
            repo.write_routes(
                [
                    {
                        "id": "ghost",
                        "content": "missing.yml",
                        "schema": "missing.schema.json",
                        "template": "missing",
                    }
                ]
            )
            with repo.patch():
                results = vcs._validate_references()
        self.assertTrue(all(r["status"] == "failed" for r in results))
        self.assertNotIn("refs", [r["id"] for r in results])

    def test_all_refs_resolve_passes(self):
        # every ref resolves -> single passed "all resolve" entry (line 172->173).
        with seeded_repo() as repo:
            repo.write_schema("home")
            repo.write_page("en", "home", "title: T\n")
            repo.write_template("page")
            repo.write_routes(
                [
                    {
                        "id": "home",
                        "content": "content/en/pages/home.yml",
                        "schema": "schemas/content/home.schema.json",
                        "template": "page",
                    }
                ]
            )
            with repo.patch():
                results = vcs._validate_references()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "refs")
        self.assertEqual(results[0]["status"], "passed")


class ParityBranches(unittest.TestCase):
    def test_key_parity_drift_reported_both_directions(self):
        # en has a key fr lacks AND fr has a key en lacks -> both diff lines (198-203).
        with seeded_repo() as repo:
            repo.write_page("en", "home", "meta: {}\nhero: {}\nonly_en: {}\n")
            repo.write_page("fr", "home", "meta: {}\nhero: {}\nonly_fr: {}\n")
            with repo.patch():
                results = vcs._validate_parity()
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r["id"], "parity:home")
        self.assertEqual(r["tier"], "advisory")
        self.assertIn("missing in fr: ['only_en']", r["stdout"])
        self.assertIn("missing in en: ['only_fr']", r["stdout"])


class MainFailRender(unittest.TestCase):
    def test_main_fails_and_prints_blocking_and_advisory(self):
        # drive main() over a tree with one blocking violation (orphan page, no
        # schema) and one advisory parity drift -> rc 1, both lines printed,
        # plus the --json report branch (lines 230-245, 238-240).
        with seeded_repo() as repo:
            # blocking: en page with no schema.
            repo.write_page("en", "orphan", "title: T\n")
            # advisory: matching en/fr pages with divergent keys.
            repo.write_schema("home")
            repo.write_page("en", "home", "title: T\nextra: {}\n")
            repo.write_page("fr", "home", "title: T\n")
            report_path = repo.root / "report.json"
            out, err = io.StringIO(), io.StringIO()
            with repo.patch(), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = vcs.main(["--json", str(report_path)])
            # assert inside the with-block: the temp tree is torn down on exit.
            report_written = report_path.exists()
        self.assertEqual(rc, 1)
        text = out.getvalue()
        self.assertIn("X FAIL", text)
        self.assertIn("schema:en/orphan", text)
        self.assertIn("! WARN", text)
        self.assertIn("parity:home", text)
        self.assertIn("FAIL: content contract broken", text)
        self.assertIn("report:", text)
        self.assertTrue(report_written)


if __name__ == "__main__":
    unittest.main()
