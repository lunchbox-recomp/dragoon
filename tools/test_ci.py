"""ci.py's runner on stand-in jobs, its jobs against the workflow that runs them, and the
kit's stub link with a fake xcrun and make."""
from __future__ import annotations

import os
import re
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ci
from testutil import run_main

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def in_temp_dir(test: unittest.TestCase) -> Path:
    """Run the rest of the test in a new empty directory."""
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    test.addCleanup(os.chdir, os.getcwd())
    root = Path(tmp.name).resolve()
    os.chdir(root)
    return root


class Runner(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.mark = Path(tmp.name, "ran")

    def test_the_first_failing_step_stops_the_run(self):
        jobs = {"a": lambda: [("ok", py("pass")), ("bad", py("raise SystemExit(3)")),
                              ("never", py(f"open({str(self.mark)!r}, 'w')"))],
                "b": lambda: [("never either", py(f"open({str(self.mark)!r}, 'w')"))]}
        with mock.patch.dict(ci.JOBS, jobs, clear=True):
            code, out, err = run_main(ci.main)
        self.assertEqual(code, 1)
        self.assertIn("== a: bad exited 3", out)
        self.assertFalse(self.mark.exists())

    def test_no_job_runs_every_job_and_a_named_job_runs_alone(self):
        jobs = {"a": lambda: [("first", py("pass"))], "b": lambda: [("second", lambda: 0)]}
        with mock.patch.dict(ci.JOBS, jobs, clear=True):
            self.assertEqual(run_main(ci.main)[:2], (0, "== a: first\n== b: second\n"))
            self.assertEqual(run_main(ci.main, "b")[:2], (0, "== b: second\n"))

    def test_an_unknown_job_exits_2(self):
        code, out, err = run_main(ci.main, "tools", "nope")
        self.assertEqual(code, 2)
        self.assertIn("no job nope", err)


class Jobs(unittest.TestCase):
    def commands(self, job: str) -> list:
        """Each step's command, or a Python step's function name."""
        return [step if isinstance(step, list) else step.__name__ for _, step in ci.JOBS[job]()]

    def test_each_job_runs_the_steps_the_workflow_ran(self):
        tests = ["-m", "unittest", "discover", "-s", "tools", "-p", "test_*.py"]
        self.assertEqual(self.commands("tools"), [
            ["python3", "tools/check_no_game_data.py"], ["python3", *tests],
            ["/usr/bin/python3", "tools/check_no_game_data.py"], ["/usr/bin/python3", *tests]])
        self.assertEqual(self.commands("macos"), [
            ["cmake", "-S", ".", "-B", "build-nodisc", "-G", "Ninja", "-DDRAGOON_TESTS=ON"],
            ["ninja", "-C", "build-nodisc", "runtime_check"],
            ["ninja", "-C", "build-nodisc", "unit"]])
        self.assertEqual(self.commands("kit"), [
            "clear_kit",
            ["cmake", "-S", ".", "-B", "build-kit", "-G", "Ninja", "-DCMAKE_BUILD_TYPE=RelWithDebInfo",
             "-DCMAKE_OSX_DEPLOYMENT_TARGET=14.0", "-DGAME_ISO="],
            ["ninja", "-C", "build-kit", "runtime_check", "SDL3-static"],
            ["python3", "tools/engine_kit.py", "--build", "build-kit", "--out", os.path.abspath("engine kit"),
             "--strip-debug"],
            "link_stub"])

    def test_the_launcher_job_runs_swift_only_where_the_launcher_has_a_package(self):
        in_temp_dir(self)
        tests = ["-m", "unittest", "discover", "-s", "launcher/tools", "-p", "test_*.py"]
        self.assertEqual(self.commands("launcher"), [["python3", *tests], ["/usr/bin/python3", *tests]])
        Path("launcher").mkdir()
        Path("launcher/Package.swift").write_text("")
        self.assertEqual(self.commands("launcher")[2], ["python3", "launcher/tools/swift_test.py"])

    def test_each_workflow_job_runs_only_its_own_ci_job(self):
        runs: dict[str, list[str]] = {}
        job = None
        in_jobs = False
        for line in WORKFLOW.read_text().splitlines():
            if line == "jobs:":
                in_jobs = True
            elif in_jobs and re.fullmatch(r"  [\w-]+:", line):
                job = line.strip()[:-1]
                runs[job] = []
            elif job and re.match(r"\s+run:", line):
                runs[job].append(line.split("run:", 1)[1].strip())
        self.assertEqual(sorted(runs), sorted(ci.JOBS))
        for job, lines in runs.items():
            with self.subTest(job=job):
                self.assertIn(f"python3 tools/ci.py {job}", lines)
                self.assertLessEqual(set(lines), {"brew install ninja", f"python3 tools/ci.py {job}"})


class KitSteps(unittest.TestCase):
    """link_stub with an xcrun that prints a path with a space and a make that logs where and
    with what it ran, and links only when MAKE_LINKS is set."""

    def setUp(self) -> None:
        self.root = in_temp_dir(self)
        Path("tests/kit").mkdir(parents=True)
        Path("tests/kit/stub_tables.c").write_text("// stub tables\n")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        self.tool(bin_dir / "xcrun", "#!/bin/sh\necho '/sdk dir'\n")
        self.tool(bin_dir / "make", '#!/bin/sh\n'
                                    'pwd -P > "$MAKE_LOG"\n'
                                    'for a in "$@"; do echo "$a" >> "$MAKE_LOG"; done\n'
                                    '[ -n "$MAKE_LINKS" ] && printf "" > dragoon && chmod +x dragoon\n'
                                    'exit "${MAKE_EXIT:-0}"\n')
        self.log = self.root / "make.log"
        env = mock.patch.dict(os.environ, {"PATH": f"{bin_dir}:{os.environ['PATH']}",
                                           "MAKE_LOG": str(self.log)})
        env.start()
        self.addCleanup(env.stop)

    def tool(self, path: Path, text: str) -> None:
        path.write_text(text)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def link(self, **env: str) -> tuple[int, str]:
        with mock.patch.dict(os.environ, env):
            code, out, err = run_main(lambda argv: ci.link_stub())
        return code, out

    def test_links_the_kit_from_the_stub_game_with_its_paths(self):
        self.assertEqual(self.link(MAKE_LINKS="1")[0], 0)
        kit = f"{self.root}/engine kit"
        self.assertEqual(self.log.read_text().splitlines(), [
            f"{self.root}/stub game", "-f", f"{kit}/Makefile", f"KIT={kit}", "SDK=/sdk dir",
            "CC=clang", "CXX=clang++"])
        self.assertEqual(Path("stub game/gen/stub_tables.c").read_text(), "// stub tables\n")

    def test_a_link_that_leaves_no_game_fails(self):
        code, out = self.link()
        self.assertEqual(code, 1)
        self.assertIn("stub game/dragoon wasn't linked", out)

    def test_a_failing_make_fails_with_its_code(self):
        self.assertEqual(self.link(MAKE_LINKS="1", MAKE_EXIT="2")[0], 2)

    def test_a_missing_stub_or_xcrun_fails_without_a_traceback(self):
        Path("tests/kit/stub_tables.c").unlink()
        code, out = self.link(MAKE_LINKS="1")
        self.assertEqual(code, 1)
        self.assertIn("couldn't set up stub game", out)
        self.assertFalse(self.log.exists())

    def test_clear_kit_deletes_the_last_kit_and_stub_game(self):
        for path in ("engine kit/lib", "stub game/gen"):
            Path(path).mkdir(parents=True)
        self.assertEqual(ci.clear_kit(), 0)
        self.assertFalse(Path("engine kit").exists() or Path("stub game").exists())


if __name__ == "__main__":
    unittest.main()
