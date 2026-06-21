#!/usr/bin/env python3
"""Tests for the asset-version coherence gate
(tools/quality/validate_asset_version.py).

Two seams crossed: `evaluate(Repo, recomputed)` takes the recomputed version as
input so the coherence logic is tested on a tiny fixture, and
`recompute_asset_version(Repo)` is tested directly with a minimal generate_site.py.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import hashlib
import json
import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
for _sub in ("lib", "build", "quality", "verify"):
    sys.path.insert(0, str(TOOLS / _sub))

import validate_asset_version as va  # noqa: E402

REPO_ROOT = TOOLS.parent
AV = "2026-06-14.deadbeef"


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = va.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _seed_coherent(self):
        _write(self.root, va.SITE_METADATA_REL, json.dumps({"asset_version": AV}))
        _write(self.root, va.SW_REL, f"const CACHE='{AV}';\n")
        # index.html references every swept asset with ?v=AV.
        refs = "".join(f'<link href="{a}?v={AV}">' for a in va.SWEPT_ASSETS)
        _write(self.root, "public/index.html", refs)
        for rel in va.active_html_for_av():
            if rel != "index.html":
                _write(self.root, f"public/{rel}", "<html></html>")

    def test_coherent_green(self):
        self._seed_coherent()
        r = va.evaluate(self.repo, AV)  # injected recomputed == av
        self.assertTrue(r.ok, msg=r.fails)
        self.assertEqual(r.av, AV)

    def test_recompute_drift_fails(self):
        self._seed_coherent()
        r = va.evaluate(self.repo, "2026-06-14.00000000")  # differs from av
        self.assertFalse(r.ok)
        self.assertTrue(any("does not match disk-derived" in f for f in r.fails), r.fails)

    def test_recompute_none_fails(self):
        self._seed_coherent()
        r = va.evaluate(self.repo, None)
        self.assertFalse(r.ok)
        self.assertTrue(any("cannot recompute" in f for f in r.fails), r.fails)

    def test_sw_missing_av_fails(self):
        self._seed_coherent()
        _write(self.root, va.SW_REL, "const CACHE='other';\n")
        r = va.evaluate(self.repo, AV)
        self.assertFalse(r.ok)
        self.assertTrue(any("sw.js: cache name" in f for f in r.fails), r.fails)

    def test_missing_qv_fails(self):
        self._seed_coherent()
        _write(self.root, "public/index.html", '<link href="/styles.css">')
        r = va.evaluate(self.repo, AV)
        self.assertFalse(r.ok)
        self.assertTrue(any("missing ?v=" in f for f in r.fails), r.fails)

    def test_wrong_qv_fails(self):
        self._seed_coherent()
        _write(self.root, "public/index.html", '<link href="/styles.css?v=stale">')
        r = va.evaluate(self.repo, AV)
        self.assertFalse(r.ok)
        self.assertTrue(any("expected" in f for f in r.fails), r.fails)

    def test_site_metadata_missing(self):
        r = va.evaluate(self.repo, AV)
        self.assertTrue(r.sm_missing)

    def test_no_asset_version(self):
        _write(self.root, va.SITE_METADATA_REL, json.dumps({}))
        r = va.evaluate(self.repo, AV)
        self.assertTrue(r.no_av)


class Recompute(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = va.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_recompute_matches_hand_computed(self):
        edition = "2026-06-14"
        body = b"body{color:#000}\n"
        _write(self.root, "public/styles.css", body.decode())
        _write(
            self.root,
            "tools/build/generate_site.py",
            'ASSET_BUNDLE = ["styles.css"]\nprint("noise")\n',
        )
        _write(self.root, "tools/config/identity_canonical.json", json.dumps({"edition": edition}))
        h = hashlib.sha256()
        h.update(b"styles.css")
        h.update(b"\0")
        h.update(hashlib.sha256(body).digest())
        expected = f"{edition}.{h.hexdigest()[:8]}"
        self.assertEqual(va.recompute_asset_version(self.repo), expected)

    def test_recompute_none_when_generator_absent(self):
        self.assertIsNone(va.recompute_asset_version(self.repo))


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = va.main(REPO_ROOT)
        self.assertEqual(rc, 0, msg=buf.getvalue())


if __name__ == "__main__":
    unittest.main()
