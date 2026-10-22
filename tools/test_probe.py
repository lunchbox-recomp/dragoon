from __future__ import annotations

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

    def test_frame_count_leaves_out_output_dumps(self):
        self.add_game("dragoon", "touch frame_00060.png output_00060.png\n")
        r = probe(NAME, "1", "", "60", "--output", script=self.script)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.rstrip().endswith(": 1 frames"), r.stdout)


if __name__ == "__main__":
    unittest.main()
