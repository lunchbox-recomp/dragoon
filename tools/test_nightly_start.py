from __future__ import annotations

import os
import plistlib
import subprocess
import time
import unittest
from collections.abc import Sequence
from pathlib import Path
from unittest import mock

import nightly
import nightly_agent
import nightly_start
from nightly_fakes import FakeScript
from testutil import run_main, temp_dir, write_file

HEAD = "1" * 40


class LockTest(unittest.TestCase):
    def test_a_second_run_is_refused_until_the_first_lets_go(self) -> None:
        nightly_dir = temp_dir(self) / "nightly"
        fd = nightly_start.take_lock(nightly_dir)
        with self.assertRaisesRegex(nightly_start.Refused, "another nightly run holds"):
            nightly_start.take_lock(nightly_dir)
        os.close(fd)
        os.close(nightly_start.take_lock(nightly_dir))

    def test_a_game_running_is_found_by_name(self) -> None:
        pgrep = FakeScript(self, "pgrep", code=1)
        self.assertEqual(nightly_start.games_running(pgrep.command()), [])
        pgrep.now("", 0)
        self.assertEqual(nightly_start.games_running(pgrep.command()), ["dragoon", "dragoon_bench"])

    def test_the_window_is_0100_to_0600(self) -> None:
        self.assertEqual([h for h in range(24) if nightly_start.in_window(h)], [1, 2, 3, 4, 5])


class RunRefusesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.nightly = temp_dir(self) / "nightly"
        patch = mock.patch.object(nightly, "NIGHTLY", self.nightly)
        patch.start()
        self.addCleanup(patch.stop)
        self.pgrep = FakeScript(self, "pgrep", code=1)

    def run_nightly(self, *argv: str) -> tuple[int, str, str]:
        return run_main(nightly.main, "run", "--pgrep", str(self.pgrep.script), *argv)

    def runs(self) -> list[str]:
        return sorted(p.name for p in self.nightly.iterdir() if p.is_dir()) if self.nightly.is_dir() else []

    def test_a_game_already_running_refuses_the_run(self) -> None:
        self.pgrep.now("", 0)
        code, _, err = self.run_nightly()
        self.assertEqual(code, 2)
        self.assertIn("dragoon and dragoon_bench is running", err)
        self.assertEqual(self.runs(), [])

    def test_another_run_holding_the_lock_refuses_the_run(self) -> None:
        fd = nightly_start.take_lock(self.nightly)
        self.addCleanup(os.close, fd)
        code, _, err = self.run_nightly()
        self.assertEqual(code, 2)
        self.assertIn("another nightly run holds", err)
        self.assertEqual(self.runs(), [])

    def test_a_launchd_run_outside_its_hours_is_skipped_with_a_line(self) -> None:
        noon = time.mktime((2026, 11, 18, 12, 0, 0, 0, 0, -1))
        with mock.patch.object(nightly.time, "time", return_value=noon):
            code, out, _ = self.run_nightly("--scheduled")
        self.assertEqual(code, 0)
        self.assertEqual(out, "2026-11-18 12:00: skipped, since a launchd run starts from 01:00 to 06:00\n")
        self.assertFalse(self.nightly.exists())


class FakeGit:
    """A stand-in for the commands update runs, answering git's questions from what it's told."""

    def __init__(self, dirty: str = "", branch: str = "main", head: str = HEAD, main: str = HEAD,
                 built: int = 0) -> None:
        self.answers = {("status", "--porcelain"): dirty, ("rev-parse", "--abbrev-ref", "HEAD"): branch,
                        ("rev-parse", "HEAD"): head, ("rev-parse", "origin/main"): main}
        self.built = built
        self.ran: list[list[str]] = []

    def __call__(self, cmd: Sequence[str]) -> subprocess.CompletedProcess:
        cmd = list(cmd)
        self.ran.append(cmd)
        if cmd[0] == "git":
            return subprocess.CompletedProcess(cmd, 0, self.answers.get(tuple(cmd[3:]), ""), "")
        return subprocess.CompletedProcess(cmd, self.built, "[1/1] Linking dragoon\n", "")


class UpdateTest(unittest.TestCase):
    def clone(self) -> Path:
        root = temp_dir(self)
        (root / "build").mkdir()
        write_file(root / "build", "CMakeCache.txt", "X:STRING=1\nCMAKE_COMMAND:INTERNAL=/opt/cmake\n")
        return root

    def test_a_clean_clone_on_main_is_fast_forwarded_and_built_by_name(self) -> None:
        root, git = self.clone(), FakeGit()
        self.assertEqual(nightly_start.update(root, git, say=lambda text: None), HEAD)
        self.assertEqual([c[3:] if c[0] == "git" else c for c in git.ran], [
            ["status", "--porcelain"], ["rev-parse", "--abbrev-ref", "HEAD"], ["fetch", "--quiet", "origin"],
            ["merge", "--ff-only", "--quiet", "origin/main"], ["submodule", "update", "--init", "--quiet"],
            ["status", "--porcelain"], ["rev-parse", "HEAD"], ["rev-parse", "origin/main"],
            ["/opt/cmake", "--build", str(root / "build"), "--target", "dragoon", "dragoon_bench"]])

    def test_changes_another_branch_or_another_commit_refuse(self) -> None:
        for git, why in ((FakeGit(dirty=" M tools/x.py"), "has changes: M tools/x.py"),
                         (FakeGit(branch="nightly"), "is on nightly, not main"),
                         (FakeGit(main="2" * 40), "is at 1111111, not origin/main 2222222"),
                         (FakeGit(built=1), "building dragoon and dragoon_bench exited 1")):
            with self.subTest(why):
                with self.assertRaisesRegex(nightly_start.Refused, why):
                    nightly_start.update(self.clone(), git, say=lambda text: None)

    def test_a_clone_with_changes_isnt_touched(self) -> None:
        git = FakeGit(dirty="?? notes.txt")
        with self.assertRaises(nightly_start.Refused):
            nightly_start.update(self.clone(), git, say=lambda text: None)
        self.assertEqual([c[3:] for c in git.ran], [["status", "--porcelain"]])

    def test_a_build_never_configured_refuses(self) -> None:
        with self.assertRaisesRegex(nightly_start.Refused, "isn't a configured build"):
            nightly_start.update(temp_dir(self), FakeGit(), say=lambda text: None)


class AgentTest(unittest.TestCase):
    def test_install_writes_a_daily_0130_scheduled_run_of_the_clone_and_uninstall_removes_it(self) -> None:
        agents, clone = temp_dir(self), temp_dir(self).resolve()
        code, out, _ = run_main(nightly.main, "install-agent", "--dir", str(agents), "--clone", str(clone))
        self.assertEqual(code, 0)
        path = agents / f"{nightly_agent.LABEL}.plist"
        job = plistlib.loads(path.read_bytes())
        self.assertEqual(job["StartCalendarInterval"], {"Hour": 1, "Minute": 30})
        self.assertEqual(job["ProgramArguments"],
                         ["/usr/bin/python3", str(clone / "tools" / "nightly.py"), "run", "--scheduled"])
        self.assertEqual((job["WorkingDirectory"], job["StandardOutPath"]), (str(clone), str(nightly_agent.LOG)))
        self.assertIn("<key>StartCalendarInterval</key>", out)
        self.assertIn("isn't loaded", out)
        code, out, _ = run_main(nightly.main, "uninstall-agent", "--dir", str(agents))
        self.assertEqual((code, path.exists()), (0, False))

    def test_print_writes_nothing(self) -> None:
        agents = temp_dir(self) / "agents"
        code, out, _ = run_main(nightly.main, "install-agent", "--dir", str(agents), "--print")
        self.assertEqual(code, 0)
        self.assertIn(str(nightly_agent.CLONE / "tools" / "nightly.py"), out)
        self.assertFalse(agents.exists())


if __name__ == "__main__":
    unittest.main()
