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
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_file_sizes as vfs  # noqa: E402
from _fixture import write as _write  # noqa: E402
from sizes import humanise_bytes  # noqa: E402

REPO_ROOT = TOOLS.parent
INDEX_HTML = "<p>hello world</p>\n"
INDEX_BYTES = len(INDEX_HTML.encode("utf-8"))


def _make_fixture_repo(root: pathlib.Path) -> None:
    """A coherent public/ tree whose recorded sizes match disk exactly."""
    _write(root, "public/index.html", INDEX_HTML)
    _write(
        root,
        "public/file-metadata.json",
        json.dumps(
            {
                "files": {
                    "index.html": {
                        "bytes": INDEX_BYTES,
                        "size_human_en": humanise_bytes(INDEX_BYTES, lang="en"),
                        "size_human_fr": humanise_bytes(INDEX_BYTES, lang="fr"),
                    }
                }
            }
        ),
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
        d = self._meta()
        d["files"]["index.html"]["bytes"] = INDEX_BYTES + 1
        self._set_meta(d)
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("bytes=" in e and "disk=" in e for e in r.errors), r.errors)

    def test_human_label_mismatch_errors(self):
        d = self._meta()
        d["files"]["index.html"]["size_human_en"] = "9 ZB"
        self._set_meta(d)
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("size_human_en" in e for e in r.errors), r.errors)

    def test_listed_but_missing_on_disk_errors(self):
        d = self._meta()
        d["files"]["ghost.html"] = {"bytes": 1, "size_human_en": "x", "size_human_fr": "x"}
        self._set_meta(d)
        r = vfs.evaluate(self.repo)
        self.assertTrue(
            any("ghost.html" in e and "missing on disk" in e for e in r.errors), r.errors
        )

    def test_source_manifest_size_mismatch_errors(self):
        _write(
            self.root,
            "public/source/source-manifest.json",
            json.dumps(
                {
                    "files": [
                        {
                            "name": "x.txt",
                            "live_path": "/index.html",
                            "size": INDEX_BYTES + 5,
                            "size_human": "x",
                            "mirror_bytes": 0,
                            "mirror_size_human": "x",
                        },
                    ]
                }
            ),
        )
        _write(self.root, "public/source/x.txt", "mirror\n")
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("source-manifest.json" in e and "size=" in e for e in r.errors), r.errors
        )

    def test_verification_data_size_mismatch_errors(self):
        _write(
            self.root,
            "public/verify/verification-data.js",
            'window.TP_VERIFICATION_MAP = {"/":{"size_bytes":99999,"path":"/index.html"}};\n',
        )
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("verification-data.js" in e and "size_bytes=" in e for e in r.errors), r.errors
        )

    def test_print_evidence_chip_literal_is_a_hard_error(self):
        _write(self.root, "public/chip.html", '<span class="print-evidence">28 KB</span>\n')
        # cover chip.html in the manifest so only the literal trips.
        b = vfs._size_public(self.repo, "chip.html")
        d = self._meta()
        d["files"]["chip.html"] = {
            "bytes": b,
            "size_human_en": humanise_bytes(b, lang="en"),
            "size_human_fr": humanise_bytes(b, lang="fr"),
        }
        self._set_meta(d)
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("print-evidence chip contains byte" in e for e in r.errors), r.errors)

    def test_prose_literal_is_only_a_warning(self):
        _write(self.root, "public/prose.html", "<p>about 5 KB of text</p>\n")
        r = vfs.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.errors)  # prose literal never fails
        self.assertTrue(any("prose byte literal" in w for w in r.warnings), r.warnings)

    # ── file-metadata.json structural defects ──────────────────────

    def test_file_metadata_missing_errors(self):
        (self.root / "public/file-metadata.json").unlink()
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("file-metadata.json: file missing" in e for e in r.errors), r.errors
        )

    def test_file_metadata_invalid_json_errors(self):
        _write(self.root, "public/file-metadata.json", "{not json")
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("file-metadata.json: invalid JSON" in e for e in r.errors), r.errors
        )

    def test_file_metadata_files_not_a_dict_errors(self):
        # a truthy non-dict `files` (empty list is falsy and treated as {}).
        self._set_meta({"files": [1, 2]})
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("missing 'files' dict" in e for e in r.errors), r.errors
        )

    # ── source-manifest.json structural defects ────────────────────

    def test_source_manifest_missing_errors(self):
        (self.root / "public/source/source-manifest.json").unlink()
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("source/source-manifest.json: file missing" in e for e in r.errors),
            r.errors,
        )

    def test_source_manifest_invalid_json_errors(self):
        _write(self.root, "public/source/source-manifest.json", "{not json")
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("source/source-manifest.json: invalid JSON" in e for e in r.errors),
            r.errors,
        )

    def test_source_manifest_files_not_a_list_errors(self):
        # a truthy non-list `files` (empty dict is falsy and treated as []).
        _write(
            self.root,
            "public/source/source-manifest.json",
            json.dumps({"files": {"a": 1}}),
        )
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("'files' is not a list" in e for e in r.errors), r.errors
        )

    def test_source_manifest_live_path_missing_on_disk_errors(self):
        _write(
            self.root,
            "public/source/source-manifest.json",
            json.dumps(
                {
                    "files": [
                        {
                            "name": "x.txt",
                            "live_path": "/nope.html",
                            "size": 1,
                            "size_human": "1 B",
                            "mirror_bytes": 0,
                            "mirror_size_human": "0 B",
                        },
                    ]
                }
            ),
        )
        _write(self.root, "public/source/x.txt", "")
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("live_path /nope.html missing on disk" in e for e in r.errors),
            r.errors,
        )

    def test_source_manifest_size_human_mismatch_errors(self):
        # size matches disk but the human label does not.
        mirror = "mirror\n"
        _write(self.root, "public/source/x.txt", mirror)
        mirror_bytes = len(mirror.encode("utf-8"))
        _write(
            self.root,
            "public/source/source-manifest.json",
            json.dumps(
                {
                    "files": [
                        {
                            "name": "x.txt",
                            "live_path": "/index.html",
                            "size": INDEX_BYTES,
                            "size_human": "wrong label",
                            "mirror_bytes": mirror_bytes,
                            "mirror_size_human": vfs._fmt_size_compat(mirror_bytes),
                        },
                    ]
                }
            ),
        )
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("size_human=" in e and "expected" in e for e in r.errors), r.errors
        )

    def test_source_manifest_mirror_missing_on_disk_errors(self):
        _write(
            self.root,
            "public/source/source-manifest.json",
            json.dumps(
                {
                    "files": [
                        {
                            "name": "ghost.txt",
                            "mirror_bytes": 0,
                            "mirror_size_human": "0 B",
                        },
                    ]
                }
            ),
        )
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("mirror source/ghost.txt missing on disk" in e for e in r.errors),
            r.errors,
        )

    def test_source_manifest_mirror_bytes_mismatch_errors(self):
        mirror = "mirror\n"
        _write(self.root, "public/source/x.txt", mirror)
        _write(
            self.root,
            "public/source/source-manifest.json",
            json.dumps(
                {
                    "files": [
                        {
                            "name": "x.txt",
                            "mirror_bytes": 99999,
                            "mirror_size_human": "x",
                        },
                    ]
                }
            ),
        )
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("mirror_bytes=" in e for e in r.errors), r.errors
        )

    def test_source_manifest_mirror_size_human_mismatch_errors(self):
        mirror = "mirror\n"
        _write(self.root, "public/source/x.txt", mirror)
        mirror_bytes = len(mirror.encode("utf-8"))
        _write(
            self.root,
            "public/source/source-manifest.json",
            json.dumps(
                {
                    "files": [
                        {
                            "name": "x.txt",
                            "mirror_bytes": mirror_bytes,
                            "mirror_size_human": "wrong label",
                        },
                    ]
                }
            ),
        )
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("mirror_size_human=" in e and "expected" in e for e in r.errors),
            r.errors,
        )

    def test_source_manifest_entry_without_name_skips_mirror(self):
        # an entry with a valid live_path but no `name` exercises the
        # live-path branch fully and skips the mirror block; gate stays green.
        _write(
            self.root,
            "public/source/source-manifest.json",
            json.dumps(
                {
                    "files": [
                        {
                            "display_name": "index",
                            "live_path": "/index.html",
                            "size": INDEX_BYTES,
                            "size_human": vfs._fmt_size_compat(INDEX_BYTES),
                        },
                    ]
                }
            ),
        )
        r = vfs.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.errors)
        self.assertTrue(
            any("source-manifest.json: 1 entries" in o for o in r.oks), r.oks
        )

    # ── verify/verification-data.js structural defects ─────────────

    def test_verification_data_no_object_literal_errors(self):
        _write(
            self.root,
            "public/verify/verification-data.js",
            "// no map here\n",
        )
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("could not locate" in e for e in r.errors), r.errors
        )

    def test_verification_data_invalid_json_errors(self):
        _write(
            self.root,
            "public/verify/verification-data.js",
            "window.TP_VERIFICATION_MAP = {not json};\n",
        )
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("not valid JSON" in e for e in r.errors), r.errors
        )

    def test_verification_data_path_missing_on_disk_errors(self):
        _write(
            self.root,
            "public/verify/verification-data.js",
            'window.TP_VERIFICATION_MAP = '
            '{"/gone":{"size_bytes":1,"path":"/gone.html"}};\n',
        )
        r = vfs.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("gone.html missing on disk" in e for e in r.errors), r.errors
        )

    def test_verification_data_non_dict_and_pathless_records_skipped(self):
        # a non-dict record and a record with no resolvable path are both
        # skipped silently — the gate stays green and reports the route count.
        records = json.dumps(
            {
                "/a": "not-a-dict",
                "/b": {"size_bytes": 1},
                "/": {"size_bytes": INDEX_BYTES, "path": "/index.html"},
            }
        )
        _write(
            self.root,
            "public/verify/verification-data.js",
            f"window.TP_VERIFICATION_MAP = {records};\n",
        )
        r = vfs.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.errors)
        self.assertTrue(
            any("verification-data.js: 3 routes" in o for o in r.oks), r.oks
        )


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

    def test_main_fails_and_prints_error_on_seeded_defect(self):
        # build a tiny failing fixture: file-metadata.json is absent, so
        # check_file_metadata appends a hard error. main() must render the
        # ERROR line and return 1.
        import contextlib
        import io

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        _make_fixture_repo(root)
        (root / "public/file-metadata.json").unlink()

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vfs.main(root)
        out = buf.getvalue()
        self.assertEqual(rc, 1, msg=out)
        self.assertIn("ERROR file-metadata.json: file missing", out)
        self.assertIn("RESULT: 1 error", out)


if __name__ == "__main__":
    unittest.main()
