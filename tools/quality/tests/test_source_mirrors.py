#!/usr/bin/env python3
"""Tests for the source-mirror gate (tools/verify/validate_source_mirrors.py).

These cross the module's interface — `evaluate(Repo, Ctx) -> Result` and
`load(Repo)` — over a tiny fixture repo. No monkeypatching: the fixture repo is
the second filesystem adapter, so the whole compute path runs over it. Tests
assert on the returned Result, never on stdout, so they survive internal
refactors.

The fixture pins a minimal coherent repo: one public file plus its byte-matching
/source/ mirror plus a source-manifest.json whose size + sha256 agree with the
mirror on disk. evaluate() over that fixture is green. Each defect test seeds one
drift and asserts the matching failure surfaces.

Stdlib unittest — no pytest dep.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import tempfile
import unittest

import _fixture

_fixture.bootstrap()

import validate_source_mirrors as vsm  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

# the validator imports the generator's MIRROR map at load(); the fixture
# replaces that Ctx with a tiny hand-built map so evaluate() runs entirely
# over the fixture repo. one text mirror: a public file -> its /source/ .txt.
PUBLIC_FILE = "hello.txt"
MIRROR_NAME = "hello.txt.txt"
BODY = b"hello mirror\n"

# REQUIRED_MIRRORS is a hard global gate (the trust-system pages must always
# have a mirror). a coherent green fixture must therefore satisfy every
# required mirror too: each gets a live public file, a byte-matching mirror,
# a mirror-map entry, and a manifest record. derive the (live, mirror) pairs
# off the required-mirror names: source/<X>.txt mirrors live url public/<X>.
def _required_pairs() -> list[tuple[str, str]]:
    pairs = []
    for mirror_name in sorted(vsm.REQUIRED_MIRRORS):
        live = mirror_name[:-4]  # strip the trailing ".txt"
        pairs.append((live, mirror_name))
    return pairs


def _ctx(extra: list[tuple[str, str]] | None = None) -> vsm.Ctx:
    """A Ctx whose mirror map carries the one fixture entry plus every required
    mirror, so the required-mirror gate is satisfied. all entries are plain
    non-html, non-htaccess, non-authored mirrors → the src_bytes == dst_bytes
    comparison path."""
    mirror = [(PUBLIC_FILE, MIRROR_NAME), *_required_pairs()]
    if extra:
        mirror = [*mirror, *extra]
    return vsm.Ctx(
        mirror=mirror,
        mirror_map={},
        banner_css=b"",
        banner_js=b"",
        htaccess_transform=lambda b: b,
    )


def _record(name: str, body: bytes) -> dict:
    from hashing import sha256_b64

    return {
        "name": name,
        "mirror_bytes": len(body),
        "size": len(body),
        "sha256": sha256_b64(body),
        "modified": "2026-06-18",
    }


def _make_fixture_repo(root: pathlib.Path) -> None:
    """A coherent repo: the fixture public file + its byte-matching /source/
    mirror, every required trust-system mirror likewise, and a
    source-manifest.json whose size + sha256 agree with the mirrors on disk."""
    import json

    files = []
    for live, mirror_name in [(PUBLIC_FILE, MIRROR_NAME), *_required_pairs()]:
        _fixture.write_bytes(root, f"public/{live}", BODY)
        _fixture.write_bytes(root, f"public/source/{mirror_name}", BODY)
        files.append(_record(mirror_name, BODY))
    _write(
        root,
        "public/source/source-manifest.json",
        json.dumps({"files": files, "images": []}),
    )


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _make_fixture_repo(self.root)
        self.repo = vsm.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pristine_all_green(self):
        r = vsm.evaluate(self.repo, _ctx())
        # the only entry is byte-matched and manifest-consistent; nothing else
        # in the fixture tree, so no completeness/extra failures fire.
        self.assertTrue(r.ok, msg=r.fails)
        self.assertIn("source mirrors", r.summary)

    def test_mirror_bytes_differ_from_source_fails(self):
        # seeded defect: mirror bytes drift from the live public file.
        _fixture.write_bytes(self.root, f"public/source/{MIRROR_NAME}", b"tampered\n")
        r = vsm.evaluate(self.repo, _ctx())
        self.assertFalse(r.ok)
        self.assertTrue(
            any(f.startswith(f"DRIFT: {PUBLIC_FILE} ") for f in r.fails), r.fails
        )

    def test_missing_required_mirror_fails(self):
        # seeded defect: a required trust-system mirror is removed from disk.
        required = sorted(vsm.REQUIRED_MIRRORS)[0]
        (self.root / "public" / "source" / required).unlink()
        r = vsm.evaluate(self.repo, _ctx())
        self.assertFalse(r.ok)
        self.assertTrue(
            any(f.startswith(f"REQUIRED MIRROR MISSING: source/{required}") for f in r.fails),
            r.fails,
        )

    def test_unmirrored_unexcluded_public_file_fails(self):
        # seeded defect: a public file with no mirror and no exclusion entry.
        _fixture.write_bytes(self.root, "public/orphan.txt", b"no mirror\n")
        r = vsm.evaluate(self.repo, _ctx())
        self.assertFalse(r.ok)
        self.assertTrue(
            any(f.startswith("COMPLETENESS: orphan.txt") for f in r.fails), r.fails
        )

    def test_extra_unlisted_mirror_fails(self):
        # seeded defect: a *.txt under /source/ that is not in MIRROR.
        _fixture.write_bytes(self.root, "public/source/stray.txt", b"x\n")
        r = vsm.evaluate(self.repo, _ctx())
        self.assertFalse(r.ok)
        self.assertTrue(
            any(f.startswith("EXTRA: source/stray.txt") for f in r.fails), r.fails
        )


class Load(unittest.TestCase):
    def test_load_returns_real_mirror_map(self):
        # load() imports the production generator; the map must be non-empty.
        repo = vsm.Repo(REPO_ROOT)
        ctx, errors = vsm.load(repo)
        self.assertEqual(errors, [])
        self.assertIsNotNone(ctx)
        self.assertTrue(len(ctx.mirror) > 0)


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vsm.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
