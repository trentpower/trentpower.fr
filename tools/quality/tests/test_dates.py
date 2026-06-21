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
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_dates as vd  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent
NOW = datetime.datetime(2026, 6, 18, 12, 0, tzinfo=datetime.UTC)
EDITION = "2026-06-18"
MOD = "2026-06-10"  # within 60 days of EDITION -> not stale


def _make_fixture_repo(root: pathlib.Path) -> None:
    """A coherent repo where every date surface agrees with the manifest."""
    _write(root, vd.IDENTITY_CANONICAL_REL, json.dumps({"edition": EDITION}))
    _write(
        root,
        vd.MANIFEST_REL,
        json.dumps(
            {
                "files": {
                    "index.html": {"modified_iso": MOD},
                    "privacy/index.html": {"modified_iso": MOD},
                }
            }
        ),
    )
    _write(
        root,
        vd.DATE_OVERRIDES_REL,
        json.dumps({"published": {}, "modified": {}, "lastmod": {}, "expires": {}}),
    )
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
        _write(
            self.root,
            vd.SITEMAP_REL,
            "<urlset><url><loc>https://trentpower.fr/</loc><lastmod>2020-01-01</lastmod></url></urlset>",
        )
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
        _write(
            self.root,
            vd.DATE_OVERRIDES_REL,
            json.dumps(
                {"expires": {"/.well-known/security.txt": {"date": "2099-12-31", "reason": "doc"}}}
            ),
        )
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertTrue(r.ok, msg=r.fails)  # mismatch never fails
        self.assertTrue(
            any("security.txt" in w and "differs from override" in w for w in r.warns), r.warns
        )

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
        _write(
            self.root,
            "public/page.html",
            '<script type="application/ld+json">{"x":"Validated"}</script>\n',
        )
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        # the word inside an open ld+json block is tolerated -> no fail from it.
        self.assertFalse(any("non-canonical trust term" in f for f in r.fails), r.fails)

    def test_override_missing_reason_fails(self):
        _write(
            self.root,
            vd.DATE_OVERRIDES_REL,
            json.dumps({"lastmod": {"/foo": {"date": "2026-06-10"}}}),
        )  # no reason
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("missing non-empty 'reason'" in f for f in r.fails), r.fails)

    def test_stale_file_is_a_warning(self):
        _write(
            self.root,
            vd.MANIFEST_REL,
            json.dumps({"files": {"index.html": {"modified_iso": "2026-01-01"}}}),
        )  # >60d before edition
        # keep sitemap consistent with the new manifest date so only staleness fires
        _write(
            self.root,
            vd.SITEMAP_REL,
            "<urlset><url><loc>https://trentpower.fr/</loc><lastmod>2026-01-01</lastmod></url></urlset>",
        )
        _write(self.root, "public/index.html", '<script>{"dateModified":"2026-01-01"}</script>\n')
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertTrue(any(w.startswith("stale:") for w in r.warns), r.warns)

    def test_overrides_non_dict_section_is_skipped(self):
        # a section whose value is not a dict is ignored by the reason check
        # (no crash, no count). published is not read by check_sitemap, so a
        # list there exercises the non-dict branch without tripping the sitemap.
        _write(
            self.root,
            vd.DATE_OVERRIDES_REL,
            json.dumps({"published": ["not", "a", "dict"], "modified": {}, "lastmod": {}}),
        )
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertTrue(any("0 published" in ok for ok in r.oks), r.oks)

    def test_override_leaf_neither_str_nor_dict_is_skipped(self):
        # a non-str / non-dict leaf (e.g. a number) is neither counted nor faulted.
        _write(
            self.root,
            vd.DATE_OVERRIDES_REL,
            json.dumps({"published": {"/": 42}, "modified": {}, "lastmod": {}}),
        )
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("0 published" in ok for ok in r.oks), r.oks)

    def test_published_short_form_string_leaf_counts_no_reason(self):
        # the short string form { "/": "2026-02-15" } counts without a reason.
        _write(
            self.root,
            vd.DATE_OVERRIDES_REL,
            json.dumps({"published": {"/": "2026-02-15"}, "modified": {}, "lastmod": {}}),
        )
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("1 published" in ok for ok in r.oks), r.oks)

    def test_sitemap_missing_fails(self):
        (self.root / vd.SITEMAP_REL).unlink()
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("sitemap.xml: missing" in f for f in r.fails), r.fails)

    def test_sitemap_url_block_without_loc_or_lastmod_is_skipped(self):
        # a <url> block missing <lastmod> is not counted; the well-formed one is.
        _write(
            self.root,
            vd.SITEMAP_REL,
            "<urlset>"
            "<url><loc>https://trentpower.fr/nolastmod/</loc></url>"
            f"<url><loc>https://trentpower.fr/</loc><lastmod>{MOD}</lastmod></url>"
            "</urlset>",
        )
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("sitemap.xml: 1 URLs checked" in ok for ok in r.oks), r.oks)

    def test_sitemap_loc_with_no_manifest_or_override_fails(self):
        # a url with no manifest entry and no lastmod override fails with guidance.
        _write(
            self.root,
            vd.SITEMAP_REL,
            "<urlset>"
            f"<url><loc>https://trentpower.fr/orphan.json</loc><lastmod>{MOD}</lastmod></url>"
            "</urlset>",
        )
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("no manifest entry" in f and "orphan.json" in f for f in r.fails), r.fails
        )

    def test_sitemap_override_supplies_expected_date(self):
        # an override date drives the comparison (source = "override").
        _write(
            self.root,
            vd.SITEMAP_REL,
            "<urlset>"
            "<url><loc>https://trentpower.fr/integrity.json.sig</loc>"
            "<lastmod>2020-01-01</lastmod></url>"
            "</urlset>",
        )
        _write(
            self.root,
            vd.DATE_OVERRIDES_REL,
            json.dumps(
                {"lastmod": {"/integrity.json.sig": {"date": "2026-06-10", "reason": "excluded"}}}
            ),
        )
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("override says 2026-06-10" in f for f in r.fails), r.fails)

    def test_jsonld_datemod_not_iso_prefix_fails(self):
        _write(self.root, "public/index.html", '<script>{"dateModified":"not-a-date"}</script>\n')
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("does not start with YYYY-MM-DD" in f for f in r.fails), r.fails)

    def test_jsonld_datemod_no_manifest_entry_fails(self):
        # a dateModified on a page absent from the manifest fails with guidance.
        _write(self.root, vd.MANIFEST_REL, json.dumps({"files": {}}))
        _write(self.root, "public/index.html", f'<script>{{"dateModified":"{MOD}"}}</script>\n')
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("no manifest entry" in f for f in r.fails), r.fails)

    def test_integrity_json_missing_fails(self):
        (self.root / vd.INTEGRITY_REL).unlink()
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("integrity.json: missing" in f for f in r.fails), r.fails)

    def test_integrity_json_invalid_json_fails(self):
        _write(self.root, vd.INTEGRITY_REL, "{not json")
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("integrity.json: invalid JSON" in f for f in r.fails), r.fails)

    def test_integrity_generated_not_iso_fails(self):
        _write(self.root, vd.INTEGRITY_REL, json.dumps({"generated": "June 2026"}))
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("is not YYYY-MM-DD" in f for f in r.fails), r.fails)

    def test_placeholder_sweep_skips_undecodable_bytes(self):
        # a non-utf8 file under public/ raises UnicodeDecodeError and is skipped,
        # not crashed on; the green path still holds.
        _fixture.write_bytes(self.root, "public/blob.txt", b"\xff\xfe\x00bad")
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("no unresolved placeholders" in ok for ok in r.oks), r.oks)

    def test_security_txt_missing_fails(self):
        (self.root / vd.SECURITY_TXT_REL).unlink()
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("security.txt: missing" in f for f in r.fails), r.fails)

    def test_security_txt_no_expires_line_fails(self):
        _write(self.root, vd.SECURITY_TXT_REL, "Contact: mailto:x@trentpower.fr\n")
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("no Expires: line found" in f for f in r.fails), r.fails)

    def test_security_txt_unparseable_expires_fails(self):
        _write(self.root, vd.SECURITY_TXT_REL, "Expires: not-a-timestamp\n")
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(r.ok)
        self.assertTrue(any("not parseable as RFC 3339" in f for f in r.fails), r.fails)

    def test_security_txt_naive_expires_treated_as_utc(self):
        # an Expires with no timezone is normalised to UTC and compared (future -> ok).
        _write(self.root, vd.SECURITY_TXT_REL, "Expires: 2027-01-01T00:00:00\n")
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("security.txt Expires=" in ok for ok in r.oks), r.oks)

    def test_security_txt_override_matches_no_warning(self):
        # override date equals the actual expiry -> no mismatch warning.
        _write(
            self.root,
            vd.DATE_OVERRIDES_REL,
            json.dumps(
                {"expires": {"/.well-known/security.txt": {"date": "2027-01-01", "reason": "doc"}}}
            ),
        )
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertFalse(any("differs from override" in w for w in r.warns), r.warns)

    def test_stale_bad_edition_returns_without_warning(self):
        # check_stale_files swallows an unparseable edition (no crash, no stale warn).
        ctx = self._ctx()
        bad = vd.Ctx(edition="not-a-date", manifest=ctx.manifest, overrides=ctx.overrides)
        r = vd.evaluate(self.repo, bad, NOW)
        self.assertFalse(any(w.startswith("stale:") for w in r.warns), r.warns)

    def test_stale_skips_entries_with_no_or_bad_iso(self):
        # a manifest entry without modified_iso and one with an unparseable iso
        # are both skipped by the staleness scan.
        _write(
            self.root,
            vd.MANIFEST_REL,
            json.dumps(
                {
                    "files": {
                        "index.html": {"modified_iso": MOD},
                        "a.html": {},
                        "b.html": {"modified_iso": "garbage"},
                    }
                }
            ),
        )
        r = vd.evaluate(self.repo, self._ctx(), NOW)
        self.assertFalse(any(w.startswith("stale:") for w in r.warns), r.warns)


class Helpers(unittest.TestCase):
    """direct tests over the pure helper functions — many small branches that
    are cheaper to hit at the helper boundary than through a fixture repo."""

    def test_resolve_override_non_dict_is_none(self):
        # entry is not a dict -> not a date-bearing leaf.
        self.assertIsNone(vd._resolve_override("2026-06-10", EDITION))

    def test_resolve_override_no_date_is_none(self):
        # dict without a date key -> none.
        self.assertIsNone(vd._resolve_override({"reason": "doc"}, EDITION))

    def test_resolve_override_edition_token_resolves_to_edition(self):
        self.assertEqual(vd._resolve_override({"date": "edition"}, EDITION), EDITION)

    def test_resolve_override_literal_date_passthrough(self):
        self.assertEqual(vd._resolve_override({"date": "2026-06-10"}, EDITION), "2026-06-10")


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

    def test_missing_identity_canonical_returns_error(self):
        (self.root / vd.IDENTITY_CANONICAL_REL).unlink()
        ctx, errors = vd.load(self.repo)
        self.assertIsNone(ctx)
        self.assertTrue(any("identity_canonical" in e for e in errors), errors)

    def test_missing_overrides_file_loads_empty_overrides(self):
        # date_overrides.json is optional — absent means an empty overrides dict.
        (self.root / vd.DATE_OVERRIDES_REL).unlink()
        ctx, errors = vd.load(self.repo)
        self.assertEqual(errors, [])
        self.assertEqual(ctx.overrides, {})

    def test_invalid_overrides_json_returns_error(self):
        _write(self.root, vd.DATE_OVERRIDES_REL, "{not valid json")
        ctx, errors = vd.load(self.repo)
        self.assertIsNone(ctx)
        self.assertTrue(any("date_overrides.json invalid" in e for e in errors), errors)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vd.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_main_renders_failures_and_returns_one(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture_repo(root)
            # seed a drift so evaluate() reports at least one failure.
            _write(
                root,
                vd.SITEMAP_REL,
                "<urlset><url><loc>https://trentpower.fr/</loc>"
                "<lastmod>2020-01-01</lastmod></url></urlset>",
            )
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vd.main(root, now=NOW)
        out = buf.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("ERROR", out)
        self.assertIn("RESULT:", out)
        self.assertTrue(any("error(s)" in line for line in out.splitlines()), out)

    def test_main_renders_load_errors_and_returns_one(self):
        # a load-stage error (missing manifest) is printed as FAIL: on stderr
        # and short-circuits with rc 1 before evaluate() runs.
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture_repo(root)
            (root / vd.MANIFEST_REL).unlink()
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = vd.main(root, now=NOW)
        out = err.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("FAIL:", out)
        self.assertIn("file-metadata.json", out)


if __name__ == "__main__":
    unittest.main()
