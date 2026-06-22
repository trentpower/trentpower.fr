#!/usr/bin/env python3
"""Tests for tools/quality/doctor.py — environment diagnosis.

The classification is the tested core: every scenario builds a fixture Repo
(tempdir) and injects a FakeEnv / FakeProc, so the whole compute path runs with
no real git / gpg / node / importlib and no host dependence. The renderer
(doctor.sh) is exercised separately and lightly in test_doctor_render.py.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import _fixture

_fixture.bootstrap()

import doctor as d  # noqa: E402
from repo import Repo  # noqa: E402

# the real fonts manifest names; a tiny valid stand-in keeps tests self-contained.
_FONTS = ["public/fonts/a.woff2", "public/fonts/b.woff2"]
_MANIFEST = (
    '{"restore": "tools/build/fetch_licensed_fonts.py",'
    ' "files": [{"path": "public/fonts/a.woff2"}, {"path": "public/fonts/b.woff2"}]}'
)


def _full_env():
    return _fixture.FakeEnv(
        which={
            "git": "/usr/bin/git",
            "node": "/usr/bin/node",
            "npm": "/usr/bin/npm",
            "gpg": "/usr/bin/gpg",
        },
        modules={"jsonschema", "yaml", "hypothesis"},
        py="3.11.7",
    )


def _in_work_tree(rc=0):
    return _fixture.FakeProc(lambda argv, cwd, env: _fixture.proc_result(rc))


class DoctorBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def repo(self):
        return Repo(self.root)

    def w(self, rel, text=""):
        _fixture.write(self.root, rel, text)

    def mkdir(self, rel):
        (self.root / rel).mkdir(parents=True, exist_ok=True)

    def scaffold_full(self):
        """A tree that should classify `full`."""
        self.w("Makefile")
        self.w("tools/lib/paths.py")
        self.mkdir(".git")
        self.w("metadata/repo-exclusions.json", _MANIFEST)
        for f in _FONTS:  # fonts present
            self.w(f, "x")
        self.mkdir("node_modules")
        self.w(d.PGP_KEY, "KEY")

    def find(self, name):
        return next(c for c in self.report.checks if c.name == name)


class FullMode(DoctorBase):
    def test_everything_present_is_full(self):
        self.scaffold_full()
        self.report = d.evaluate(self.repo(), _in_work_tree(0), _full_env())
        self.assertEqual(self.report.mode, "full")
        self.assertTrue(self.report.full_checks_available)
        self.assertTrue(self.report.archive_checks_available)
        self.assertEqual(self.report.recommended_next, "make test")
        self.assertEqual(self.find("Klim fonts").status, "present")
        self.assertEqual(self.find("signature verification").status, "plausible")


class PartialMode(DoctorBase):
    def test_missing_one_piece_is_partial(self):
        # gpg binary absent — everything else present.
        self.scaffold_full()
        env = _fixture.FakeEnv(
            which={
                "git": "/usr/bin/git",
                "node": "/usr/bin/node",
                "npm": "/usr/bin/npm",
                "gpg": None,
            },
            modules={"jsonschema", "yaml", "hypothesis"},
        )
        self.report = d.evaluate(self.repo(), _in_work_tree(0), env)
        self.assertEqual(self.report.mode, "partial")
        self.assertFalse(self.report.full_checks_available)

    def test_missing_gpg_check(self):
        self.scaffold_full()
        env = _full_env()
        env._which["gpg"] = None
        self.report = d.evaluate(self.repo(), _in_work_tree(0), env)
        self.assertEqual(self.find("gpg binary").status, "missing")
        self.assertEqual(self.find("signature verification").status, "unavailable")

    def test_missing_hypothesis_is_partial(self):
        self.scaffold_full()
        env = _fixture.FakeEnv(
            which={
                "git": "/usr/bin/git",
                "node": "/usr/bin/node",
                "npm": "/usr/bin/npm",
                "gpg": "/usr/bin/gpg",
            },
            modules={"jsonschema", "yaml"},  # no hypothesis
        )
        self.report = d.evaluate(self.repo(), _in_work_tree(0), env)
        self.assertEqual(self.report.mode, "partial")
        self.assertEqual(self.find("hypothesis").status, "missing")
        self.assertIn(d.PY_DEPS_INSTALL, self.report.next_actions)

    def test_missing_node_modules_is_partial(self):
        self.scaffold_full()
        # remove node_modules dir
        (self.root / "node_modules").rmdir()
        self.report = d.evaluate(self.repo(), _in_work_tree(0), _full_env())
        self.assertEqual(self.report.mode, "partial")
        self.assertEqual(self.find("node_modules").status, "missing")
        self.assertIn("npm install", self.report.next_actions)

    def test_missing_fonts_is_partial_with_restore(self):
        self.w("Makefile")
        self.w("tools/lib/paths.py")
        self.mkdir(".git")
        self.w("metadata/repo-exclusions.json", _MANIFEST)
        # fonts NOT written
        self.mkdir("node_modules")
        self.w(d.PGP_KEY, "KEY")
        self.report = d.evaluate(self.repo(), _in_work_tree(0), _full_env())
        self.assertEqual(self.report.mode, "partial")
        self.assertEqual(self.find("Klim fonts").status, "missing")
        restore = "python3 tools/build/fetch_licensed_fonts.py"
        self.assertIn(restore, self.report.next_actions)
        self.assertEqual(self.report.recommended_next, f"{restore}, then make gate")

    def test_partial_fonts_status(self):
        self.scaffold_full()
        (self.root / _FONTS[0]).unlink()  # one of two fonts gone
        self.report = d.evaluate(self.repo(), _in_work_tree(0), _full_env())
        self.assertEqual(self.find("Klim fonts").status, "partial")
        self.assertEqual(self.report.mode, "partial")


class ArchiveMode(DoctorBase):
    def test_no_git_metadata_is_archive(self):
        self.w("Makefile")
        self.w("tools/lib/paths.py")
        # no .git, rev-parse fails
        self.w("metadata/repo-exclusions.json", _MANIFEST)
        for f in _FONTS:
            self.w(f, "x")
        self.mkdir("node_modules")
        self.w(d.PGP_KEY, "KEY")
        self.report = d.evaluate(self.repo(), _in_work_tree(1), _full_env())
        self.assertEqual(self.report.mode, "archive")
        self.assertFalse(self.report.full_checks_available)
        # git-dependent validators named as unavailable
        gd = self.find("git-dependent gates")
        self.assertEqual(gd.status, "n/a")
        for v in d.GIT_DEPENDENT_VALIDATORS:
            self.assertIn(v, gd.detail)
        # archive-safe Python validators still available (jsonschema/yaml present)
        self.assertTrue(self.report.archive_checks_available)


class SotUnavailable(DoctorBase):
    def test_malformed_manifest_does_not_crash(self):
        self.w("Makefile")
        self.w("tools/lib/paths.py")
        self.mkdir(".git")
        self.w("metadata/repo-exclusions.json", "{ this is not json")
        self.mkdir("node_modules")
        self.w(d.PGP_KEY, "KEY")
        self.report = d.evaluate(self.repo(), _in_work_tree(0), _full_env())
        self.assertEqual(self.find("font source of truth").status, "sot-unavailable")
        self.assertEqual(self.report.mode, "partial")  # fonts can't be proven

    def test_absent_manifest_is_sot_unavailable(self):
        self.w("Makefile")
        self.w("tools/lib/paths.py")
        self.mkdir(".git")
        self.mkdir("node_modules")
        self.w(d.PGP_KEY, "KEY")
        self.report = d.evaluate(self.repo(), _in_work_tree(0), _full_env())
        self.assertEqual(self.find("font source of truth").status, "sot-unavailable")


class BlockedMode(DoctorBase):
    def test_no_repo_markers_is_blocked(self):
        # empty tree — cannot identify the repo
        self.report = d.evaluate(self.repo(), _in_work_tree(1), _full_env())
        self.assertEqual(self.report.mode, "blocked")


class MainInjected(DoctorBase):
    """main() driven over fixture seams — no real repo / git / gpg / PATH."""

    def _run(self, argv, repo, proc, env):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = d.main(argv, repo=repo, proc=proc, env=env)
        return rc, buf.getvalue()

    def test_main_json_full_exit_zero(self):
        self.scaffold_full()
        rc, out = self._run(["--json"], self.repo(), _in_work_tree(0), _full_env())
        self.assertEqual(rc, 0)
        import json

        self.assertEqual(json.loads(out)["mode"], "full")

    def test_main_plain_fallback(self):
        self.scaffold_full()
        rc, out = self._run([], self.repo(), _in_work_tree(0), _full_env())
        self.assertEqual(rc, 0)
        self.assertIn("mode: full", out)
        self.assertIn("recommended next:", out)

    def test_main_blocked_exit_one(self):
        # empty tmp tree → no repo markers → blocked → exit 1
        rc, out = self._run([], self.repo(), _in_work_tree(1), _full_env())
        self.assertEqual(rc, 1)
        self.assertIn("mode: blocked", out)


class EnvSeam(unittest.TestCase):
    """FakeEnv shape mirrors the real Env contract."""

    def test_fake_env_returns_as_configured(self):
        env = _fixture.FakeEnv(
            which={"git": "/usr/bin/git", "gpg": None},
            modules={"yaml"},
            py="3.12.1",
        )
        self.assertEqual(env.which("git"), "/usr/bin/git")
        self.assertIsNone(env.which("gpg"))
        self.assertIsNone(env.which("absent"))
        self.assertTrue(env.has_module("yaml"))
        self.assertFalse(env.has_module("jsonschema"))
        self.assertEqual(env.python_version(), "3.12.1")

    def test_real_env_shape(self):
        from env import Env

        e = Env()
        self.assertTrue(e.has_module("json"))
        self.assertFalse(e.has_module("a_module_that_does_not_exist_xyz"))
        self.assertIsInstance(e.python_version(), str)

    def test_real_env_which(self):
        from env import Env

        e = Env()
        # python3 is on PATH in any environment that can run this test.
        self.assertIsNotNone(e.which("python3"))
        self.assertIsNone(e.which("a_binary_that_does_not_exist_xyz"))

    def test_real_env_has_module_swallows_probe_errors(self):
        from env import Env

        e = Env()
        # find_spec raises (not returns None) for a dotted name whose parent is
        # absent and for a relative name; the seam must swallow it and report
        # not-importable rather than propagate the ImportError.
        self.assertFalse(e.has_module("nonexistent_parent_xyz.child"))
        self.assertFalse(e.has_module(".rel"))


if __name__ == "__main__":
    unittest.main()
