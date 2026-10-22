import subprocess
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


class RunProbeTest(unittest.TestCase):
    def test_runs_the_command_line_from_the_directory_with_its_output_dropped(self):
        with mock.patch.object(subprocess, "run") as run:
            probe_dirs.run_probe(["probe.sh", "x", "5"], Path("/clone"), "x", {"A": "1"})
        run.assert_called_once_with(["probe.sh", "x", "5"], check=True, cwd=Path("/clone"),
                                    stdout=subprocess.DEVNULL, env={"A": "1"})

    def test_the_environment_is_the_callers_unless_one_is_given(self):
        with mock.patch.object(subprocess, "run") as run:
            probe_dirs.run_probe(["probe.sh"], Path("/clone"), "x")
        self.assertIsNone(run.call_args.kwargs["env"])

    def test_a_failed_run_is_an_error_that_starts_with_what_was_run(self):
        with (mock.patch.object(subprocess, "run", side_effect=subprocess.CalledProcessError(3, "probe")),
              self.assertRaisesRegex(ValueError, "^base title: probe.sh exited 3$")):
            probe_dirs.run_probe(["probe.sh"], Path("/clone"), "base title")


if __name__ == "__main__":
    unittest.main()
