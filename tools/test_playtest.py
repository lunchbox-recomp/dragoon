import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from testutil import write_file

ROOT = Path(__file__).resolve().parents[1]
PLAYTEST = ROOT / "tools" / "playtest.sh"


class PlaytestTest(unittest.TestCase):
    """playtest.sh copied into a temp tree, so the game it would run is whatever the test puts
    in build/. The real game is never run."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "tools").mkdir()
        self.script = self.root / "tools" / "playtest.sh"
        shutil.copy(PLAYTEST, self.script)
        (self.root / "build").mkdir()

    def add_game(self, body: str = "") -> Path:
        game = write_file(self.root / "build", "dragoon", "#!/bin/sh\n" + body)
        game.chmod(game.stat().st_mode | stat.S_IXUSR)
        return game

    def playtest(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        environ = {k: v for k, v in os.environ.items() if k != "GCN_SESSION"}
        return subprocess.run([str(self.script), *args], capture_output=True, text=True, timeout=10,
                              env={**environ, **(env or {})})

    def test_help_exits_0_and_prints_usage(self):
        r = self.playtest("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Usage: tools/playtest.sh [SETTING ...]", r.stdout)
        self.assertIn("--dry-run", r.stdout)

    def test_dry_run_prints_the_command_and_makes_nothing(self):
        game = self.add_game()
        r = self.playtest("GCN_AXSTATS=0", "--pads=2", "--dry-run", "--scale=3", "GCN_WAV=/elsewhere.wav")
        self.assertEqual(r.returncode, 0, r.stderr)
        first, command = r.stdout.splitlines()
        m = re.fullmatch("session (" + re.escape(str(self.root)) + r"/build/playtest/\d{8}-\d{6})", first)
        self.assertIsNotNone(m, first)
        d = m[1]
        self.assertEqual(command, f"in {self.root}: env GCN_SESSION={d} GCN_AXSTATS=0 GCN_WAV=/elsewhere.wav "
                                  f"{game} --pads=2 --scale=3 2>&1 | tee {d}/stdout.txt")
        self.assertFalse((self.root / "build" / "playtest").exists())

    def test_dry_run_without_settings_leaves_the_games_defaults(self):
        game = self.add_game()
        command = self.playtest("--dry-run").stdout.splitlines()[1]
        self.assertTrue(command.endswith(f" {game} 2>&1 | tee {command.split('GCN_SESSION=')[1].split()[0]}/stdout.txt"),
                        command)

    def test_bad_settings_exit_2_and_make_nothing(self):
        self.add_game()
        for bad in ("--pads=5", "--pads=0", "--scale=0", "--scale=10", "--hidden", "dragoon", "GCN_SESSION=/x",
                    "GCN_SESSION="):
            with self.subTest(bad=bad):
                r = self.playtest(bad, "--dry-run")
                self.assertEqual(r.returncode, 2)
                self.assertIn(bad, r.stderr)
                self.assertEqual(r.stdout, "")
        self.assertFalse((self.root / "build" / "playtest").exists())

    def test_a_session_already_set_exits_2(self):
        self.add_game()
        r = self.playtest("--dry-run", env={"GCN_SESSION": "/somewhere"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("GCN_SESSION is set to /somewhere", r.stderr)

    def test_missing_game_exits_2(self):
        r = self.playtest("--dry-run")
        self.assertEqual(r.returncode, 2)
        self.assertIn("build/dragoon", r.stderr)
        self.assertFalse((self.root / "build" / "playtest").exists())

    def test_a_run_tees_the_games_output_and_prints_the_directory(self):
        # A stand-in game that prints its session and its arguments, then fails.
        self.add_game('echo "out $GCN_SESSION $GCN_AXSTATS $*"\necho "err" >&2\nexit 3\n')
        r = self.playtest("--pads=4", "GCN_AXSTATS=0")
        self.assertEqual(r.returncode, 3, r.stderr)
        sessions = list((self.root / "build" / "playtest").iterdir())
        self.assertEqual(len(sessions), 1)
        d = sessions[0]
        self.assertEqual((d / "stdout.txt").read_text(), f"out {d} 0 --pads=4\nerr\n")
        self.assertEqual(r.stdout, f"out {d} 0 --pads=4\nerr\nsession {d}\n"
                                   f"read it with: tools/session_report.py {d}\n")


if __name__ == "__main__":
    unittest.main()
