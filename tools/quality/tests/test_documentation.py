#!/usr/bin/env python3
"""Tests for the /documentation/ surface gate
(tools/quality/validate_documentation.py).

Cross `evaluate(Repo)` over a fixture repo: a minimal fitz-generated PDF plus a
landing-page index.html that advertises its sha256. Assert on the Result, never
on stdout. The ExternalInterface test runs `main(REPO_ROOT)` against the real
repo. fitz is a hard dependency for any test that generates a PDF, so those are
skipped when PyMuPDF is absent.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import unittest

import _fixture  # noqa: E402

_fixture.bootstrap()
import pathlib  # noqa: E402

import validate_documentation as vd  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

try:
    import fitz as _fitz
except ImportError:
    _fitz = None


def _make_pdf(root: pathlib.Path, text: str = "clean text") -> bytes:
    """write a minimal one-page README.pdf with the given body text; return
    its bytes."""
    rel = f"{vd.DOC_DIR_REL}/README.pdf"
    (root / vd.DOC_DIR_REL).mkdir(parents=True, exist_ok=True)
    doc = _fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(root / rel)
    doc.close()
    return (root / rel).read_bytes()


@unittest.skipUnless(_fitz is not None, "PyMuPDF not installed")
class Evaluate(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vd.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _seed(self, pdf_text: str = "clean text", *, advertise: bool = True):
        """build a coherent fixture: README.txt, a fitz PDF, and an index.html
        advertising the PDF's real sha256 (unless advertise is False)."""
        _write(self.root, f"{vd.DOC_DIR_REL}/README.txt", "plain text mirror\n")
        pdf_bytes = _make_pdf(self.root, pdf_text)
        from hashing import sri_sha256

        sri = sri_sha256(pdf_bytes) if advertise else "sha256-WRONGHASH"
        _write(
            self.root,
            f"{vd.DOC_DIR_REL}/index.html",
            f'<!doctype html><a integrity="{sri}">README.pdf</a>',
        )

    def test_coherent_fixture_green(self):
        self._seed()
        r = vd.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)

    def test_stale_claim_in_pdf_caught(self):
        # seed a forbidden phrase verbatim into the PDF text.
        self._seed(pdf_text="connect-src 'none'")
        r = vd.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("forbidden stale claim" in f for f in r.fails), r.fails
        )

    def test_hash_incoherence_caught(self):
        # landing page advertises a hash that does not match the PDF bytes.
        self._seed(advertise=False)
        r = vd.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("does not show the current README.pdf hash" in f for f in r.fails),
            r.fails,
        )

    def test_missing_file_caught(self):
        # only README.txt present — index.html + README.pdf absent.
        _write(self.root, f"{vd.DOC_DIR_REL}/README.txt", "mirror\n")
        r = vd.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("missing public/documentation/README.pdf" in f for f in r.fails),
            r.fails,
        )


@unittest.skipUnless(_fitz is not None, "PyMuPDF not installed")
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
