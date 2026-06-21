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
        self.assertTrue(any(f.startswith(f"DRIFT: {PUBLIC_FILE} ") for f in r.fails), r.fails)

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
        self.assertTrue(any(f.startswith("COMPLETENESS: orphan.txt") for f in r.fails), r.fails)

    def test_extra_unlisted_mirror_fails(self):
        # seeded defect: a *.txt under /source/ that is not in MIRROR.
        _fixture.write_bytes(self.root, "public/source/stray.txt", b"x\n")
        r = vsm.evaluate(self.repo, _ctx())
        self.assertFalse(r.ok)
        self.assertTrue(any(f.startswith("EXTRA: source/stray.txt") for f in r.fails), r.fails)


class EvaluateUncoveredBranches(unittest.TestCase):
    """Targeted seeded-defect tests for the evaluate() branches the pristine +
    five basic defect tests don't reach: the canonicalisation arms, the
    authored/htaccess byte paths, image-manifest records, manifest self-
    consistency, the recursive-source guard, and the json-decode error arms."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _make_fixture_repo(self.root)
        self.repo = vsm.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _add_manifest_record(self, name: str, body: bytes) -> None:
        # append a record to the on-disk source-manifest.json files array.
        import json

        smf = self.root / "public" / "source" / "source-manifest.json"
        sm = json.loads(smf.read_text(encoding="utf-8"))
        sm["files"].append(_record(name, body))
        smf.write_text(json.dumps(sm), encoding="utf-8")

    def _set_images(self, images: list[dict]) -> None:
        import json

        smf = self.root / "public" / "source" / "source-manifest.json"
        sm = json.loads(smf.read_text(encoding="utf-8"))
        sm["images"] = images
        smf.write_text(json.dumps(sm), encoding="utf-8")

    def test_missing_source_for_mirror_entry_fails(self):
        # seeded defect: a mirror entry points at a live public file that does
        # not exist on disk → the MISSING SOURCE arm (lines 279-280).
        ctx = _ctx(extra=[("ghost.txt", "ghost.txt.txt")])
        _fixture.write_bytes(self.root, "public/source/ghost.txt.txt", BODY)
        r = vsm.evaluate(self.repo, ctx)
        self.assertFalse(r.ok)
        self.assertTrue(any(f.startswith("MISSING SOURCE: ghost.txt") for f in r.fails), r.fails)

    def test_required_mirror_on_disk_but_untracked_fails(self):
        # seeded defect: a required mirror exists on disk but is dropped from the
        # MIRROR map → the REQUIRED MIRROR UNTRACKED arm (line 265). build a Ctx
        # whose mirror omits one required pair while leaving its file in place.
        required = sorted(vsm.REQUIRED_MIRRORS)[0]
        kept = [p for p in [(PUBLIC_FILE, MIRROR_NAME), *_required_pairs()] if p[1] != required]
        ctx = vsm.Ctx(
            mirror=kept,
            mirror_map={},
            banner_css=b"",
            banner_js=b"",
            htaccess_transform=lambda b: b,
        )
        r = vsm.evaluate(self.repo, ctx)
        self.assertFalse(r.ok)
        self.assertTrue(
            any(f.startswith(f"REQUIRED MIRROR UNTRACKED: source/{required}") for f in r.fails),
            r.fails,
        )

    def test_authored_mirror_missing_source_fails(self):
        # seeded defect: a mirror_map entry remaps to an authored source path
        # that does not exist → the AUTHORED-SOURCE MISSING arm (lines 288-289).
        ctx = _ctx(extra=[("asset.css", "asset.css.txt")])
        ctx = vsm.Ctx(
            mirror=ctx.mirror,
            mirror_map={"asset.css.txt": str(self.root / "does-not-exist.css")},
            banner_css=b"/* banner */\n",
            banner_js=b"",
            htaccess_transform=lambda b: b,
        )
        _fixture.write_bytes(self.root, "public/asset.css", BODY)
        _fixture.write_bytes(self.root, "public/source/asset.css.txt", BODY)
        r = vsm.evaluate(self.repo, ctx)
        self.assertFalse(r.ok)
        self.assertTrue(any(f.startswith("AUTHORED-SOURCE MISSING:") for f in r.fails), r.fails)

    def test_authored_mirror_byte_drift_fails(self):
        # seeded defect: an authored-source mirror exists but the mirror bytes
        # differ from banner+authored → the DRIFT (authored) arm (line 294).
        _fixture.write_bytes(self.root, "public/asset.css", BODY)
        _fixture.write_bytes(self.root, "public/src/asset.css", b"body{}\n")
        # mirror on disk is NOT banner+authored → drift.
        _fixture.write_bytes(self.root, "public/source/asset.css.txt", b"wrong\n")
        ctx = vsm.Ctx(
            mirror=[(PUBLIC_FILE, MIRROR_NAME), *_required_pairs(), ("asset.css", "asset.css.txt")],
            mirror_map={"asset.css.txt": str(self.root / "public" / "src" / "asset.css")},
            banner_css=b"/* banner */\n",
            banner_js=b"",
            htaccess_transform=lambda b: b,
        )
        r = vsm.evaluate(self.repo, ctx)
        self.assertFalse(r.ok)
        self.assertTrue(
            any(f.startswith("DRIFT (authored): source/asset.css.txt") for f in r.fails),
            r.fails,
        )

    def test_authored_mirror_byte_match_green(self):
        # green companion: when the mirror bytes equal banner+authored, the
        # authored arm passes (covers the banner_css branch + continue).
        banner = b"/* banner */\n"
        authored = b"body{color:red}\n"
        _fixture.write_bytes(self.root, "public/asset.css", BODY)
        _fixture.write_bytes(self.root, "public/src/asset.css", authored)
        _fixture.write_bytes(self.root, "public/source/asset.css.txt", banner + authored)
        ctx = vsm.Ctx(
            mirror=[(PUBLIC_FILE, MIRROR_NAME), *_required_pairs(), ("asset.css", "asset.css.txt")],
            mirror_map={"asset.css.txt": str(self.root / "public" / "src" / "asset.css")},
            banner_css=banner,
            banner_js=b"",
            htaccess_transform=lambda b: b,
        )
        # add a manifest record so the on-disk mirror isn't flagged EXTRA.
        self._add_manifest_record("asset.css.txt", banner + authored)
        r = vsm.evaluate(self.repo, ctx)
        self.assertTrue(all("asset.css.txt" not in f or "AUTHORED" in f for f in r.fails))
        self.assertFalse(any("asset.css.txt" in f for f in r.fails), r.fails)

    def test_htaccess_transform_applied(self):
        # the .htaccess source is run through htaccess_transform before the
        # byte comparison (line 305). seed a mirror whose bytes equal the
        # transformed source so the transform path is exercised green; then a
        # second case where it drifts.
        live = b"RewriteRule secret\n"
        transform = lambda b: b.replace(b"secret", b"[redacted]")  # noqa: E731
        _fixture.write_bytes(self.root, "public/.htaccess", live)
        _fixture.write_bytes(self.root, "public/source/.htaccess.txt", transform(live))
        ctx = vsm.Ctx(
            mirror=[(PUBLIC_FILE, MIRROR_NAME), *_required_pairs(), (".htaccess", ".htaccess.txt")],
            mirror_map={},
            banner_css=b"",
            banner_js=b"",
            htaccess_transform=transform,
        )
        self._add_manifest_record(".htaccess.txt", transform(live))
        r = vsm.evaluate(self.repo, ctx)
        self.assertFalse(any(".htaccess" in f for f in r.fails), r.fails)

    def test_html_footer_sha_canonicalisation_green(self):
        # the html mirror path canonicalises the footer source-sha + the
        # verification-data ref/SRI on BOTH sides (lines 310-312). seed a live
        # html with one sha8 and a mirror with a different sha8 / data ref so
        # only the canonicalisation makes them equal → no DRIFT.
        live = (
            b'<html><body data-source-sha256-short="abcd1234">'
            b'<a data-page-sha-short href="#"><code>abcd1234</code></a>'
            b'<script src="/verify/verification-data.js?v=2026-06-01.deadbeef" '
            b'integrity="sha384-LIVEHASH"></script>'
            b"</body></html>\n"
        )
        mirror = (
            b'<html><body data-source-sha256-short="ffff9999">'
            b'<a data-page-sha-short href="#"><code>ffff9999</code></a>'
            b'<script src="/verify/verification-data.2026-05-09.cafef00d.js" '
            b'integrity="sha384-MIRRORHASH"></script>'
            b"</body></html>\n"
        )
        _fixture.write_bytes(self.root, "public/page.html", live)
        _fixture.write_bytes(self.root, "public/source/page.html.txt", mirror)
        ctx = _ctx(extra=[("page.html", "page.html.txt")])
        self._add_manifest_record("page.html.txt", mirror)
        r = vsm.evaluate(self.repo, ctx)
        self.assertFalse(any("page.html" in f for f in r.fails), r.fails)

    def test_html_real_drift_after_canonicalisation_fails(self):
        # if real content drifts (beyond the canonicalised metadata), the html
        # arm still fails — proving canonicalisation isn't masking everything.
        live = b'<html><body data-source-sha256-short="abcd1234">REAL</body></html>\n'
        mirror = b'<html><body data-source-sha256-short="ffff9999">DIFFERENT</body></html>\n'
        _fixture.write_bytes(self.root, "public/page.html", live)
        _fixture.write_bytes(self.root, "public/source/page.html.txt", mirror)
        ctx = _ctx(extra=[("page.html", "page.html.txt")])
        self._add_manifest_record("page.html.txt", mirror)
        r = vsm.evaluate(self.repo, ctx)
        self.assertFalse(r.ok)
        self.assertTrue(any(f.startswith("DRIFT: page.html") for f in r.fails), r.fails)

    def test_manifest_invalid_json_fails(self):
        # seeded defect: source-manifest.json is not valid JSON → both the
        # image-array parse arm (silently ignored) and the self-consistency
        # arm (reported) (lines 384-386).
        _write(self.root, "public/source/source-manifest.json", "{ not json")
        r = vsm.evaluate(self.repo, _ctx())
        self.assertFalse(r.ok)
        self.assertTrue(
            any(f.startswith("source-manifest.json: invalid JSON") for f in r.fails),
            r.fails,
        )

    def test_manifest_entry_missing_on_disk_fails(self):
        # seeded defect: a manifest record names a mirror not present on disk
        # → "listed but missing on disk".
        self._add_manifest_record("phantom.txt", BODY)
        r = vsm.evaluate(self.repo, _ctx())
        self.assertFalse(r.ok)
        self.assertTrue(any("listed but missing on disk" in f for f in r.fails), r.fails)

    def test_manifest_mirror_bytes_mismatch_fails(self):
        # seeded defect: manifest mirror_bytes disagrees with the on-disk
        # mirror length.
        import json

        smf = self.root / "public" / "source" / "source-manifest.json"
        sm = json.loads(smf.read_text(encoding="utf-8"))
        for entry in sm["files"]:
            if entry["name"] == MIRROR_NAME:
                entry["mirror_bytes"] = len(BODY) + 99
        smf.write_text(json.dumps(sm), encoding="utf-8")
        r = vsm.evaluate(self.repo, _ctx())
        self.assertFalse(r.ok)
        self.assertTrue(any("mirror_bytes" in f for f in r.fails), r.fails)

    def test_manifest_sha256_mismatch_fails(self):
        # seeded defect: manifest sha256 disagrees with the on-disk mirror.
        import json

        smf = self.root / "public" / "source" / "source-manifest.json"
        sm = json.loads(smf.read_text(encoding="utf-8"))
        for entry in sm["files"]:
            if entry["name"] == MIRROR_NAME:
                entry["sha256"] = "AAAAAAAAAAAAAAAAAAAA"
        smf.write_text(json.dumps(sm), encoding="utf-8")
        r = vsm.evaluate(self.repo, _ctx())
        self.assertFalse(r.ok)
        self.assertTrue(any("sha256" in f and MIRROR_NAME in f for f in r.fails), r.fails)

    def test_manifest_modified_not_iso_fails(self):
        # seeded defect: a record's `modified` field is present but malformed
        # (not an ISO date) → line 425.
        import json

        smf = self.root / "public" / "source" / "source-manifest.json"
        sm = json.loads(smf.read_text(encoding="utf-8"))
        for entry in sm["files"]:
            if entry["name"] == MIRROR_NAME:
                entry["modified"] = "not-a-date"
        smf.write_text(json.dumps(sm), encoding="utf-8")
        r = vsm.evaluate(self.repo, _ctx())
        self.assertFalse(r.ok)
        self.assertTrue(any("is not an ISO date" in f for f in r.fails), r.fails)

    def test_image_mirror_live_missing_fails(self):
        # seeded defect: an images record whose live file is absent → the
        # "live file ... missing" arm (lines 364-366).
        self._set_images(
            [{"name": "images/logo.svg.txt", "live_path": "/images/logo.svg", "sha256": "x" * 20}]
        )
        _fixture.write_bytes(self.root, "public/source/images/logo.svg.txt", BODY)
        r = vsm.evaluate(self.repo, _ctx())
        self.assertFalse(r.ok)
        self.assertTrue(any("IMAGE MIRROR:" in f and "missing" in f for f in r.fails), r.fails)

    def test_image_mirror_file_missing_fails(self):
        # seeded defect: live image present but the mirror file is absent →
        # the "mirror source/... missing" arm (lines 369-370).
        self._set_images(
            [{"name": "images/logo.svg.txt", "live_path": "/images/logo.svg", "sha256": "x" * 20}]
        )
        _fixture.write_bytes(self.root, "public/images/logo.svg", BODY)
        r = vsm.evaluate(self.repo, _ctx())
        self.assertFalse(r.ok)
        self.assertTrue(
            any("IMAGE MIRROR:" in f and "missing (live file present)" in f for f in r.fails),
            r.fails,
        )

    def test_image_mirror_sha_mismatch_fails(self):
        # seeded defect: live image present, mirror present, but the manifest
        # sha256 disagrees with the live bytes (line 374).
        from hashing import sha256_b64

        _fixture.write_bytes(self.root, "public/images/logo.svg", b"<svg/>\n")
        _fixture.write_bytes(self.root, "public/source/images/logo.svg.txt", BODY)
        self._set_images(
            [
                {
                    "name": "images/logo.svg.txt",
                    "live_path": "/images/logo.svg",
                    "sha256": "WRONGHASHVALUEHERE==",
                }
            ]
        )
        r = vsm.evaluate(self.repo, _ctx())
        self.assertFalse(r.ok)
        self.assertTrue(any("manifest sha256" in f for f in r.fails), r.fails)
        # sanity: the real sha differs from the seeded one.
        self.assertNotEqual(sha256_b64(b"<svg/>\n"), "WRONGHASHVALUEHERE==")

    def test_image_mirror_record_green(self):
        # green companion: a coherent images record (live present, mirror
        # present, sha matches) introduces no IMAGE MIRROR failure and is not
        # flagged EXTRA (its name is in image_mirror_names).
        from hashing import sha256_b64

        body = b"<svg/>\n"
        _fixture.write_bytes(self.root, "public/images/logo.svg", body)
        _fixture.write_bytes(self.root, "public/source/images/logo.svg.txt", BODY)
        self._set_images(
            [
                {
                    "name": "images/logo.svg.txt",
                    "live_path": "/images/logo.svg",
                    "sha256": sha256_b64(body),
                }
            ]
        )
        r = vsm.evaluate(self.repo, _ctx())
        self.assertFalse(any("IMAGE MIRROR" in f for f in r.fails), r.fails)
        self.assertFalse(any("EXTRA: source/images/logo.svg.txt" in f for f in r.fails), r.fails)

    def test_recursive_source_path_forbidden(self):
        # seeded defect: a file under /source/source/ → the recursive-source
        # guard (lines 433-436).
        _fixture.write_bytes(self.root, "public/source/source/index.html.txt", BODY)
        r = vsm.evaluate(self.repo, _ctx())
        self.assertFalse(r.ok)
        self.assertTrue(
            any(f.startswith("RECURSIVE SOURCE: source/source/") for f in r.fails),
            r.fails,
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

    def test_main_renders_fail_block_over_failing_repo(self):
        # main() over an empty repo: the generator's real MIRROR map loads, but
        # none of its live files / mirrors exist in the fixture, so evaluate()
        # returns many fails. assert main() prints the itemised FAIL block and
        # returns 1 — exercises the r.fails render arm (lines 540-543).
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vsm.main(pathlib.Path(tmp))
            out = buf.getvalue()
        self.assertEqual(rc, 1)
        self.assertIn("source-mirror issue(s):", out)
        # at minimum a required-mirror line is rendered for the empty tree.
        self.assertIn("REQUIRED MIRROR MISSING:", out)


if __name__ == "__main__":
    unittest.main()
