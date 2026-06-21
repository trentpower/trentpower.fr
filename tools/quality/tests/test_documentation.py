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
import unittest.mock

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
        self.assertTrue(any("forbidden stale claim" in f for f in r.fails), r.fails)

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

    def test_layout_error_caught(self):
        # seed a coherent fixture but overwrite the PDF with one whose text
        # bleeds off the left page edge — a layout ERROR the gate must surface.
        self._seed()
        rel = f"{vd.DOC_DIR_REL}/README.pdf"
        doc = _fitz.open()
        page = doc.new_page()
        # x0 below EDGE_TOL (6pt) trips the edge-clip ERROR finding.
        page.insert_text((1, 400), "bleeding text off the left edge here")
        doc.save(self.root / rel)
        doc.close()
        # re-advertise the new bytes so coherence does not mask the layout fail.
        from hashing import sri_sha256

        sri = sri_sha256((self.root / rel).read_bytes())
        _write(
            self.root,
            f"{vd.DOC_DIR_REL}/index.html",
            f'<!doctype html><a integrity="{sri}">README.pdf</a>',
        )
        r = vd.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("edge-clip" in f for f in r.fails), r.fails)


@unittest.skipUnless(_fitz is not None, "PyMuPDF not installed")
class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vd.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


class MainFailRender(unittest.TestCase):
    """main() over failing fixtures: returns 1 and prints FAIL lines to stderr.
    the presence-fail path needs no PDF, so it is not fitz-guarded; the
    evaluate-fail path builds a PDF and is."""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_main(self):
        import contextlib
        import io

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = vd.main(repo_root=self.root)
        return rc, out.getvalue(), err.getvalue()

    def test_main_presence_fail_returns_1(self):
        # only README.txt present — README.pdf + index.html absent. the missing
        # file wins before the fitz precondition, so no PDF is needed here.
        _write(self.root, f"{vd.DOC_DIR_REL}/README.txt", "mirror\n")
        rc, _out, err = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("FAIL:", err)
        self.assertIn("missing public/documentation/README.pdf", err)

    @unittest.skipUnless(_fitz is not None, "PyMuPDF not installed")
    def test_main_evaluate_fail_returns_1(self):
        # all files present but the landing page advertises a wrong hash, so
        # evaluate() fails on coherence and main() renders the FAIL line.
        _write(self.root, f"{vd.DOC_DIR_REL}/README.txt", "plain text mirror\n")
        _make_pdf(self.root, "clean text")
        _write(
            self.root,
            f"{vd.DOC_DIR_REL}/index.html",
            '<!doctype html><a integrity="sha256-WRONGHASH">README.pdf</a>',
        )
        rc, _out, err = self._run_main()
        self.assertEqual(rc, 1)
        self.assertIn("FAIL:", err)
        self.assertIn("does not show the current README.pdf hash", err)

    def test_main_fitz_absent_returns_1(self):
        # force the fitz precondition to fail: present all files (so presence
        # passes) then make `import fitz` raise ImportError inside main(). this
        # exercises the fitz-absent adapter branch even though fitz is installed.
        import builtins
        import contextlib
        import io

        _write(self.root, f"{vd.DOC_DIR_REL}/README.txt", "mirror\n")
        _write(self.root, f"{vd.DOC_DIR_REL}/README.pdf", "not really a pdf\n")
        _write(self.root, f"{vd.DOC_DIR_REL}/index.html", "<!doctype html>")

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "fitz":
                raise ImportError("simulated: PyMuPDF absent")
            return real_import(name, *args, **kwargs)

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with unittest.mock.patch.object(builtins, "__import__", fake_import):
                rc = vd.main(repo_root=self.root)
        self.assertEqual(rc, 1)
        self.assertIn("PyMuPDF (fitz) required", err.getvalue())


if __name__ == "__main__":
    unittest.main()
