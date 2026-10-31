from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

import warm_shaders
from testutil import write_file

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe.sh"
NAME = "test-probe-never-run"


def probe(*args: str, script: Path = PROBE, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([str(script), *args], capture_output=True, text=True, timeout=10, cwd=cwd)


class ProbeArgumentsTest(unittest.TestCase):
    def tearDown(self):
        self.assertFalse((ROOT / "build" / "probe" / NAME).exists())

    def test_help_exits_0_and_prints_usage(self):
        r = probe("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Usage:", r.stdout)
        self.assertIn("--disc=PATH", r.stdout)
        self.assertIn("--disc=fast|console", r.stdout)
        self.assertIn("--bin=PATH", r.stdout)
        self.assertTrue(r.stdout.endswith("under --bench) isn't built.\n"), r.stdout)
        self.assertNotIn("set -e", r.stdout)

    def test_no_arguments_exits_2(self):
        self.assertEqual(probe().returncode, 2)

    def test_seconds_must_be_a_whole_number(self):
        r = probe(NAME, "x")
        self.assertEqual(r.returncode, 2)
        self.assertIn("SECONDS", r.stderr)

    def test_scale_out_of_range_exits_2(self):
        r = probe(NAME, "1", "", "60", "--scale=10")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--scale=10", r.stderr)

    def test_empty_log_list_exits_2(self):
        r = probe(NAME, "1", "", "60", "--log=")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--log=", r.stderr)

    def test_empty_aspect_exits_2(self):
        r = probe(NAME, "1", "", "60", "--aspect=")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--aspect=", r.stderr)

    def test_empty_bin_exits_2(self):
        r = probe(NAME, "1", "", "60", "--bin=")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--bin=", r.stderr)


class ProbeTreeTest(unittest.TestCase):
    """probe.sh copied into a temp tree, so the game it runs is whatever the test puts in build/."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()  # as $PWD gives it
        (self.root / "tools").mkdir()
        self.script = self.root / "tools" / "probe.sh"
        shutil.copy(PROBE, self.script)
        (self.root / "build").mkdir()

    def add_game(self, name: str, body: str) -> None:
        game = write_file(self.root / "build", name, "#!/bin/sh\n" + body)
        game.chmod(game.stat().st_mode | stat.S_IXUSR)

    def test_missing_game_exits_2_before_making_a_run_directory(self):
        r = probe(NAME, "1", script=self.script)
        self.assertEqual(r.returncode, 2)
        self.assertIn("build/dragoon", r.stderr)
        self.assertFalse((self.root / "build" / "probe").exists())

    def test_missing_bench_exits_2_even_with_the_game_built(self):
        self.add_game("dragoon", "")
        r = probe(NAME, "1", "", "60", "--bench", script=self.script)
        self.assertEqual(r.returncode, 2)
        self.assertIn("build/dragoon_bench", r.stderr)
        self.assertFalse((self.root / "build" / "probe").exists())

    def test_log_with_bench_exits_2_before_making_a_run_directory(self):
        self.add_game("dragoon_bench", "echo 'whole run'\n")
        r = probe(NAME, "1", "", "60", "--log=dsp", "--bench", script=self.script)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--log", r.stderr)
        self.assertFalse((self.root / "build" / "probe").exists())

    def test_aspect_or_output_with_bench_exits_2_before_making_a_run_directory(self):
        self.add_game("dragoon_bench", "echo 'whole run'\n")
        for setting in ("--aspect=16:9", "--output"):
            r = probe(NAME, "1", "", "60", setting, "--bench", script=self.script)
            self.assertEqual(r.returncode, 2, setting)
            self.assertIn(setting, r.stderr)
            self.assertFalse((self.root / "build" / "probe").exists())

    def test_crashed_bench_with_no_report_exits_1(self):
        self.add_game("dragoon_bench", "exit 3\n")
        r = probe(NAME, "1", "", "60", "--bench", script=self.script)
        self.assertEqual(r.returncode, 1)

    def test_route_file_is_flattened_as_warm_shaders_does(self):
        route = write_file(self.root, "route.txt",
                           b"# a comment\r\n120:A:5, 300:A:5,\r\n\r\n# more\r\n  900 : A : 5\r\n\n")
        self.add_game("dragoon", "printf '%s' \"$GCN_INPUT\" > input.txt\n")
        r = probe(NAME, "1", str(route), script=self.script)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = (self.root / "build" / "probe" / NAME / "input.txt").read_text()
        self.assertEqual(got, warm_shaders.script_text(route))
        self.assertEqual(got, "120:A:5,300:A:5,900:A:5")

    def game_args(self, *settings: str, game: str = "dragoon") -> list[str]:
        self.add_game(game, "printf '%s\\n' \"$@\" > args.txt\necho 'whole run'\n")
        r = probe(NAME, "1", "", "60", *settings, script=self.script, cwd=self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        return (self.root / "build" / "probe" / NAME / "args.txt").read_text().splitlines()

    def disc(self) -> Path:
        (self.root / "rom dir").mkdir()
        return write_file(self.root / "rom dir", "Kirby Air Ride (USA).gcm", b"a disc")

    def test_a_disc_reaches_the_game_as_an_absolute_path(self):
        disc = self.disc()
        args = self.game_args("--disc=rom dir/Kirby Air Ride (USA).gcm")  # from the root
        self.assertEqual(args[-1], str(disc))
        self.assertEqual([a for a in args if a.startswith("--disc")], [])

    def test_a_disc_reaches_the_bench_too(self):
        disc = self.disc()
        args = self.game_args(f"--disc={disc}", "--bench", game="dragoon_bench")
        self.assertEqual(args[-1], str(disc))

    def test_without_a_disc_the_game_gets_no_path(self):
        self.assertEqual([a for a in self.game_args() if not a.startswith("--")], [])

    def test_a_missing_disc_exits_2_before_making_a_run_directory(self):
        self.add_game("dragoon", "")
        r = probe(NAME, "1", "", "60", "--disc=no such.iso", script=self.script, cwd=self.root)
        self.assertEqual(r.returncode, 2)
        self.assertIn(f"{self.root}/no such.iso", r.stderr)
        self.assertFalse((self.root / "build" / "probe").exists())

    def test_a_disc_speed_reaches_the_windowed_game_and_is_not_taken_for_a_path(self):
        for speed in ("fast", "console"):
            with self.subTest(speed=speed):
                args = self.game_args(f"--disc={speed}")
                self.assertIn(f"--disc={speed}", args)
                self.assertEqual([a for a in args if not a.startswith("--")], [])

    def test_no_disc_speed_setting_passes_no_disc_argument(self):
        self.assertEqual([a for a in self.game_args() if a.startswith("--disc")], [])

    def test_a_disc_speed_and_a_disc_path_go_together_in_either_order(self):
        disc = self.disc()
        for settings in (("--disc=console", f"--disc={disc}"), (f"--disc={disc}", "--disc=console")):
            with self.subTest(settings=settings):
                args = self.game_args(*settings)
                self.assertIn("--disc=console", args)
                self.assertEqual(args[-1], str(disc))

    def test_the_last_disc_speed_wins_at_the_game(self):
        args = self.game_args("--disc=console", "--disc=fast")
        self.assertEqual([a for a in args if a.startswith("--disc")], ["--disc=fast"])

    def test_a_disc_file_named_like_a_speed_is_a_path_with_a_dot_slash(self):
        write_file(self.root, "console", b"a disc")
        args = self.game_args("--disc=./console")
        self.assertEqual(args[-1], f"{self.root}/./console")
        self.assertEqual([a for a in args if a.startswith("--disc")], [])

    def test_any_other_disc_value_exits_2_before_making_a_run_directory(self):
        self.add_game("dragoon", "")
        for bad in ("--disc=slow", "--disc=Console", "--disc=fast ", "--disc="):
            with self.subTest(bad=bad):
                r = probe(NAME, "1", "", "60", bad, script=self.script, cwd=self.root)
                self.assertEqual(r.returncode, 2)
                self.assertIn("--disc", r.stderr)
        self.assertFalse((self.root / "build" / "probe").exists())

    def test_a_refused_disc_path_says_the_speeds_too(self):
        self.add_game("dragoon", "")
        r = probe(NAME, "1", "", "60", "--disc=slow", script=self.script, cwd=self.root)
        self.assertEqual(r.returncode, 2)
        self.assertIn(f"no disc image at {self.root}/slow", r.stderr)
        self.assertIn("fast or console", r.stderr)

    def test_a_disc_speed_with_bench_exits_2_before_making_a_run_directory(self):
        self.add_game("dragoon_bench", "echo 'whole run'\n")
        for speed in ("--disc=fast", "--disc=console"):
            with self.subTest(speed=speed):
                r = probe(NAME, "1", "", "60", speed, "--bench", script=self.script)
                self.assertEqual(r.returncode, 2)
                self.assertIn(f"{speed} needs a windowed run", r.stderr)
        self.assertFalse((self.root / "build" / "probe").exists())

    def test_log_list_reaches_the_windowed_game(self):
        self.assertIn("--log=dsp,ai", self.game_args("--log=dsp,ai"))

    def test_no_log_setting_passes_no_log_argument(self):
        args = self.game_args()
        self.assertEqual([a for a in args if a == "" or a.startswith("--log")], [])

    def test_aspect_reaches_the_windowed_game(self):
        self.assertIn("--aspect=16:9", self.game_args("--aspect=16:9"))
        self.assertIn("--aspect=window", self.game_args("--aspect=window"))

    def test_output_asks_the_game_for_output_dumps(self):
        self.assertIn("--dump-output", self.game_args("--output"))

    def test_no_aspect_or_output_setting_passes_neither(self):
        args = self.game_args()
        self.assertEqual([a for a in args if a.startswith(("--aspect", "--dump-output"))], [])

    def test_dragoon_setting_reaches_the_game_environment(self):
        self.add_game("dragoon", "printf '%s' \"$DRAGOON_CENSUS\" > census.txt\n")
        r = probe(NAME, "1", "", "60", "DRAGOON_CENSUS=1", script=self.script)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.root / "build" / "probe" / NAME / "census.txt").read_text(), "1")

    def test_gcn_setting_reaches_the_game_environment(self):
        self.add_game("dragoon", "printf '%s' \"$GCN_FRAMETIME\" > frametime.txt\n")
        r = probe(NAME, "1", "", "60", "GCN_FRAMETIME=1", script=self.script)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.root / "build" / "probe" / NAME / "frametime.txt").read_text(), "1")

    def test_an_exported_gcn_variable_reaches_the_game_environment_windowed_and_bench(self):
        # interp_bisect.py hands the game its GCN_INTERPRET list this way
        env = {**os.environ, "GCN_INTERPRET": "/lists/one.txt"}
        for name, settings in (("dragoon", ()), ("dragoon_bench", ("--bench",))):
            with self.subTest(name=name):
                self.add_game(name, "printf '%s' \"$GCN_INTERPRET\" > interpret.txt\necho 'whole run'\n")
                r = subprocess.run([str(self.script), NAME, "1", "", "60", *settings], capture_output=True,
                                   text=True, timeout=10, env=env)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual((self.root / "build" / "probe" / NAME / "interpret.txt").read_text(),
                                 "/lists/one.txt")
                (self.root / "build" / "probe" / NAME / "interpret.txt").unlink()

    def test_setting_of_another_prefix_exits_2_naming_it(self):
        self.add_game("dragoon", "")
        r = probe(NAME, "1", "", "60", "FOO_BAR=1", script=self.script)
        self.assertEqual(r.returncode, 2)
        self.assertIn("FOO_BAR=1", r.stderr)
        self.assertFalse((self.root / "build" / "probe").exists())

    def test_frame_count_leaves_out_output_dumps(self):
        self.add_game("dragoon", "touch frame_00060.png output_00060.png\n")
        r = probe(NAME, "1", "", "60", "--output", script=self.script)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.rstrip().endswith(": 1 frames"), r.stdout)

    def test_a_run_keeps_no_input_log_unless_it_is_a_session(self):
        self.assertIn("--no-input-log", self.game_args())
        self.assertNotIn("--no-input-log", self.game_args("GCN_SESSION=/somewhere/session"))
        self.assertIn("--no-input-log", self.game_args("GCN_SESSION="))

    def inputs(self) -> Path:
        directory = self.root / "my inputs"
        directory.mkdir()
        write_file(directory, "inputs.txt", "# gcn-recomp input log v4\n")
        return directory

    def test_replay_and_exit_after_reach_the_windowed_game(self):
        directory = self.inputs()
        args = self.game_args(f"--replay={directory}", "--exit-after=900")
        self.assertIn(f"--replay={directory}", args)
        self.assertIn("--exit-after=900", args)
        self.assertEqual([a for a in self.game_args() if a.startswith(("--replay", "--exit-after"))], [])

    def test_a_relative_replay_directory_is_taken_from_where_probe_was_run(self):
        directory = self.inputs()
        self.assertIn(f"--replay={directory}", self.game_args("--replay=my inputs"))  # from the root

    def test_a_replay_directory_with_no_input_log_exits_2_before_making_a_run_directory(self):
        self.add_game("dragoon", "")
        (self.root / "empty").mkdir()
        for given, shown in (("nowhere", self.root / "nowhere"), ("empty", self.root / "empty"),
                             (str(self.root / "nowhere"), self.root / "nowhere")):
            with self.subTest(given=given):
                r = probe(NAME, "1", "", "60", f"--replay={given}", script=self.script, cwd=self.root)
                self.assertEqual(r.returncode, 2)
                self.assertIn(f"no input log at {shown}/inputs.txt", r.stderr)
        self.assertFalse((self.root / "build" / "probe").exists())

    def test_a_windowed_run_is_hidden_silent_and_off_the_controllers_whatever_the_callers_audio_driver(self):
        self.add_game("dragoon", "printf '%s\\n' \"$@\" > args.txt\nprintf '%s' \"$SDL_AUDIO_DRIVER\" > driver.txt\n")
        r = subprocess.run([str(self.script), NAME, "1", "", "60"], capture_output=True, text=True, timeout=10,
                           env={**os.environ, "SDL_AUDIO_DRIVER": "coreaudio"})
        self.assertEqual(r.returncode, 0, r.stderr)
        run = self.root / "build" / "probe" / NAME
        args = (run / "args.txt").read_text().splitlines()
        self.assertIn("--hidden", args)
        self.assertIn("--no-gamepads", args)  # a controller left on beside it is never opened
        self.assertEqual((run / "driver.txt").read_text(), "dummy")

    def test_exit_after_must_be_a_positive_whole_number(self):
        self.add_game("dragoon", "")
        for bad in ("--exit-after=", "--exit-after=0", "--exit-after=9x", "--replay="):
            with self.subTest(bad=bad):
                r = probe(NAME, "1", "", "60", bad, script=self.script)
                self.assertEqual(r.returncode, 2)
                self.assertIn(bad, r.stderr)
        self.assertFalse((self.root / "build" / "probe").exists())

    def test_replay_and_exit_after_with_bench_exit_2(self):
        self.add_game("dragoon_bench", "echo 'whole run'\n")
        for setting in ("--replay=/somewhere/inputs", "--exit-after=900"):
            with self.subTest(setting=setting):
                r = probe(NAME, "1", "", "60", setting, "--bench", script=self.script)
                self.assertEqual(r.returncode, 2)
                self.assertIn(setting.split("=")[0] + " needs a windowed run", r.stderr)
        self.assertFalse((self.root / "build" / "probe").exists())

    def other_game(self, body: str, name: str = "dragoon-b") -> Path:
        """An executable game outside build/, in a folder with a space as a player's path may have."""
        folder = self.root / "other builds"
        folder.mkdir(exist_ok=True)
        game = write_file(folder, name, "#!/bin/sh\n" + body)
        game.chmod(game.stat().st_mode | stat.S_IXUSR)
        return game

    def run_dir(self) -> Path:
        return self.root / "build" / "probe" / NAME

    def test_bin_runs_that_game_instead_of_build_dragoon(self):
        self.add_game("dragoon", "touch ran-build-dragoon\n")
        game = self.other_game("touch ran-other\n")
        r = probe(NAME, "1", "", "60", f"--bin={game}", script=self.script)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.run_dir() / "ran-other").exists())
        self.assertFalse((self.run_dir() / "ran-build-dragoon").exists())

    def test_bin_runs_that_game_instead_of_build_dragoon_bench_under_bench(self):
        self.add_game("dragoon_bench", "touch ran-build-bench\n")
        self.add_game("dragoon", "touch ran-build-dragoon\n")
        game = self.other_game("printf '%s\\n' \"$@\" > args.txt\necho 'whole run'\n")
        r = probe(NAME, "7", "", "60", f"--bin={game}", "--bench", script=self.script)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("whole run", r.stdout)
        self.assertIn("--seconds=7", (self.run_dir() / "args.txt").read_text().splitlines())
        self.assertEqual([p.name for p in self.run_dir().iterdir() if p.name.startswith("ran-")], [])

    def test_bin_needs_no_build_of_its_own(self):
        game = self.other_game("touch ran-other\necho 'whole run'\n")
        for settings in ((), ("--bench",)):
            with self.subTest(settings=settings):
                r = probe(NAME, "1", "", "60", f"--bin={game}", *settings, script=self.script)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertTrue((self.run_dir() / "ran-other").exists())

    def test_a_relative_bin_is_taken_from_where_probe_was_run(self):
        self.other_game("touch ran-other\n")
        r = probe(NAME, "1", "", "60", "--bin=other builds/dragoon-b", script=self.script, cwd=self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.run_dir() / "ran-other").exists())

    def test_a_link_to_a_game_is_a_game(self):
        game = self.other_game("touch ran-other\n")
        link = self.root / "dragoon-link"
        link.symlink_to(game)
        r = probe(NAME, "1", "", "60", f"--bin={link}", script=self.script)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.run_dir() / "ran-other").exists())

    def test_bin_is_not_passed_on_to_the_game(self):
        game = self.other_game("printf '%s\\n' \"$@\" > args.txt\n")
        r = probe(NAME, "1", "", "60", f"--bin={game}", script=self.script)
        self.assertEqual(r.returncode, 0, r.stderr)
        args = (self.run_dir() / "args.txt").read_text().splitlines()
        self.assertIn("--hidden", args)
        self.assertEqual([a for a in args if "--bin" in a or str(game) in a], [])

    def test_a_bin_that_is_not_an_executable_file_exits_2_before_making_a_run_directory(self):
        self.add_game("dragoon", "")
        self.add_game("dragoon_bench", "")
        plain = write_file(self.root, "plain", "#!/bin/sh\n")  # no execute bit
        folder = self.root / "a folder"
        folder.mkdir()
        for bad in (self.root / "nowhere", plain, folder):
            for settings in ((), ("--bench",)):
                with self.subTest(bad=bad.name, settings=settings):
                    r = probe(NAME, "1", "", "60", f"--bin={bad}", *settings, script=self.script)
                    self.assertEqual(r.returncode, 2)
                    self.assertIn("--bin", r.stderr)
                    self.assertIn(str(bad), r.stderr)
                    self.assertFalse((self.root / "build" / "probe").exists())

    def test_a_bin_with_an_equals_sign_in_its_path_exits_2_before_making_a_run_directory(self):
        # env would read the path as a VAR=value setting and run the game's arguments as the command
        folder = self.root / "builds a=b"
        folder.mkdir()
        for name in ("dragoon", "dragoon=2"):
            game = write_file(folder, name, "#!/bin/sh\ntouch ran-other\n")
            game.chmod(game.stat().st_mode | stat.S_IXUSR)
        for given in (str(folder / "dragoon"), "builds a=b/dragoon", str(self.root / "builds a=b" / "dragoon=2")):
            for settings in ((), ("--bench",)):
                with self.subTest(given=given, settings=settings):
                    r = probe(NAME, "1", "", "60", f"--bin={given}", *settings, script=self.script, cwd=self.root)
                    self.assertEqual(r.returncode, 2)
                    self.assertIn("--bin", r.stderr)
                    self.assertIn("builds a=b", r.stderr)
                    self.assertIn("env would read", r.stderr)
                    self.assertFalse((self.root / "build" / "probe").exists())

    def test_without_bin_the_builds_still_run(self):
        self.add_game("dragoon", "touch ran-build-dragoon\n")
        r = probe(NAME, "1", script=self.script)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.run_dir() / "ran-build-dragoon").exists())

    def test_a_game_that_exits_ends_the_run_early(self):
        self.add_game("dragoon", "exit 0\n")
        r = subprocess.run([str(self.script), NAME, "8"], capture_output=True, text=True, timeout=6)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
