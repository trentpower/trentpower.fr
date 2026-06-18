#!/usr/bin/env python3
"""Tests for the date-drift gate (tools/quality/validate_dates.py).

These cross the module's interface — `evaluate(Repo, Ctx, now) -> Result` and
`load(Repo)` — over a tiny fixture repo at a frozen instant. No monkeypatching:
the fixture repo is the second filesystem adapter and the injected `now` is the
second clock adapter, so both seams are real. Tests assert on the returned
Result, never on stdout, so they survive internal refactors.

Stdlib unittest — no pytest dep.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import datetime
import json
import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
for _sub in ("lib", "build", "quality", "verify"):
    sys.path.insert(0, str(TOOLS / _sub))

import validate_dates as vd  # noqa: E402

REPO_ROOT = TOOLS.parent
NOW = datetime.datetime(2026, 6, 18, 12, 0, tzinfo=datetime.UTC)
EDITION = "2026-06-18"
MOD = "2026-06-10"  # within 60 days of EDITION -> not stale


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _make_fixture_repo(root: pathlib.Path) -> None:
    """A coherent repo where every date surface agrees with the manifest."""
    _write(root, vd.IDENTITY_CANONICAL_REL, json.dumps({"edition": EDITION}))
    _write(
        root,
        vd.MANIFEST_REL,
        json.dumps({"files": {"index.html": {"modified_iso": MOD}, "privacy/index.html": {"modified_iso": MOD}}}),
    )
    _write(root, vd.DATE_OVERRIDES_REL, json.dumps({"published": {}, "modified": {}, "lastmod": {}, "expires": {}}))
    _write(
        root,
        vd.SITEMAP_REL,
        "<urlset>"
        f"<url><loc>https://trentpower.fr/</loc><lastmod>{MOD}</lastmod></url>"
        f"<url><loc>https://trentpower.fr/privacy/</loc><lastmod>{MOD}</lastmod></url>"
        "</urlset>",
    )
    _write(root, vd.INTEGRITY_REL, json.dumps({"generated": MOD}))
    _write(
        root,
        vd.SECURITY_TXT_REL,
        "Contact: mailto:x@trentpower.fr\nExpires: 2027-01-01T00:00:00Z\n",
    )
    _write(root, "public/index.html", f'<script>{{"dateModified":"{MOD}"}}</script>\n')


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _make_fixture_repo(self.root)
        self.repo = vd.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _ctx(self):
        ctx, errors = vd.load(self.repo)
        self.assertEqual(errors, [])
        return ctx

    def test_pristine_all_green(self):
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.warns, [])

    def test_sitemap_lastmod_drift(self):
        _write(self.root, vd.SITEMAP_REL,
               "<urlset><url><loc>https://trentpower.fr/</loc><lastmod>2020-01-01</lastmod></url></urlset>")
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("sitemap:" in f and "manifest says" in f for f in r.fails), r.fails)

    def test_jsonld_datemod_drift(self):
        _write(self.root, "public/index.html", '<script>{"dateModified":"2020-01-01"}</script>\n')
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("dateModified" in f and "manifest says" in f for f in r.fails), r.fails)

    def test_integrity_generated_in_future(self):
        _write(self.root, vd.INTEGRITY_REL, json.dumps({"generated": "2099-01-01"}))
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("integrity.json" in f and "future" in f for f in r.fails), r.fails)

    def test_security_txt_expired(self):
        _write(self.root, vd.SECURITY_TXT_REL, "Expires: 2020-01-01T00:00:00Z\n")
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("security.txt" in f and "past" in f for f in r.fails), r.fails)

    def test_security_txt_override_mismatch_is_a_warning(self):
        _write(self.root, vd.DATE_OVERRIDES_REL, json.dumps(
            {"expires": {"/.well-known/security.txt": {"date": "2099-12-31", "reason": "doc"}}}))
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertTrue(r.ok, msg=r.fails)  # mismatch never fails
        self.assertTrue(any("security.txt" in w and "differs from override" in w for w in r.warns), r.warns)

    def test_unresolved_placeholder_fails(self):
        _write(self.root, "public/foo.html", "lastmod {{lastmod:/index.html}} here\n")
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("placeholder" in f for f in r.fails), r.fails)

    def test_validated_word_fails_outside_ldjson(self):
        _write(self.root, "public/page.html", "<p>Validated yesterday</p>\n")
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("non-canonical trust term" in f for f in r.fails), r.fails)

    def test_validated_key_tolerated_inside_ldjson(self):
        _write(self.root, "public/page.html",
               '<script type="application/ld+json">{"x":"Validated"}</script>\n')
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        # the word inside an open ld+json block is tolerated -> no fail from it.
        self.assertFalse(any("non-canonical trust term" in f for f in r.fails), r.fails)

    def test_override_missing_reason_fails(self):
        _write(self.root, vd.DATE_OVERRIDES_REL, json.dumps(
            {"lastmod": {"/foo": {"date": "2026-06-10"}}}))  # no reason
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("missing non-empty 'reason'" in f for f in r.fails), r.fails)

    def test_stale_file_is_a_warning(self):
        _write(self.root, vd.MANIFEST_REL, json.dumps(
            {"files": {"index.html": {"modified_iso": "2026-01-01"}}}))  # >60d before edition
        # keep sitemap consistent with the new manifest date so only staleness fires
        _write(self.root, vd.SITEMAP_REL,
               "<urlset><url><loc>https://trentpower.fr/</loc><lastmod>2026-01-01</lastmod></url></urlset>")
        _write(self.root, "public/index.html", '<script>{"dateModified":"2026-01-01"}</script>\n')
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertTrue(any(w.startswith("stale:") for w in r.warns), r.warns)


class Load(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _make_fixture_repo(self.root)
        self.repo = vd.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_manifest_returns_error(self):
        (self.root / vd.MANIFEST_REL).unlink()
        ctx, errors = vd.load(self.repo)
        self.assertIsNone(ctx)
        self.assertTrue(any("file-metadata.json" in e for e in errors), errors)

    def test_bad_edition_returns_error(self):
        _write(self.root, vd.IDENTITY_CANONICAL_REL, json.dumps({"edition": "nope"}))
        ctx, errors = vd.load(self.repo)
        self.assertIsNone(ctx)
        self.assertTrue(any("edition" in e for e in errors), errors)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vd.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
