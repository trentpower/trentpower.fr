#!/usr/bin/env python3
"""Tests for the archive-text-casing gate
(tools/quality/validate_archive_text_casing.py).

Cross `evaluate(Repo, Ctx)` / `load(Repo)` over a fixture repo. Assert on the
Result, never on stdout.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import io
import pathlib
import tempfile
import unittest
import zipfile

import _fixture

_fixture.bootstrap()

import validate_archive_text_casing as vatc  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

EDITION = "2026-05-09"
# clean orientation file bodies — lowercase prose, title-case labels.
_CLEAN = {
    "FILES.txt": "this archive lists the published files for the edition.\n",
    "FONT-LICENSE-NOTICE.txt": "the bundled fonts ship under their upstream licences.\n",
    "README.txt": "Edition: 2026-05-09\nthis archive mirrors the published edition.\n",
    "RELEASE.txt": "Date: 2026-05-09\nthis is the release manifest for the edition.\n",
    "VERIFY.txt": "run the verify steps described in this file to check the archive.\n",
}


def _seed_identity(root: pathlib.Path, edition: str = EDITION) -> None:
    _write(root, vatc.IDENTITY_CANONICAL_REL, f'{{"edition": "{edition}"}}')


def _seed_zip(root: pathlib.Path, bodies: dict[str, str], edition: str = EDITION) -> None:
    rel = f"public/integrity/releases/{edition}/trentpower-fr-{edition}.zip"
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in bodies.items():
            zf.writestr(name, text)
    p.write_bytes(buf.getvalue())


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vatc.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_archive_green(self):
        _seed_identity(self.root)
        _seed_zip(self.root, _CLEAN)
        r = vatc.evaluate(self.repo, vatc.load(self.repo))
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.zip_name, f"trentpower-fr-{EDITION}.zip")

    def test_wrong_casing_caught(self):
        bodies = dict(_CLEAN)
        # shouting prose: an ordinary capitalised word in a free-running line.
        bodies["README.txt"] = "Edition: 2026-05-09\nThis archive mirrors the edition.\n"
        _seed_identity(self.root)
        _seed_zip(self.root, bodies)
        r = vatc.evaluate(self.repo, vatc.load(self.repo))
        self.assertFalse(r.ok)
        self.assertTrue(any("uppercase tokens in prose" in f for f in r.fails), r.fails)

    def test_missing_orientation_file_caught(self):
        bodies = dict(_CLEAN)
        del bodies["VERIFY.txt"]
        _seed_identity(self.root)
        _seed_zip(self.root, bodies)
        r = vatc.evaluate(self.repo, vatc.load(self.repo))
        self.assertFalse(r.ok)
        self.assertTrue(any("missing orientation file" in f for f in r.fails), r.fails)

    def test_no_zip_skips(self):
        _seed_identity(self.root)
        r = vatc.evaluate(self.repo, vatc.load(self.repo))
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(r.skipped)

    def test_clearsign_block_caught(self):
        # an orientation file carrying an inline pgp block must be flagged
        # because archive_only files are not directly_signed (line 205).
        bodies = dict(_CLEAN)
        bodies["README.txt"] = (
            f"{vatc.CLEARSIGN_HEADER}\nEdition: 2026-05-09\n"
            "this archive mirrors the published edition.\n"
        )
        _seed_identity(self.root)
        _seed_zip(self.root, bodies)
        r = vatc.evaluate(self.repo, vatc.load(self.repo))
        self.assertFalse(r.ok)
        self.assertTrue(any("clearsigned block" in f for f in r.fails), r.fails)

    def test_shouting_acronym_run_caught(self):
        # a multi-letter uppercase run inside a plain prose token is loud
        # shouting and gets flagged via the [A-Z]{2,} branch (lines 137-138).
        bodies = dict(_CLEAN)
        bodies["FILES.txt"] = "this archive lists its files LOUDly for the reader.\n"
        _seed_identity(self.root)
        _seed_zip(self.root, bodies)
        r = vatc.evaluate(self.repo, vatc.load(self.repo))
        self.assertFalse(r.ok)
        self.assertTrue(
            any("LOUDly" in f for f in r.fails),
            r.fails,
        )


class PreserveToken(unittest.TestCase):
    # direct coverage of _is_preserve_token branches that line.split()
    # cannot reach through prose (empty token) or that need specific shapes.
    def test_empty_token_is_preserved(self):
        self.assertTrue(vatc._is_preserve_token(""))  # line 100

    def test_pure_hex_is_preserved(self):
        self.assertTrue(vatc._is_preserve_token("deadbeef0123"))  # line 102

    def test_camel_case_is_preserved(self):
        self.assertTrue(vatc._is_preserve_token("someThing"))  # line 106


class Load(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vatc.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_identity_file_yields_no_zip(self):
        # no identity_canonical.json at all: the is_file guard is false so
        # edition stays empty and load returns a none zip path (lines 177->179, 180).
        ctx = vatc.load(self.repo)
        self.assertIsNone(ctx.zip_path)

    def test_empty_edition_yields_no_zip(self):
        # identity present but edition empty: still the skip case (line 180).
        _write(self.root, vatc.IDENTITY_CANONICAL_REL, '{"edition": ""}')
        ctx = vatc.load(self.repo)
        self.assertIsNone(ctx.zip_path)


class ExternalInterface(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_main_passes_against_the_real_repo(self):
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vatc.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_main_skips_when_no_zip(self):
        # no identity, no zip: main renders the skip line and returns 0
        # (lines 227-228).
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vatc.main(self.root)
        self.assertEqual(rc, 0)
        self.assertIn("skipping archive-casing check", buf.getvalue())

    def test_main_fails_and_renders_offenders(self):
        # a seeded casing defect makes r.fails true: main prints the FAIL
        # header plus the offender lines and returns 1 (lines 231-236).
        import contextlib

        bodies = dict(_CLEAN)
        bodies["README.txt"] = "Edition: 2026-05-09\nThis archive mirrors the edition.\n"
        _seed_identity(self.root)
        _seed_zip(self.root, bodies)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vatc.main(self.root)
        out = buf.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("FAIL:", out)
        self.assertIn("archive-text-casing issue(s):", out)

    def test_main_truncates_overflow_offenders(self):
        # more than 50 offending lines exercises the "... and N more" tail
        # (lines 234-235).
        import contextlib

        bodies = dict(_CLEAN)
        shouting = "".join(f"This line number {n} shouts loudly here.\n" for n in range(60))
        bodies["FILES.txt"] = shouting
        _seed_identity(self.root)
        _seed_zip(self.root, bodies)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vatc.main(self.root)
        out = buf.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("more", out)


if __name__ == "__main__":
    unittest.main()
