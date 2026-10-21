import tempfile
import unittest
from pathlib import Path
from unittest import mock

import probe_dirs
from testutil import write_file


class TrashTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name) / "home"
        (self.home / ".Trash").mkdir(parents=True)
        self.run_dir = Path(tmp.name) / "audio-title"
        self.run_dir.mkdir()
        write_file(self.run_dir, "stdout.txt", "x")

    def trash(self) -> None:
        with (mock.patch.object(probe_dirs.Path, "home", return_value=self.home),
              mock.patch.object(probe_dirs.time, "strftime", return_value="20261021-120000")):
            probe_dirs.trash(self.run_dir)

    def test_moves_the_directory_into_the_trash_under_a_time_stamped_name(self):
        self.trash()
        self.assertFalse(self.run_dir.exists())
        moved = self.home / ".Trash" / "audio-title-20261021-120000"
        self.assertEqual((moved / "stdout.txt").read_text(), "x")


if __name__ == "__main__":
    unittest.main()
