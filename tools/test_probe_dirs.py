import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import probe_dirs
from testutil import write_file


class RemoveRunTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "home"
        (self.home / ".Trash").mkdir(parents=True)
        home = mock.patch.object(probe_dirs.Path, "home", return_value=self.home)
        home.start()
        self.addCleanup(home.stop)
        self.run_dir = self.root / "audio-title"
        (self.run_dir / "frames").mkdir(parents=True)
        write_file(self.run_dir, "stdout.txt", "x")
        write_file(self.run_dir / "frames", "frame_00060.png", b"png")
        self.outside = self.root / "outside"
        self.outside.mkdir()
        write_file(self.outside, "keep.txt", "keep")
        self.disc = write_file(self.root, "game.iso", b"disc")

    def everything_but_the_run(self) -> dict[str, object]:
        """Each path under the temp tree except the run directory's, with its bytes (None for a
        directory), and a link listed as the link it is."""
        seen: dict[str, object] = {}
        for path in sorted(self.root.rglob("*")):
            if path == self.run_dir or self.run_dir in path.parents:
                continue
            name = str(path.relative_to(self.root))
            if path.is_symlink():
                seen[name] = f"-> {path.readlink()}".encode()
            else:
                seen[name] = None if path.is_dir() else path.read_bytes()
        return seen

    def test_deletes_the_directory_and_its_files(self):
        probe_dirs.remove_run(self.run_dir)
        self.assertFalse(self.run_dir.exists())

    def test_does_not_move_the_directory_into_the_trash(self):
        probe_dirs.remove_run(self.run_dir)
        self.assertEqual(list((self.home / ".Trash").iterdir()), [])

    def test_leaves_nothing_beside_the_directory_changed(self):
        write_file(self.root, "audio-title.log", "log")
        (self.root / "audio-title-2").mkdir()
        write_file(self.root / "audio-title-2", "stdout.txt", "y")
        (self.root / "other-run").symlink_to(self.outside)
        before = self.everything_but_the_run()
        probe_dirs.remove_run(self.run_dir)
        self.assertEqual(self.everything_but_the_run(), before)

    def test_unlinks_a_link_to_a_directory_outside_and_keeps_its_target(self):
        (self.run_dir / "saves").symlink_to(self.outside)
        (self.run_dir / "frames" / "deeper").symlink_to(self.outside, target_is_directory=True)
        probe_dirs.remove_run(self.run_dir)
        self.assertFalse(self.run_dir.exists())
        self.assertEqual((self.outside / "keep.txt").read_text(), "keep")

    def test_unlinks_a_link_to_a_file_outside_and_keeps_its_target(self):
        (self.run_dir / "disc.iso").symlink_to(self.disc)
        (self.run_dir / "frames" / "disc.iso").symlink_to(self.disc)
        probe_dirs.remove_run(self.run_dir)
        self.assertFalse(self.run_dir.exists())
        self.assertEqual(self.disc.read_bytes(), b"disc")

    def test_unlinks_a_link_whose_target_is_gone(self):
        (self.run_dir / "stale").symlink_to(self.root / "nowhere")
        probe_dirs.remove_run(self.run_dir)
        self.assertFalse(self.run_dir.exists())

    def test_refuses_a_run_directory_that_is_a_link_and_changes_nothing(self):
        target = self.root / "real-run"
        (target / "frames").mkdir(parents=True)
        write_file(target / "frames", "frame_00060.png", b"png")
        for name, points_at in (("audio-dir", target), ("audio-file", self.disc),
                                ("audio-nothing", self.root / "nowhere")):
            with self.subTest(name):
                link = self.root / name
                link.symlink_to(points_at)
                before = self.everything_but_the_run()
                with self.assertRaisesRegex(ValueError, f"{name}: is a link"):
                    probe_dirs.remove_run(link)
                self.assertTrue(link.is_symlink())
                self.assertEqual(link.readlink(), points_at)
                self.assertEqual(self.everything_but_the_run(), before)
        self.assertEqual((target / "frames" / "frame_00060.png").read_bytes(), b"png")
        self.assertEqual(self.disc.read_bytes(), b"disc")

    def test_a_missing_directory_is_an_error_and_changes_nothing(self):
        before = self.everything_but_the_run()
        with self.assertRaises(FileNotFoundError):
            probe_dirs.remove_run(self.root / "audio-gone")
        self.assertEqual(self.everything_but_the_run(), before)

    @unittest.skipIf(os.geteuid() == 0, "root can remove what a mode forbids")
    def test_a_file_it_cannot_remove_is_an_error_and_not_skipped(self):
        frames = self.run_dir / "frames"
        frames.chmod(0o500)
        self.addCleanup(frames.chmod, 0o700)
        with self.assertRaises(PermissionError):
            probe_dirs.remove_run(self.run_dir)
        self.assertTrue((frames / "frame_00060.png").exists())


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
