#!/usr/bin/env python3
"""Tests for the no-mutation-after-seal guard (tools/build/assert_seal_immutable.py).

The pure compare (moved_paths) is checked directly; the record->verify cycle is
exercised over a tiny fixture public/ tree.

Run:
    python3 -m unittest discover -s tools/quality/tests
"""

import unittest

import _fixture

_fixture.bootstrap()

import assert_seal_immutable as asi  # noqa: E402


class MovedPaths(unittest.TestCase):
    def test_identical_snapshots_no_move(self):
        a = {"index.html": "h1", "styles.css": "h2"}
        self.assertEqual(asi.moved_paths(a, dict(a)), [])

    def test_content_change_detected(self):
        a = {"index.html": "h1"}
        b = {"index.html": "DIFFERENT"}
        self.assertEqual(asi.moved_paths(a, b), ["index.html"])

    def test_added_and_removed_detected(self):
        sealed = {"a": "1", "b": "2"}
        current = {"a": "1", "c": "3"}  # b removed, c added
        self.assertEqual(asi.moved_paths(sealed, current), ["b", "c"])


class RecordVerifyCycle(unittest.TestCase):
    def setUp(self):
        import pathlib
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _fixture.write(self.root, "public/index.html", "<html>sealed</html>")
        _fixture.write(self.root, "public/styles.css", "body{}")

    def tearDown(self):
        self._tmp.cleanup()

    def test_record_then_verify_clean(self):
        self.assertEqual(asi.record(self.root), 0)
        self.assertEqual(asi.verify(self.root), 0)

    def test_verify_fails_when_a_file_mutates_after_seal(self):
        asi.record(self.root)
        _fixture.write(self.root, "public/index.html", "<html>TAMPERED</html>")
        self.assertEqual(asi.verify(self.root), 1)

    def test_verify_fails_when_a_file_appears_after_seal(self):
        asi.record(self.root)
        _fixture.write(self.root, "public/sneaky.js", "alert(1)")
        self.assertEqual(asi.verify(self.root), 1)

    def test_verify_without_record_fails(self):
        # this fixture root has no recorded snapshot under its own .build/ -> fail.
        self.assertFalse(asi._snapshot_path(self.root).exists())
        self.assertEqual(asi.verify(self.root), 1)

    def test_verify_reports_a_removed_file(self):
        asi.record(self.root)
        (self.root / "public/styles.css").unlink()  # sealed has it, now gone
        self.assertEqual(asi.verify(self.root), 1)

    def test_main_record_then_verify_dispatch(self):
        # exercises the argparse dispatch (both subcommands) through main().
        self.assertEqual(asi.main(["--record"], repo_root=self.root), 0)
        self.assertEqual(asi.main(["--verify"], repo_root=self.root), 0)


class SnapshotTree(unittest.TestCase):
    def test_hashes_every_file_and_is_stable(self):
        import pathlib
        import tempfile

        import public_tree

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _fixture.write(root, "a.html", "x")
            _fixture.write(root, "sub/b.css", "y")
            snap = public_tree.snapshot_tree(root)
            self.assertEqual(set(snap), {"a.html", "sub/b.css"})
            self.assertEqual(snap, public_tree.snapshot_tree(root))  # deterministic
            _fixture.write(root, "a.html", "CHANGED")
            self.assertNotEqual(public_tree.snapshot_tree(root)["a.html"], snap["a.html"])


if __name__ == "__main__":
    unittest.main()
