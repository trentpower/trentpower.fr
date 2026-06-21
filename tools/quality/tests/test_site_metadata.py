#!/usr/bin/env python3
"""Tests for the site-metadata schema gate (tools/quality/validate_site_metadata.py).

Cross the module's interface — `evaluate(Repo, data)` and `load(Repo)` — over a
tiny fixture repo. No monkeypatching: the fixture repo is the second filesystem
adapter, so the whole compute path runs without touching globals. Tests assert on
the returned Result, never on stdout, so they survive internal refactors.

Stdlib unittest — no pytest dep.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import contextlib
import io
import json
import pathlib
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_site_metadata as vsm  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent


def _valid_metadata() -> dict:
    """A coherent site-metadata document that satisfies every rule."""
    return {
        "type": "PersonalSiteMetadata",
        "schema_version": "1.0",
        "name": "Trent Power",
        "description": "A personal publication.",
        "url": "https://trentpower.fr/",
        "canonical_url": "https://trentpower.fr/",
        "language": ["en-AU", "fr"],
        "edition": {"id": "2026-06-21", "label": "Edition 2026-06-21", "date": "2026-06-21"},
        "author": "Trent Power",
        "publisher": "Trent Power",
        "information_classes": {"declared": [], "attested": []},
        "trust_order": [],
        "integrity": {
            "manifest": "https://trentpower.fr/integrity.json",
            "signature": "https://trentpower.fr/integrity.json.sig",
            "public_key": "https://trentpower.fr/pgp.txt",
            "checksums": "https://trentpower.fr/SHA256SUMS",
        },
        "privacy": {
            "tracking": False,
            "analytics": False,
            "cookies": False,
            "third_party_requests": False,
            "attestations": [],
        },
        "citation": {"text": "Cite me", "format": "text/plain"},
        "license": {"content": "CC-BY-4.0", "portrait": "All rights reserved"},
        "machine_readable": {
            "person": "https://trentpower.fr/person.json",
            "webfinger": "https://trentpower.fr/.well-known/webfinger",
            "security": "https://trentpower.fr/.well-known/security.txt",
            "attestations": [],
        },
        "asset_version": "abc123",
    }


def _make_fixture_repo(root: pathlib.Path, data: dict | None = None) -> None:
    _write(root, vsm.SM_REL, json.dumps(data if data is not None else _valid_metadata()))
    # integrity.checksums points at /SHA256SUMS, so the file must exist on disk.
    _write(root, vsm.CHECKSUMS_REL, "deadbeef  index.html\n")


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vsm.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pristine_metadata_is_green(self):
        _make_fixture_repo(self.root)
        data, errors = vsm.load(self.repo)
        self.assertEqual(errors, [])
        r = vsm.evaluate(self.repo, data)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("all nested shapes present" in o for o in r.oks), r.oks)

    def test_missing_required_key_caught(self):
        data = _valid_metadata()
        del data["asset_version"]
        _make_fixture_repo(self.root, data)
        loaded, _ = vsm.load(self.repo)
        r = vsm.evaluate(self.repo, loaded)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("missing required top-level keys" in f and "asset_version" in f for f in r.fails),
            r.fails,
        )

    def test_forbidden_key_present_caught(self):
        data = _valid_metadata()
        data["asset_bundle"] = {"junk": True}
        _make_fixture_repo(self.root, data)
        loaded, _ = vsm.load(self.repo)
        r = vsm.evaluate(self.repo, loaded)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("forbidden top-level key(s) present" in f and "asset_bundle" in f for f in r.fails),
            r.fails,
        )

    def test_wrong_schema_version_caught(self):
        data = _valid_metadata()
        data["schema_version"] = "2.0"
        _make_fixture_repo(self.root, data)
        loaded, _ = vsm.load(self.repo)
        r = vsm.evaluate(self.repo, loaded)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("schema_version must be '1.0'" in f for f in r.fails),
            r.fails,
        )

    def test_wrong_type_value_caught(self):
        data = _valid_metadata()
        data["type"] = "SomethingElse"
        _make_fixture_repo(self.root, data)
        loaded, _ = vsm.load(self.repo)
        r = vsm.evaluate(self.repo, loaded)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("type must be 'PersonalSiteMetadata'" in f for f in r.fails),
            r.fails,
        )

    def test_nested_value_not_an_object_caught(self):
        # edition is a required nested shape; a non-object value is a shape error,
        # not a missing-key error.
        data = _valid_metadata()
        data["edition"] = "2026-06-21"
        _make_fixture_repo(self.root, data)
        loaded, _ = vsm.load(self.repo)
        r = vsm.evaluate(self.repo, loaded)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("'edition' must be an object" in f and "str" in f for f in r.fails),
            r.fails,
        )

    def test_nested_missing_keys_caught(self):
        # edition present and an object, but missing a required nested key.
        data = _valid_metadata()
        del data["edition"]["date"]
        _make_fixture_repo(self.root, data)
        loaded, _ = vsm.load(self.repo)
        r = vsm.evaluate(self.repo, loaded)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("'edition' missing nested keys" in f and "date" in f for f in r.fails),
            r.fails,
        )

    def test_nested_key_absent_top_level_skips_shape_check(self):
        # when a nested-required key is wholly absent it is reported by the
        # top-level missing-keys rule, and the per-shape loop simply continues.
        data = _valid_metadata()
        del data["edition"]
        _make_fixture_repo(self.root, data)
        loaded, _ = vsm.load(self.repo)
        r = vsm.evaluate(self.repo, loaded)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("missing required top-level keys" in f and "edition" in f for f in r.fails),
            r.fails,
        )
        # the shape loop must not also emit an 'edition' object/nested error.
        self.assertFalse(
            any(
                "'edition' must be an object" in f or "'edition' missing nested" in f
                for f in r.fails
            ),
            r.fails,
        )

    def test_language_not_a_list_caught(self):
        data = _valid_metadata()
        data["language"] = "en-AU"
        _make_fixture_repo(self.root, data)
        loaded, _ = vsm.load(self.repo)
        r = vsm.evaluate(self.repo, loaded)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("language must be a list of strings" in f for f in r.fails),
            r.fails,
        )

    def test_language_list_of_non_strings_caught(self):
        data = _valid_metadata()
        data["language"] = ["en-AU", 7]
        _make_fixture_repo(self.root, data)
        loaded, _ = vsm.load(self.repo)
        r = vsm.evaluate(self.repo, loaded)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("language must be a list of strings" in f for f in r.fails),
            r.fails,
        )

    def test_checksums_url_without_disk_file_caught(self):
        # integrity.checksums ends in /SHA256SUMS, so the file must exist on disk;
        # write the metadata but NOT the checksums file.
        _write(self.root, vsm.SM_REL, json.dumps(_valid_metadata()))
        loaded, _ = vsm.load(self.repo)
        r = vsm.evaluate(self.repo, loaded)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("public/SHA256SUMS does not exist on disk" in f for f in r.fails),
            r.fails,
        )

    def test_checksums_url_not_sha256sums_skips_disk_check(self):
        # a checksums url that does not end in /SHA256SUMS takes the false branch:
        # no disk check, and (everything else valid) the document is green.
        data = _valid_metadata()
        data["integrity"]["checksums"] = "https://trentpower.fr/checksums.txt"
        _write(self.root, vsm.SM_REL, json.dumps(data))
        loaded, _ = vsm.load(self.repo)
        r = vsm.evaluate(self.repo, loaded)
        self.assertTrue(r.ok, msg=r.fails)


class Load(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vsm.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_file_reports_error(self):
        # no site-metadata.json on disk at all.
        data, errors = vsm.load(self.repo)
        self.assertIsNone(data)
        self.assertEqual(len(errors), 1)
        self.assertIn("missing", errors[0])

    def test_invalid_json_reports_error(self):
        _write(self.root, vsm.SM_REL, "{ not valid json ")
        data, errors = vsm.load(self.repo)
        self.assertIsNone(data)
        self.assertEqual(len(errors), 1)
        self.assertIn("invalid JSON", errors[0])


class ExternalInterface(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_main_passes_against_the_real_repo(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vsm.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_main_renders_fail_and_returns_one(self):
        # a fixture repo whose metadata violates a rule drives main()'s
        # FAIL-render branch: rc 1 plus the issue header and per-fail lines.
        data = _valid_metadata()
        data["schema_version"] = "2.0"
        _make_fixture_repo(self.root, data)

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = vsm.main(self.root)

        self.assertEqual(rc, 1)
        printed = out.getvalue()
        self.assertIn("FAIL:", printed)
        self.assertIn("site-metadata.json issue(s)", printed)
        self.assertIn("schema_version must be '1.0'", printed)

    def test_main_renders_load_error_and_returns_one(self):
        # no site-metadata.json on disk drives main()'s load-errors branch.
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = vsm.main(self.root)

        self.assertEqual(rc, 1)
        printed = out.getvalue()
        self.assertIn("FAIL:", printed)
        self.assertIn("missing", printed)


if __name__ == "__main__":
    unittest.main()
