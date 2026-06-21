#!/usr/bin/env python3
"""Tests for the deny-extension parity gate
(tools/quality/validate_deny_parity.py).

Cross `evaluate(Repo)` over a fixture repo holding the two deny surfaces. The
validator AST-parses both files, so the fixture writes real Python source for
each — no monkeypatching; the fixture repo is the second filesystem adapter.
Tests assert on the returned Result, never on stdout.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[2]
import _fixture  # noqa: E402

_fixture.bootstrap()

import validate_deny_parity as vdp  # noqa: E402
from _fixture import write as _write  # noqa: E402

REPO_ROOT = TOOLS.parent


def _htaccess_source(exts: list[str]) -> str:
    """A minimal htaccess_config.py with a DENY_EXTENSION_RULES alternation
    over the given extensions (plus the out-of-scope template/credential rules,
    which the validator ignores)."""
    group = "|".join(exts)
    return (
        "DENY_EXTENSION_RULES = [\n"
        f'    r"\\.({group})$",\n'
        '    r"\\.template\\.js$",\n'
        '    r"(?i)(invoice|credential|password)|-key\\.txt$",\n'
        "]\n"
    )


def _manifest_source(exts: list[str]) -> str:
    """A minimal generate_public_exposure_manifest.py with a flat
    DENY_EXTENSION_PATTERNS suffix list over the given extensions."""
    body = "".join(f'    ".{e}",\n' for e in exts)
    return f"DENY_EXTENSION_PATTERNS = [\n{body}]\n"


def _make_fixture_repo(
    root: pathlib.Path,
    htaccess_exts: list[str],
    manifest_exts: list[str],
) -> None:
    _write(root, vdp.HTACCESS_CONFIG_REL, _htaccess_source(htaccess_exts))
    _write(root, vdp.EXPOSURE_MANIFEST_REL, _manifest_source(manifest_exts))


_EXTS = ["php", "phar", "env", "sql", "log"]


class Evaluate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = vdp.Repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_matching_deny_lists_are_green(self):
        _make_fixture_repo(self.root, _EXTS, list(_EXTS))
        r = vdp.evaluate(self.repo)
        self.assertTrue(r.ok, msg=r.fails)
        self.assertTrue(any("extensions agree across" in o for o in r.oks), r.oks)

    def test_mismatch_fails(self):
        # manifest is missing "log" — a real drift the gate must catch.
        _make_fixture_repo(self.root, _EXTS, ["php", "phar", "env", "sql"])
        r = vdp.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(any("two deny surfaces disagree" in f for f in r.fails), r.fails)
        self.assertTrue(
            any("denied by .htaccess but NOT by the manifest" in f for f in r.fails),
            r.fails,
        )

    def test_manifest_only_extension_fails(self):
        # the manifest denies "bak" but .htaccess does not — the reverse drift,
        # exercising the only_manifest reporting branch.
        _make_fixture_repo(self.root, _EXTS, [*_EXTS, "bak"])
        r = vdp.evaluate(self.repo)
        self.assertFalse(r.ok)
        self.assertTrue(
            any("denied by the manifest but NOT by .htaccess" in f for f in r.fails),
            r.fails,
        )
        self.assertTrue(any("bak" in f for f in r.fails), r.fails)

    def test_missing_deny_list_raises(self):
        # a fixture whose htaccess_config.py lacks DENY_EXTENSION_RULES makes the
        # AST lookup raise SystemExit naming the missing symbol.
        _write(self.root, vdp.HTACCESS_CONFIG_REL, "OTHER = []\n")
        _write(self.root, vdp.EXPOSURE_MANIFEST_REL, _manifest_source(_EXTS))
        with self.assertRaises(SystemExit) as ctx:
            vdp.evaluate(self.repo)
        self.assertIn("DENY_EXTENSION_RULES not found", str(ctx.exception))


class ExternalInterface(unittest.TestCase):
    def test_main_passes_against_the_real_repo(self):
        import contextlib
        import io

        buf = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = vdp.main(REPO_ROOT)
        # same RC as the recorded baseline (RC=0, green).
        self.assertEqual(rc, 0, msg=buf.getvalue() + err.getvalue())

    def test_main_fails_over_a_drifting_fixture(self):
        # main() points at a fixture repo whose two deny surfaces disagree; it
        # must return rc=1 and render the disagreement to stderr.
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture_repo(root, _EXTS, ["php", "phar", "env", "sql"])
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = vdp.main(root)

        self.assertEqual(rc, 1)
        out = err.getvalue()
        self.assertIn("FAIL", out)
        self.assertIn("two deny surfaces disagree", out)
        self.assertIn("log", out)


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
