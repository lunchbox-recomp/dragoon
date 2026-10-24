import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import launcher_build
import mutant
from testutil import GIT_ENV, commit, git, run_main, write_file

CALC_PATH = "lib dir/calc.py"
CALC = """\
def add(a, b):
    return a + b


def sub(a, b):
    return a - b


def twice(x):
    # keep both operands the same
    return add(x, x)
"""
# Only add is tested, so a change to sub or twice survives.
TEST_CALC = """\
import unittest

import calc


class CalcTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(calc.add(2, 3), 5)
"""
TEST_ENV = f"""\
import os
import unittest


class EnvTest(unittest.TestCase):
    def test_nothing_of_the_parents_gets_in(self):
        for name in ("DRAGOON_SECRET", "GITHUB_TOKEN", "PYTHONPATH", "GIT_AUTHOR_NAME"):
            self.assertNotIn(name, os.environ)
        self.assertEqual(os.environ["PATH"], {launcher_build.TOOL_PATH!r})
        self.assertEqual(os.environ["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(os.environ["PYTHONUNBUFFERED"], "1")
        for name in ("HOME", "TMPDIR"):
            self.assertIn(name, os.environ)
"""
TEST_BROKEN = """\
import unittest


class BrokenTest(unittest.TestCase):
    def test_fails(self):
        self.fail("always fails")
"""
TEST_SLOW = """\
import time
import unittest


class SlowTest(unittest.TestCase):
    def test_sleeps(self):
        time.sleep(30)
"""
# Writes to stderr, which is unbuffered, so the lines come before unittest's own and the
# log ends where unittest does.
TEST_NOISY = """\
import sys
import unittest


class NoisyTest(unittest.TestCase):
    def test_prints_a_lot(self):
        for n in range(20000):
            print(f"noise line {n:06d}", file=sys.stderr)
"""
# Prints on import, to stdout, which is buffered when the output is a pipe unless the tests run
# unbuffered. The text would then come after unittest's own summary and read as its count.
TEST_CHATTY = """\
import unittest

print("Ran 0 tests in 0.000s\\n\\nOK")


class ChattyTest(unittest.TestCase):
    def test_passes(self):
        pass
"""
GREET_PATH = "two files/greet.py"
GREET = 'def hi():\n    return "hi"\n'
TEST_GREET = """\
import unittest

import greet


class GreetTest(unittest.TestCase):
    def test_hi(self):
        self.assertEqual(greet.hi(), "hi")
"""
# A second file in the directory, which only a pattern that names test_greet.py leaves out.
TEST_EXTRA = """\
import unittest


class ExtraTest(unittest.TestCase):
    def test_fails(self):
        self.fail("test_extra.py was selected")
"""
FILES = {
    "no tests/helper.py": "VALUE = 1\n",
    "empty tests/test_empty.py": "VALUE = 1\n",  # a name the default pattern matches, with no test
    CALC_PATH: CALC,
    "lib dir/test_calc.py": TEST_CALC,
    "env check/test_env.py": TEST_ENV,
    "broken tests/test_broken.py": TEST_BROKEN,
    "slow tests/test_slow.py": TEST_SLOW,
    "noisy tests/test_noisy.py": TEST_NOISY,
    "chatty tests/test_chatty.py": TEST_CHATTY,
    GREET_PATH: GREET,
    "two files/test_greet.py": TEST_GREET,
    "two files/test_extra.py": TEST_EXTRA,
}


def edit(old: str, new: str, file: str = CALC_PATH) -> dict:
    return {"file": file, "old": old, "new": new}


def spec_mutant(name: str, *replace: dict, dir: str = "lib dir", pattern: str = None) -> dict:
    entry = {"name": name, "dir": dir, "replace": list(replace)}
    if pattern is not None:
        entry["pattern"] = pattern
    return entry


KILLED = spec_mutant("add subtracts", edit("return a + b", "return a - b"))
SURVIVOR = spec_mutant("sub swapped", edit("return a - b", "return b - a"))


def total(killed: int, survived: int, timeout: int) -> str:
    count = killed + survived + timeout
    return f"total {count}, killed {killed}, survived {survived}, timeout {timeout}\n"


class MutantTestCase(unittest.TestCase):
    """A repository with a module, a test that checks half of it and three test directories
    that fail, hang or check the environment, with a space in every path."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.dict(os.environ, GIT_ENV)
        patch.start()
        self.addCleanup(patch.stop)
        self.dir = Path(tmp.name)
        self.repo = self.dir / "the repo"
        self.first = commit(self.repo, FILES)
        self.dest = self.dir / "the copies"
        self.spec_file = self.dir / "the spec.json"

    def write_spec(self, content: object) -> None:
        self.spec_file.write_text(content if isinstance(content, str) else json.dumps(content))

    def run_spec(self, *extra: str, dest: Path = None) -> tuple:
        return run_main(mutant.main, str(self.spec_file), str(dest or self.dest),
                        "--repo", str(self.repo), *extra)

    def run_tool(self, *mutants: dict, extra: tuple = (), dest: Path = None) -> tuple:
        self.write_spec(list(mutants))
        return self.run_spec(*extra, dest=dest)

    def read(self, copy: str, name: str = CALC_PATH) -> str:
        return (self.dest / copy / name).read_text()

    def left(self) -> list:
        """The names in DEST."""
        return sorted(p.name for p in self.dest.iterdir())

    def recording_python(self) -> tuple:
        """(a python that writes its working directory and arguments to a file, a JSON line a
        call, and then runs the real one, that file)."""
        calls = self.dir / "calls.jsonl"
        fake = write_file(self.dir, "fake python", (
            f"#!{sys.executable}\n"
            "import json, os, subprocess, sys\n"
            f"with open({str(calls)!r}, 'a') as f:\n"
            "    f.write(json.dumps([os.getcwd(), sys.argv[1:]]) + '\\n')\n"
            f"sys.exit(subprocess.run([{sys.executable!r}, *sys.argv[1:]]).returncode)\n"))
        fake.chmod(0o755)
        return fake, calls

    @staticmethod
    def recorded(calls: Path) -> list:
        return [json.loads(line) for line in calls.read_text().splitlines()]

    @staticmethod
    def alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    @staticmethod
    def kill_quietly(pid: int) -> None:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass

    def assert_child_gone(self, pid_file: Path) -> None:
        """The process a mutant started and wrote the pid of to PID_FILE is dead."""
        pid = int(pid_file.read_text())
        self.addCleanup(self.kill_quietly, pid)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and self.alive(pid):
            time.sleep(0.05)
        self.assertFalse(self.alive(pid), "the mutant's child outlived the run")

    def assert_tool_error(self, result: tuple, *why: str) -> None:
        code, out, err = result
        self.assertEqual(code, 2, err)
        self.assertEqual(out, "")
        self.assertTrue(err.startswith("mutant: "), err)
        for text in why:
            self.assertIn(text, err)


class VerdictTest(MutantTestCase):
    def test_a_killed_mutant(self):
        self.assertEqual(self.run_tool(KILLED), (0, "killed add subtracts\n" + total(1, 0, 0), ""))

    def test_a_surviving_mutant(self):
        self.assertEqual(self.run_tool(SURVIVOR), (1, "survived sub swapped\n" + total(0, 1, 0), ""))

    def test_one_line_per_mutant_in_the_specs_order(self):
        self.assertEqual(self.run_tool(SURVIVOR, KILLED), (
            1, "survived sub swapped\nkilled add subtracts\n" + total(1, 1, 0), ""))

    def test_a_kill_that_isnt_unittests_exit_1_says_how_the_run_ended(self):
        leaves = spec_mutant("exits with 7", edit("return a + b", "import os; os._exit(7)"))
        dies = spec_mutant("dies by a signal", edit(
            "return a + b", "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"))
        self.assertEqual(self.run_tool(KILLED, leaves, dies), (
            0, "killed add subtracts\nkilled exits with 7 (exit 7)\n"
               "killed dies by a signal (exit -9)\n" + total(3, 0, 0), ""))

    def test_a_mutant_that_outruns_the_timeout_and_the_process_it_started(self):
        pid_file = self.dir / "sleeper pid"
        hang = spec_mutant("hangs", edit("return a + b", (
            f"import subprocess; p = subprocess.Popen(['/bin/sleep', '60']); "
            f"open({str(pid_file)!r}, 'w').write(str(p.pid)); p.wait()")))
        started = time.monotonic()
        result = self.run_tool(hang, extra=("--timeout", "4"))
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(result, (1, "timeout hangs\n" + total(0, 0, 1), ""))
        self.assert_child_gone(pid_file)

    def test_a_child_left_running_after_the_tests_end_is_killed_too(self):
        pid_file = self.dir / "leftover pid"
        leaves = spec_mutant("leaves a child", edit("return a + b", (
            f"import subprocess; "
            f"open({str(pid_file)!r}, 'w').write(str(subprocess.Popen(['/bin/sleep', '60']).pid)); "
            "return a + b")))
        self.assertEqual(self.run_tool(leaves), (1, "survived leaves a child\n" + total(0, 1, 0), ""))
        self.assert_child_gone(pid_file)

    def test_a_crash_in_the_tool_is_a_tool_error_and_not_a_survivor(self):
        self.write_spec([KILLED])
        with mock.patch.object(mutant, "run_tests", side_effect=RuntimeError("boom")):
            self.assert_tool_error(self.run_spec(), "RuntimeError: boom")


class CopyTest(MutantTestCase):
    def tree(self) -> tuple:
        """Every file outside .git with its hash, and what git says about the tree."""
        files = {p.relative_to(self.repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(self.repo.rglob("*"))
                 if p.is_file() and ".git" not in p.relative_to(self.repo).parts}
        return files, git(self.repo, "status", "--porcelain", "--ignored")

    def test_the_repo_is_untouched_and_the_committed_files_are_what_run(self):
        # The committed calc.py has "a + b" once. If the tool read this one instead, KILLED
        # would find nothing to replace.
        write_file(self.repo / "lib dir", "calc.py", CALC.replace("a + b", "a * b"))
        write_file(self.repo, "notes.txt", "mine")
        before = self.tree()
        self.assertEqual(self.run_tool(KILLED, SURVIVOR)[:2], (
            1, "killed add subtracts\nsurvived sub swapped\n" + total(1, 1, 0)))
        self.assertEqual(self.tree(), before)
        self.assertEqual(list(self.repo.rglob("__pycache__")), [])

    def test_every_run_gets_its_own_copy(self):
        two = spec_mutant("two edits", edit("return a + b", "return a * b"),
                          edit("# keep both operands the same", "# edited"))
        other = spec_mutant("other", edit("return a - b", "return a // b"))
        self.run_tool(two, other, extra=("--keep",))
        self.assertEqual(self.read("baseline-1"), CALC)
        self.assertEqual(self.read("mutant-1"), CALC.replace("a + b", "a * b").replace(
            "keep both operands the same", "edited"))
        self.assertEqual(self.read("mutant-2"), CALC.replace("a - b", "a // b"))

    def test_a_baseline_copy_for_each_distinct_dir(self):
        self.run_tool(KILLED, spec_mutant("env", edit("return a + b", "return b + a"),
                                          dir="env check"), SURVIVOR, extra=("--keep",))
        self.assertEqual(sorted(p.name for p in self.dest.iterdir() if p.is_dir()),
                         ["baseline-1", "baseline-2", "mutant-1", "mutant-2", "mutant-3"])
        self.assertTrue((self.dest / "baseline-2" / "env check" / "test_env.py").is_file())

    def test_the_tail_of_each_runs_output_is_kept(self):
        self.run_tool(KILLED)
        self.assertIn("OK", (self.dest / "baseline-1.log").read_text())
        self.assertIn("FAIL: test_add", (self.dest / "mutant-1.log").read_text())

    def test_a_log_keeps_the_last_64_kib_of_the_output_and_no_more(self):
        quiet = spec_mutant("quiet", edit("# keep both operands the same", "# edited"),
                            dir="noisy tests")
        self.assertEqual(self.run_tool(quiet)[:2], (1, "survived quiet\n" + total(0, 1, 0)))
        for name in ("baseline-1.log", "mutant-1.log"):
            with self.subTest(name):
                data = (self.dest / name).read_bytes()
                self.assertEqual(len(data), 64 * 1024)  # over 300 KB were written
                lines = data.decode().splitlines()
                self.assertEqual(lines[-1], "OK")
                self.assertIn("noise line 019999", lines)
                self.assertNotIn("noise line 000000", lines)

    def test_no_bytecode_is_written(self):
        self.run_tool(KILLED, SURVIVOR, extra=("--keep",))
        self.assertTrue((self.dest / "mutant-1").is_dir())
        self.assertEqual(list(self.dest.rglob("__pycache__")), [])

    def test_rev_names_the_commit_to_copy(self):
        commit(self.repo, {CALC_PATH: CALC.replace("return a + b", "return b + a")})
        self.assert_tool_error(self.run_tool(KILLED), "add subtracts", "0 times")
        later = self.dir / "later copies"
        self.assertEqual(self.run_tool(KILLED, extra=("--rev", self.first), dest=later)[:2],
                         (0, "killed add subtracts\n" + total(1, 0, 0)))

    def test_paths_with_spaces(self):
        for path in (self.repo, self.dest, self.spec_file, self.repo / "lib dir"):
            self.assertIn(" ", str(path))
        self.assertEqual(self.run_tool(KILLED, SURVIVOR)[:2], (
            1, "killed add subtracts\nsurvived sub swapped\n" + total(1, 1, 0)))

    def test_the_command_line_and_the_directory_the_tests_run_in(self):
        fake, calls = self.recording_python()
        self.assertEqual(self.run_tool(KILLED, extra=("--python", str(fake)))[0], 0)
        dest = self.dest.resolve()
        want = []
        for copy in ("baseline-1", "mutant-1"):
            want.append([str(dest / copy), ["-B", "-m", "unittest", "discover", "-s",
                                            str(dest / copy / "lib dir"), "-p", "test_*.py"]])
        self.assertEqual(self.recorded(calls), want)

    def test_a_relative_python_is_relative_to_where_the_tool_ran(self):
        wrapper = write_file(self.dir, "py wrapper", f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        wrapper.chmod(0o755)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.dir)  # the tests run in a copy, so the path has to be made absolute
        self.assertEqual(self.run_tool(KILLED, extra=("--python", "./py wrapper"))[:2],
                         (0, "killed add subtracts\n" + total(1, 0, 0)))

    def test_the_tests_get_a_minimal_environment(self):
        leaks = {"DRAGOON_SECRET": "hunter2", "GITHUB_TOKEN": "x", "PYTHONPATH": str(self.repo),
                 "PATH": "/nowhere/bin:" + os.environ["PATH"]}
        harmless = spec_mutant("harmless", edit("# keep both operands the same", "# edited"),
                               dir="env check")
        with mock.patch.dict(os.environ, leaks):
            # The test in env check fails its baseline, a tool error, if anything leaked.
            self.assertEqual(self.run_tool(harmless), (1, "survived harmless\n" + total(0, 1, 0), ""))

    def test_a_symlink_that_leaves_the_copy_isnt_written_through(self):
        outside = write_file(self.dir, "outside.txt", "original text\n")
        os.symlink(outside, self.repo / "lib dir" / "link.txt")
        git(self.repo, "add", "--", "lib dir/link.txt")
        git(self.repo, "commit", "-q", "-m", "link")
        result = self.run_tool(spec_mutant("via link", edit("original", "changed", "lib dir/link.txt")))
        self.assert_tool_error(result, "lib dir/link.txt", "outside the copy")
        self.assertEqual(outside.read_text(), "original text\n")


class CleanupTest(MutantTestCase):
    """A run removes the copies it built however it ends, and keeps the logs."""

    def crash_at_the_first_mutant(self, error: BaseException):
        """Baselines run for real, and the first mutant's run raises ERROR."""
        real = mutant.run_tests

        def run_tests(python, copy, rel, pattern, timeout, log):
            if log.name.startswith("mutant-"):
                raise error
            return real(python, copy, rel, pattern, timeout, log)

        return mock.patch.object(mutant, "run_tests", run_tests)

    def test_the_copies_are_removed_and_the_logs_and_dest_stay(self):
        self.assertEqual(self.run_tool(KILLED, SURVIVOR)[0], 1)
        self.assertEqual(self.left(), ["baseline-1.log", "mutant-1.log", "mutant-2.log"])
        self.assertIn("FAIL: test_add", (self.dest / "mutant-1.log").read_text())

    def test_keep_keeps_the_copies(self):
        self.run_tool(KILLED, SURVIVOR, extra=("--keep",))
        self.assertEqual(self.left(), ["baseline-1", "baseline-1.log", "mutant-1", "mutant-1.log",
                                       "mutant-2", "mutant-2.log"])

    def test_keep_keeps_them_after_a_failing_baseline_too(self):
        broken = spec_mutant("no good", edit("return a + b", "return a * b"), dir="broken tests")
        self.assert_tool_error(self.run_tool(broken, extra=("--keep",)), "fail without a mutant")
        self.assertEqual(self.left(), ["baseline-1", "baseline-1.log", "mutant-1"])

    def test_the_copies_are_removed_after_a_failing_baseline(self):
        broken = spec_mutant("no good", edit("return a + b", "return a * b"), dir="broken tests")
        self.assert_tool_error(self.run_tool(KILLED, broken), "fail without a mutant")
        self.assertEqual(self.left(), ["baseline-1.log", "baseline-2.log"])

    def test_the_copies_are_removed_after_a_baseline_that_outruns_the_timeout(self):
        slow = spec_mutant("slow", edit("return a + b", "return a * b"), dir="slow tests")
        self.assert_tool_error(self.run_tool(slow, extra=("--timeout", "0.5")), "0.5 s")
        self.assertEqual(self.left(), ["baseline-1.log"])

    def test_the_copies_are_removed_after_a_mutant_that_outruns_the_timeout(self):
        hang = spec_mutant("hangs", edit("return a + b", "import time; time.sleep(60)"))
        self.assertEqual(self.run_tool(hang, extra=("--timeout", "4"))[:2],
                         (1, "timeout hangs\n" + total(0, 0, 1)))
        self.assertEqual(self.left(), ["baseline-1.log", "mutant-1.log"])

    def test_the_copies_are_removed_after_a_crash(self):
        self.write_spec([KILLED])
        with self.crash_at_the_first_mutant(RuntimeError("boom")):
            self.assert_tool_error(self.run_spec(), "RuntimeError: boom")
        self.assertEqual(self.left(), ["baseline-1.log"])

    def test_the_copies_are_removed_after_ctrl_c(self):
        self.write_spec([KILLED])
        with self.crash_at_the_first_mutant(KeyboardInterrupt()), \
                self.assertRaises(KeyboardInterrupt):
            self.run_spec()
        self.assertEqual(self.left(), ["baseline-1.log"])

    def test_a_dest_with_nothing_left_is_removed_too(self):
        self.assert_tool_error(self.run_tool(KILLED, spec_mutant("typo", edit("zzz", "y"))), "typo")
        self.assertFalse(self.dest.exists())

    def test_what_the_run_didnt_make_stays_and_keeps_its_dest(self):
        def plant_and_crash(*args):
            write_file(self.dest, "mine.txt", "keep")
            (self.dest / "mine").mkdir()
            write_file(self.dest / "mine", "inner.txt", "keep")
            raise RuntimeError("boom")

        self.write_spec([KILLED])
        with mock.patch.object(mutant, "run_tests", plant_and_crash):
            self.assert_tool_error(self.run_spec(), "boom")
        self.assertEqual(self.left(), ["mine", "mine.txt"])
        self.assertEqual((self.dest / "mine" / "inner.txt").read_text(), "keep")

    def test_a_copy_that_already_exists_isnt_the_runs_to_remove(self):
        real = mutant.extract

        def extract_over_a_dir(tar, copy, made):
            copy.mkdir()  # as if something else made it between the run's mkdir of DEST and now
            write_file(copy, "mine.txt", "keep")
            return real(tar, copy, made)

        self.write_spec([KILLED])
        with mock.patch.object(mutant, "extract", extract_over_a_dir):
            self.assert_tool_error(self.run_spec(), "FileExistsError")
        self.assertEqual(self.left(), ["baseline-1"])
        self.assertEqual((self.dest / "baseline-1" / "mine.txt").read_text(), "keep")

    def test_a_dest_that_exists_keeps_what_it_holds(self):
        (self.dest / "baseline-1").mkdir(parents=True)
        mine = write_file(self.dest / "baseline-1", "mine.txt", "keep")
        self.assert_tool_error(self.run_tool(KILLED), str(self.dest))
        self.assertEqual(mine.read_text(), "keep")
        self.assertEqual(self.left(), ["baseline-1"])

    def test_nothing_outside_the_runs_own_copies_is_removed(self):
        beside = write_file(self.dir, "beside the copies.txt", "mine")
        older = self.dir / "older copies"
        (older / "baseline-1").mkdir(parents=True)
        inside = write_file(older / "baseline-1", "mine.txt", "mine")
        broken = spec_mutant("no good", edit("return a + b", "return a * b"), dir="broken tests")
        self.run_tool(KILLED, SURVIVOR)
        self.run_tool(KILLED, broken, dest=self.dir / "second copies")
        self.assertEqual(beside.read_text(), "mine")
        self.assertEqual(inside.read_text(), "mine")

    def test_a_link_in_a_copy_is_removed_and_not_followed(self):
        outside = self.dir / "outside dir"
        outside.mkdir()
        precious = write_file(outside, "precious.txt", "mine")
        os.symlink(outside, self.repo / "lib dir" / "link to outside")
        git(self.repo, "add", "--", "lib dir/link to outside")
        git(self.repo, "commit", "-q", "-m", "link")
        kept = self.dir / "kept copies"
        self.run_tool(KILLED, extra=("--keep",), dest=kept)
        self.assertTrue((kept / "baseline-1" / "lib dir" / "link to outside").is_symlink())
        self.run_tool(KILLED)
        self.assertEqual(precious.read_text(), "mine")

    def test_a_copy_that_cant_be_removed_is_said_and_the_rest_go_and_the_verdict_stands(self):
        real = mutant.run_tests

        def lock_the_baseline_copy(python, copy, rel, pattern, timeout, log):
            code = real(python, copy, rel, pattern, timeout, log)
            if copy.name == "baseline-1":  # a file in a read-only dir can't be unlinked
                locked = copy / "locked"
                locked.mkdir()
                write_file(locked, "held.txt", "x")
                locked.chmod(0o555)
                self.addCleanup(locked.chmod, 0o755)
            return code

        self.write_spec([KILLED])
        with mock.patch.object(mutant, "run_tests", lock_the_baseline_copy):
            code, out, err = self.run_spec()
        baseline = self.dest.resolve() / "baseline-1"
        self.assertEqual((code, out), (0, "killed add subtracts\n" + total(1, 0, 0)))
        self.assertTrue(err.startswith(f"mutant: couldn't remove {baseline}: "), err)
        self.assertIn("Permission denied", err)
        self.assertEqual(err.count("\n"), 1, err)  # mutant-1 was removed without a word
        self.assertEqual(self.left(), ["baseline-1", "baseline-1.log", "mutant-1.log"])


class SignalTest(MutantTestCase):
    """SIGTERM and SIGHUP end a run as ^C does, with a real signal sent to the real tool."""

    def stopped_by(self, signum: int) -> None:
        pid_file = self.dir / "sleeper pid"
        hang = spec_mutant("hangs", edit("return a + b", (
            f"import subprocess; p = subprocess.Popen(['/bin/sleep', '60']); "
            f"open({str(pid_file)!r}, 'w').write(str(p.pid)); p.wait()")))
        self.write_spec([hang])
        proc = subprocess.Popen([sys.executable, "-B", mutant.__file__, str(self.spec_file),
                                 str(self.dest), "--repo", str(self.repo)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(proc.kill)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and not (pid_file.is_file() and pid_file.read_text()):
            time.sleep(0.05)
        self.assertTrue(pid_file.is_file() and pid_file.read_text(), "the mutant never started")
        self.addCleanup(self.kill_quietly, int(pid_file.read_text()))
        proc.send_signal(signum)
        out, err = proc.communicate(timeout=30)
        # The exit status a shell gives a process a signal ended, and nothing said about it.
        self.assertEqual((proc.returncode, out, err), (128 + signum, "", ""))
        self.assertEqual(self.left(), ["baseline-1.log"])
        self.assert_child_gone(pid_file)

    def test_sigterm_removes_the_copies_and_kills_what_the_tests_started(self):
        self.stopped_by(signal.SIGTERM)

    def test_sighup_removes_the_copies_and_kills_what_the_tests_started(self):
        self.stopped_by(signal.SIGHUP)

    def test_the_handlers_are_there_only_while_a_run_is(self):
        wanted = (signal.SIGTERM, signal.SIGHUP)
        before = [signal.getsignal(s) for s in wanted]
        during = []
        real = mutant.run_tests

        def peek(*args):
            during.append([signal.getsignal(s) for s in wanted])
            return real(*args)

        self.write_spec([KILLED])
        with mock.patch.object(mutant, "run_tests", peek):
            self.assertEqual(self.run_spec()[0], 0)
        self.assertEqual(during, [[mutant.exit_on_signal] * 2] * 2)  # the baseline and the mutant
        self.assertEqual([signal.getsignal(s) for s in wanted], before)


class PatternTest(MutantTestCase):
    def hi(self, name: str = "hi changes", **kw) -> dict:
        return spec_mutant(name, edit('return "hi"', 'return "ho"', GREET_PATH),
                           dir="two files", **kw)

    def test_a_pattern_leaves_a_failing_test_file_out(self):
        self.assertEqual(self.run_tool(self.hi(pattern="test_greet.py")),
                         (0, "killed hi changes\n" + total(1, 0, 0), ""))
        self.assertNotIn("test_extra", (self.dest / "baseline-1.log").read_text())
        mutant_log = (self.dest / "mutant-1.log").read_text()
        self.assertIn("FAIL: test_hi", mutant_log)
        self.assertNotIn("test_extra", mutant_log)

    def test_the_default_pattern_finds_every_test_file(self):
        self.assert_tool_error(self.run_tool(self.hi()), "two files", "fail without a mutant")
        self.assertIn("test_extra.py was selected", (self.dest / "baseline-1.log").read_text())

    def test_a_failing_baseline_names_its_pattern(self):
        self.assert_tool_error(self.run_tool(self.hi(pattern="test_extra.py")), "two files",
                               "test_extra.py", "fail without a mutant")

    def test_each_dir_and_pattern_pair_gets_a_baseline_and_runs_with_its_pattern(self):
        fake, calls = self.recording_python()
        by_name, by_glob = self.hi("by name", pattern="test_greet.py"), self.hi(
            "by glob", pattern="test_gre*.py")
        self.assertEqual(self.run_tool(by_name, by_glob,
                                       extra=("--python", str(fake), "--keep"))[0], 0)
        patterns = [args[args.index("-p") + 1] for _, args in self.recorded(calls)]
        self.assertEqual(patterns, ["test_greet.py", "test_gre*.py"] * 2)
        self.assertTrue((self.dest / "baseline-2").is_dir())
        self.assertFalse((self.dest / "baseline-3").exists())

    def test_one_pair_in_two_mutants_gets_one_baseline(self):
        fake, calls = self.recording_python()
        one, two = self.hi("one", pattern="test_greet.py"), self.hi("two", pattern="test_greet.py")
        self.assertEqual(self.run_tool(one, two, extra=("--python", str(fake)))[0], 0)
        self.assertEqual(len(self.recorded(calls)), 3)


class CountTest(unittest.TestCase):
    def test_the_count_in_unittests_summary_line(self):
        self.assertEqual(mutant.tests_run("....\n" + "-" * 70 + "\nRan 22 tests in 5.219s\n\nOK\n"), 22)
        self.assertEqual(mutant.tests_run("Ran 1 test in 0.000s\n\nOK"), 1)

    def test_no_tests_on_3_9_and_on_3_12_and_later(self):
        self.assertEqual(mutant.tests_run("Ran 0 tests in 0.000s\n\nOK\n"), 0)
        self.assertEqual(mutant.tests_run("Ran 0 tests in 0.000s\n\nNO TESTS RAN\n"), 0)

    def test_the_last_summary_line_counts(self):
        self.assertEqual(mutant.tests_run("Ran 9 tests in 1s\nRan 0 tests in 0.000s\n\nOK"), 0)

    def test_a_line_that_is_not_the_summary_does_not_count(self):
        self.assertIsNone(mutant.tests_run("it Ran 3 tests in the dark\nRan 3 tests\n"))
        self.assertIsNone(mutant.tests_run(""))


class NoTestsTest(MutantTestCase):
    """A baseline that runs no test says nothing about a mutant: on Python 3.9 it exits 0 and
    on 3.12 and later 5, so these only pass if the count decides."""

    def harmless(self, **where: str) -> dict:
        return spec_mutant("harmless", edit("# keep both operands the same", "# edited"), **where)

    def assert_ran_no_tests(self, result: tuple, *why: str) -> None:
        self.assert_tool_error(result, "ran no tests", "baseline-", *why)

    def test_a_misspelled_pattern_is_refused_before_any_mutant_runs(self):
        typo = spec_mutant("typo", edit("# keep both operands the same", "# edited"),
                           pattern="test_calcc.py")
        self.assert_ran_no_tests(self.run_tool(KILLED, typo), "lib dir", "'test_calcc.py'")
        self.assertEqual(list(self.dest.glob("mutant-*.log")), [])
        self.assertIn("Ran 0 tests", (self.dest / "baseline-2.log").read_text())

    def test_a_dir_with_no_test_file_is_refused(self):
        self.assert_ran_no_tests(self.run_tool(self.harmless(dir="no tests")), "no tests",
                                 "'test_*.py'")

    def test_a_matching_file_that_holds_no_test_is_refused(self):
        self.assert_ran_no_tests(self.run_tool(self.harmless(dir="empty tests")), "empty tests")

    def test_a_baseline_with_tests_is_not_refused(self):
        self.assertEqual(self.run_tool(self.harmless()), (1, "survived harmless\n" + total(0, 1, 0), ""))
        self.assertIn("Ran 1 test", (self.dest / "baseline-1.log").read_text())

    def test_a_test_module_that_prints_a_summary_line_isnt_the_count(self):
        chatty = self.harmless(dir="chatty tests")
        self.assertEqual(self.run_tool(chatty), (1, "survived harmless\n" + total(0, 1, 0), ""))
        log = (self.dest / "baseline-1.log").read_text()
        self.assertIn("Ran 0 tests in 0.000s", log)  # its line is in the log, before the real one
        self.assertEqual(mutant.tests_run(log), 1)

    def test_a_python_that_exits_0_and_prints_no_count_is_refused(self):
        quiet = write_file(self.dir, "quiet python", "#!/bin/sh\nexit 0\n")
        quiet.chmod(0o755)
        self.assert_ran_no_tests(self.run_tool(KILLED, extra=("--python", str(quiet))), "lib dir")

    def test_a_failing_baseline_is_still_a_failure_not_an_empty_one(self):
        self.assert_tool_error(self.run_tool(self.harmless(dir="broken tests")),
                               "fail without a mutant", "exit 1")


class RefusalTest(MutantTestCase):
    def test_an_old_found_nowhere(self):
        result = self.run_tool(KILLED, spec_mutant("typo", edit("return a * b", "return a / b")))
        self.assert_tool_error(result, "typo", CALC_PATH, "0 times")

    def test_an_old_found_twice(self):
        result = self.run_tool(KILLED, spec_mutant("vague", edit("(a, b):", "(b, a):")))
        self.assert_tool_error(result, "vague", CALC_PATH, "2 times")

    def test_a_second_edit_is_counted_in_the_text_the_first_left(self):
        result = self.run_tool(spec_mutant("clash", edit("return a + b", "return a - b"),
                                           edit("return a - b", "return b - a")))
        self.assert_tool_error(result, "clash", "2 times")

    def test_a_file_that_isnt_in_the_copy(self):
        self.assert_tool_error(self.run_tool(spec_mutant("gone", edit("a", "b", "lib dir/none.py"))),
                               "gone", "lib dir/none.py")

    def test_a_file_that_is_a_directory(self):
        self.assert_tool_error(self.run_tool(spec_mutant("dir", edit("a", "b", "lib dir"))),
                               "dir", "lib dir")

    def test_a_file_that_isnt_text(self):
        commit(self.repo, {"lib dir/blob.dat": b"\xff\xfe"})
        self.assert_tool_error(self.run_tool(spec_mutant("blob", edit("a", "b", "lib dir/blob.dat"))),
                               "blob", "lib dir/blob.dat", "UTF-8")

    def test_a_dir_that_isnt_in_the_copy(self):
        self.assert_tool_error(self.run_tool(spec_mutant("nowhere", edit("return a + b", "x"),
                                                         dir="no such dir")),
                               "nowhere", "no such dir")

    def test_nothing_runs_when_a_later_mutant_is_refused(self):
        self.assert_tool_error(self.run_tool(KILLED, spec_mutant("typo", edit("zzz", "y"))), "typo")
        self.assertEqual(list(self.dest.glob("*.log")), [])

    def test_a_failing_baseline_is_a_tool_error_and_not_a_kill(self):
        broken = spec_mutant("no good", edit("return a + b", "return a * b"), dir="broken tests")
        result = self.run_tool(KILLED, broken)
        self.assert_tool_error(result, "broken tests", "fail without a mutant", "baseline-2.log")
        self.assertIn("always fails", (self.dest / "baseline-2.log").read_text())
        self.assertEqual(list(self.dest.glob("mutant-*.log")), [])

    def test_a_baseline_that_outruns_the_timeout(self):
        slow = spec_mutant("slow", edit("return a + b", "return a * b"), dir="slow tests")
        self.assert_tool_error(self.run_tool(slow, extra=("--timeout", "0.5")),
                               "slow tests", "0.5 s", "baseline-1.log")

    def test_a_dest_that_exists(self):
        self.dest.mkdir()
        write_file(self.dest, "mine.txt", "keep")
        self.assert_tool_error(self.run_tool(KILLED), str(self.dest))
        self.assertEqual(os.listdir(self.dest), ["mine.txt"])

    def test_a_dest_inside_the_repo(self):
        dest = self.repo / "build" / "copies"
        self.assert_tool_error(self.run_tool(KILLED, dest=dest), "inside the repo")
        self.assertFalse((self.repo / "build").exists())

    def test_a_dest_inside_the_repo_by_way_of_a_link(self):
        os.symlink(self.repo, self.dir / "link to repo")
        dest = self.dir / "link to repo" / "copies"
        self.assert_tool_error(self.run_tool(KILLED, dest=dest), "inside the repo")
        self.assertFalse((self.repo / "copies").exists())

    def test_a_dest_inside_the_repo_in_another_letter_case(self):
        if not (self.dir / "THE REPO").exists():
            self.skipTest("the temp directory is on a case-sensitive volume")
        dest = self.dir / "THE REPO" / "copies"
        self.assert_tool_error(self.run_tool(KILLED, dest=dest), "inside the repo")
        self.assertFalse((self.repo / "copies").exists())

    def test_a_dest_inside_the_repo_by_way_of_the_data_volume(self):
        data = Path("/System/Volumes/Data") / self.repo.resolve().relative_to("/")
        if not (data.exists() and data.samefile(self.repo)):
            self.skipTest("this system has no /System/Volumes/Data spelling of the temp directory")
        self.assert_tool_error(self.run_tool(KILLED, dest=data / "copies"), "inside the repo")
        self.assertFalse((self.repo / "copies").exists())

    def test_a_dest_that_is_a_dangling_link(self):
        target = self.dir / "link target"
        os.symlink(target, self.dest)
        self.assert_tool_error(self.run_tool(KILLED), str(self.dest))
        self.assertFalse(target.exists())

    def test_a_dest_inside_the_checkout_holding_the_tool(self):
        tool_root = self.dir / "tool checkout"
        tool_root.mkdir()
        with mock.patch.object(mutant, "ROOT", tool_root):
            result = self.run_tool(KILLED, dest=tool_root / "copies")
        self.assert_tool_error(result, "inside the checkout holding this tool")
        self.assertEqual(os.listdir(tool_root), [])

    def test_the_repo_itself_as_dest_is_a_dest_that_exists(self):
        self.assert_tool_error(self.run_tool(KILLED, dest=self.repo), str(self.repo))

    def test_a_directory_that_isnt_a_checkout(self):
        self.write_spec([KILLED])
        result = run_main(mutant.main, str(self.spec_file), str(self.dest), "--repo", str(self.dir))
        self.assert_tool_error(result, "isn't a git checkout")

    def test_a_rev_git_doesnt_know(self):
        self.assert_tool_error(self.run_tool(KILLED, extra=("--rev", "no-such-rev")), "no-such-rev")
        self.assertFalse(self.dest.exists())

    def test_a_tar_that_fails_says_why(self):
        fake = write_file(self.dir, "fake tar", '#!/bin/sh\necho "tar: No space left on device" >&2\nexit 1\n')
        fake.chmod(0o755)
        self.write_spec([KILLED])
        with mock.patch.object(mutant, "TAR", str(fake)):
            self.assert_tool_error(self.run_spec(), "No space left on device")
        self.assertFalse(self.dest.exists())

    def test_a_rev_that_looks_like_an_option(self):
        result = self.run_tool(KILLED, extra=("--rev=--output=" + str(self.dir / "out.tar"),))
        self.assert_tool_error(result, "--output")
        self.assertFalse((self.dir / "out.tar").exists())

    def test_a_python_that_isnt_there(self):
        self.assert_tool_error(self.run_tool(KILLED, extra=("--python", str(self.dir / "no python"))),
                               "no python")
        self.assertFalse(self.dest.exists())

    def test_a_timeout_that_isnt_a_positive_number(self):
        for value in ("0", "-1", "soon", "nan", "inf"):
            with self.subTest(value):
                self.write_spec([KILLED])
                code, out, err = self.run_spec("--timeout=" + value)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("--timeout", err)
                self.assertFalse(self.dest.exists())


class SpecTest(MutantTestCase):
    def test_what_a_spec_may_not_hold(self):
        bad = {
            "an object, not a list": KILLED,
            "an empty list": [],
            "a mutant that isn't an object": ["add subtracts"],
            "no name": [{"dir": "lib dir", "replace": KILLED["replace"]}],
            "an extra key": [{**KILLED, "extra": 1}],
            "a name that isn't text": [{**KILLED, "name": 3}],
            "an empty name": [{**KILLED, "name": ""}],
            "a name with a newline": [{**KILLED, "name": "two\nlines"}],
            "the same name twice": [KILLED, KILLED],
            "a dir that isn't text": [{**KILLED, "dir": ["lib dir"]}],
            "an empty dir": [{**KILLED, "dir": ""}],
            "an absolute dir": [{**KILLED, "dir": str(self.repo / "lib dir")}],
            "a dir up a level": [{**KILLED, "dir": "../lib dir"}],
            "a dir that goes up in the middle": [{**KILLED, "dir": "lib dir/../../x"}],
            "no replace": [{"name": "x", "dir": "lib dir"}],
            "an empty replace": [spec_mutant("x")],
            "a replace that isn't a list": [{**KILLED, "replace": edit("a", "b")}],
            "an edit that isn't an object": [{**KILLED, "replace": ["return a + b"]}],
            "an edit with no new": [spec_mutant("x", {"file": CALC_PATH, "old": "a"})],
            "an edit with an extra key": [spec_mutant("x", {**edit("a", "b"), "count": 1})],
            "a pattern that isn't text": [spec_mutant("x", edit("a", "b"), pattern=3)],
            "an empty pattern": [spec_mutant("x", edit("a", "b"), pattern="")],
            "a pattern with a slash": [spec_mutant("x", edit("a", "b"), pattern="sub/test_*.py")],
            "an empty old": [spec_mutant("x", edit("", "b"))],
            "an old that isn't text": [spec_mutant("x", edit(1, "b"))],
            "a new that isn't text": [spec_mutant("x", edit("a", 2))],
            "an old the same as its new": [spec_mutant("x", edit("return a + b", "return a + b"))],
            "an empty file": [spec_mutant("x", edit("a", "b", ""))],
            "an absolute file": [spec_mutant("x", edit("a", "b", str(self.repo / CALC_PATH)))],
            "a file up a level": [spec_mutant("x", edit("a", "b", "../the spec.json"))],
            "text that isn't JSON": "[{",
        }
        for label, content in bad.items():
            with self.subTest(label):
                self.write_spec(content)
                self.assert_tool_error(self.run_spec())
                self.assertFalse(self.dest.exists())

    def test_a_spec_that_isnt_there(self):
        self.assert_tool_error(self.run_spec(), str(self.spec_file))
        self.assertFalse(self.dest.exists())

    def test_an_edit_may_delete_the_old_text(self):
        gone = spec_mutant("deleted", edit("return a + b", "pass"))
        self.assertEqual(self.run_tool(gone, extra=("--keep",))[:2],
                         (0, "killed deleted\n" + total(1, 0, 0)))
        self.assertNotIn("return a + b", self.read("mutant-1"))

    def test_a_crlf_file_keeps_its_line_endings(self):
        crlf = CALC.replace("\n", "\r\n")
        commit(self.repo, {CALC_PATH: crlf.encode()})
        self.run_tool(spec_mutant("crlf", edit("return a - b", "return b - a")), extra=("--keep",))
        self.assertEqual((self.dest / "mutant-1" / CALC_PATH).read_bytes(),
                         crlf.replace("a - b", "b - a").encode())


class PathTest(unittest.TestCase):
    def test_the_fixed_path_is_the_launchers(self):
        self.assertEqual(mutant.TOOL_PATH, launcher_build.TOOL_PATH)

    def test_the_tool_runs_with_no_other_file_of_the_repo_beside_it(self):
        """A tool that imported a sibling would run the repo's own files, and a broken one
        would give a traceback and an exit 1 that reads as a survivor."""
        with tempfile.TemporaryDirectory() as tmp:
            alone = write_file(Path(tmp), "mutant.py", Path(mutant.__file__).read_text())
            done = subprocess.run([sys.executable, "-B", str(alone), "--help"], cwd=tmp,
                                  env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
        self.assertEqual((done.returncode, done.stderr), (0, ""))


class HelpTest(unittest.TestCase):
    def test_help_prints_the_usage(self):
        code, out, err = run_main(mutant.main, "--help")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("SPEC DEST", out)
        self.assertIn("--timeout", out)


if __name__ == "__main__":
    unittest.main()
