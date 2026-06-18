#!/usr/bin/env python3
"""Tests for the file-size honesty gate (tools/quality/validate_file_sizes.py).

These cross the module's interface — `evaluate(Repo) -> Result` — over a fixture
public/ tree whose recorded sizes are computed from the real bytes on disk. No
monkeypatching: the fixture repo is the second filesystem adapter. Tests assert
on the returned Result, never on stdout.

Stdlib unittest — no pytest dep.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import json
import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
for _sub in ("lib", "build", "quality", "verify"):
    sys.path.insert(0, str(TOOLS / _sub))

import validate_file_sizes as vfs  # noqa: E402
from sizes import humanise_bytes  # noqa: E402

REPO_ROOT = TOOLS.parent
INDEX_HTML = "<p>hello world</p>\n"
INDEX_BYTES = len(INDEX_HTML.encode("utf-8"))


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _make_fixture_repo(root: pathlib.Path) -> None:
    """A coherent public/ tree whose recorded sizes match disk exactly."""
    _write(root, "public/index.html", INDEX_HTML)
    _write(
        root,
        "public/file-metadata.json",
        json.dumps({"files": {"index.html": {
            "bytes": INDEX_BYTES,
            "size_human_en": humanise_bytes(INDEX_BYTES, lang="en"),
            "size_human_fr": humanise_bytes(INDEX_BYTES, lang="fr"),
        }}}),
    )
    _write(root, "public/source/source-manifest.json", json.dumps({"files": []}))


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _make_fixture_repo(self.root)
        self.repo = vfs.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _meta(self):
        return json.loads((self.root / "public/file-metadata.json").read_text())

    def _set_meta(self, data):
        _write(self.root, "public/file-metadata.json", json.dumps(data))

    def test_pristine_green(self):
        r = vfs.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.errors)
        self.assertEqual(r.warnings, [])

    def test_byte_mismatch_errors(self):
        d = self._meta(); d["files"]["index.html"]["bytes"] = INDEX_BYTES + 1; self._set_meta(d)
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("bytes=" in e and "disk=" in e for e in r.errors), r.errors)

    def test_human_label_mismatch_errors(self):
        d = self._meta(); d["files"]["index.html"]["size_human_en"] = "9 ZB"; self._set_meta(d)
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("size_human_en" in e for e in r.errors), r.errors)

    def test_listed_but_missing_on_disk_errors(self):
        d = self._meta(); d["files"]["ghost.html"] = {"bytes": 1, "size_human_en": "x", "size_human_fr": "x"}
        self._set_meta(d)
        r = vfs.evaluate(self.repo)
        self.assertTrue(any("ghost.html" in e and "missing on disk" in e for e in r.errors), r.errors)

    def test_source_manifest_size_mismatch_errors(self):
        _write(self.root, "public/source/source-manifest.json", json.dumps({"files": [
            {"name": "x.txt", "live_path": "/index.html", "size": INDEX_BYTES + 5,
             "size_human": "x", "mirror_bytes": 0, "mirror_size_human": "x"},
        ]}))
        _write(self.root, "public/source/x.txt", "mirror\n")
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("source-manifest.json" in e and "size=" in e for e in r.errors), r.errors)

    def test_verification_data_size_mismatch_errors(self):
        _write(self.root, "public/verify/verification-data.js",
               'window.TP_VERIFICATION_MAP = {"/":{"size_bytes":99999,"path":"/index.html"}};\n')
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("verification-data.js" in e and "size_bytes=" in e for e in r.errors), r.errors)

    def test_print_evidence_chip_literal_is_a_hard_error(self):
        _write(self.root, "public/chip.html", '<span class="print-evidence">28 KB</span>\n')
        # cover chip.html in the manifest so only the literal trips.
        b = vfs._size_public(self.repo, "chip.html")
        d = self._meta()
        d["files"]["chip.html"] = {"bytes": b, "size_human_en": humanise_bytes(b, lang="en"),
                                   "size_human_fr": humanise_bytes(b, lang="fr")}
        self._set_meta(d)
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("print-evidence chip contains byte" in e for e in r.errors), r.errors)

    def test_prose_literal_is_only_a_warning(self):
        _write(self.root, "public/prose.html", "<p>about 5 KB of text</p>\n")
        r = vfs.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.errors)  # prose literal never fails
        self.assertTrue(any("prose byte literal" in w for w in r.warnings), r.warnings)


# the real-repo smoke needs a fully-built public/ tree; the font subsets are
# build-generated and absent in a bare checkout (CI's test job), so skip there.
_FULL_TREE = bool(list((REPO_ROOT / "public" / "fonts" / "subsets").glob("*.woff2")))


class ExternalInterface(unittest.TestCase):
    @unittest.skipUnless(_FULL_TREE, "public/ tree not fully built (font subsets absent)")
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vfs.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
