from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import clone_file


def failing_clonefile(src: bytes, dst: bytes, flags: int) -> int:
    return -1


class CloneTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="clone test ")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.src = self.tmp / "a mod file é.bin"
        self.src.write_bytes(bytes(range(256)) * 9)
        self.dst = self.tmp / "the build's copy.bin"

    def test_a_clone_holds_the_same_bytes(self) -> None:
        self.assertTrue(clone_file.clone(self.src, self.dst))
        self.assertEqual(self.dst.read_bytes(), self.src.read_bytes())

    def test_a_clone_keeps_its_bytes_when_the_original_changes(self) -> None:
        before = self.src.read_bytes()
        clone_file.clone(self.src, self.dst)
        with open(self.src, "r+b") as f:
            f.write(b"edited")
        self.assertEqual(self.dst.read_bytes(), before)

    def test_a_clone_that_fails_falls_back_to_a_copy(self) -> None:
        with mock.patch.object(clone_file, "CLONEFILE", failing_clonefile):
            self.assertFalse(clone_file.clone(self.src, self.dst))
        self.assertEqual(self.dst.read_bytes(), self.src.read_bytes())

    def test_with_no_clonefile_the_bytes_are_copied(self) -> None:
        with mock.patch.object(clone_file, "CLONEFILE", None):
            self.assertFalse(clone_file.clone(self.src, self.dst))
        self.assertEqual(self.dst.read_bytes(), self.src.read_bytes())

    def test_a_copy_of_more_than_one_chunk_is_whole(self) -> None:
        self.src.write_bytes(bytes(range(251)) * (2 * clone_file.CHUNK // 251 + 7))
        with mock.patch.object(clone_file, "CLONEFILE", failing_clonefile):
            clone_file.clone(self.src, self.dst)
        self.assertEqual(self.dst.read_bytes(), self.src.read_bytes())

    def test_a_destination_that_exists_is_refused_and_left_alone(self) -> None:
        for clonefile in (clone_file.CLONEFILE, failing_clonefile):
            with self.subTest(clonefile=clonefile), \
                    mock.patch.object(clone_file, "CLONEFILE", clonefile):
                self.dst.write_bytes(b"old")
                with self.assertRaises(FileExistsError):
                    clone_file.clone(self.src, self.dst)
                self.assertEqual(self.dst.read_bytes(), b"old")

    def test_a_missing_source_is_an_error(self) -> None:
        with self.assertRaises(FileNotFoundError):
            clone_file.clone(self.tmp / "gone.bin", self.dst)
        self.assertFalse(self.dst.exists())


if __name__ == "__main__":
    unittest.main()
