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


def probe(*args: str, script: Path = PROBE) -> subprocess.CompletedProcess:
    return subprocess.run([str(script), *args], capture_output=True, text=True, timeout=10)


class ProbeArgumentsTest(unittest.TestCase):
    def tearDown(self):
        self.assertFalse((ROOT / "build" / "probe" / NAME).exists())

    def test_help_exits_0_and_prints_usage(self):
        r = probe("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Usage:", r.stdout)

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


class ProbeTreeTest(unittest.TestCase):
    """probe.sh copied into a temp tree, so the game it runs is whatever the test puts in build/."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
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

    def game_args(self, *settings: str) -> list[str]:
        self.add_game("dragoon", "printf '%s\\n' \"$@\" > args.txt\n")
        r = probe(NAME, "1", "", "60", *settings, script=self.script)
        self.assertEqual(r.returncode, 0, r.stderr)
        return (self.root / "build" / "probe" / NAME / "args.txt").read_text().splitlines()

    def test_log_list_reaches_the_windowed_game(self):
        self.assertIn("--log=dsp,ai", self.game_args("--log=dsp,ai"))

    def test_no_log_setting_passes_no_log_argument(self):
        args = self.game_args()
        self.assertEqual([a for a in args if a == "" or a.startswith("--log")], [])


if __name__ == "__main__":
    unittest.main()
