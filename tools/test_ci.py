"""ci.py's runner on stand-in jobs, its jobs against the workflow that runs them, and the
kit's stub link with a fake xcrun and make."""
from __future__ import annotations

import os
import re
import stat
import sys
import unittest
from pathlib import Path
from unittest import mock

import ci
from testutil import run_main, temp_dir

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def in_temp_dir(test: unittest.TestCase) -> Path:
    """Run the rest of the test in a new empty directory."""
    root = temp_dir(test).resolve()
    test.addCleanup(os.chdir, os.getcwd())
    os.chdir(root)
    return root


class Runner(unittest.TestCase):
    def setUp(self) -> None:
        self.mark = temp_dir(self) / "ran"

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
            ["cmake", "-S", ".", "-B", "build-nodisc", "-G", "Ninja", "-DDRAGOON_TESTS=ON", "-DGAME_ISO="],
            ["ninja", "-C", "build-nodisc", "runtime_check"],
            ["ninja", "-C", "build-nodisc", "unit"]])
        self.assertEqual(self.commands("kit"), [
            "clear_kit",
            ["cmake", "-S", ".", "-B", "build-kit", "-G", "Ninja", "-DCMAKE_BUILD_TYPE=RelWithDebInfo",
             "-DCMAKE_OSX_DEPLOYMENT_TARGET=14.0", "-DGAME_ISO="],
            ["ninja", "-C", "build-kit", "runtime_check", "gcn_imgui", "SDL3-static"],
            ["python3", "tools/engine_kit.py", "--build", "build-kit", "--out", os.path.abspath("engine kit"),
             "--strip-debug"],
            "link_stub"])
        snapshot, built = os.path.abspath("app job/source"), os.path.abspath("app job/build")
        self.assertEqual(self.commands("app"), [
            "clear_app",
            ["swift", "build", "-c", "release", "--package-path", "launcher"],
            ["python3", "tools/export_source.py", snapshot],
            ["python3", "launcher/tools/make_app.py", "--out", built, "--version", "0.0.0",
             "--launcher", "launcher/.build/release/Dragoon", "--kit", os.path.abspath("engine kit"),
             "--source", snapshot],
            ["ditto", "-c", "-k", "--norsrc", "--keepParent", "app job/build/Dragoon.app", "app job/Dragoon.zip"],
            ["ditto", "-x", "-k", "app job/Dragoon.zip", "app job/unzipped"],
            ["python3", "tools/check_bundle.py", "app job/unzipped/Dragoon.app", "--commit", "HEAD"],
            "link_app_stub"])

    def test_the_launcher_job_runs_swift_only_where_the_launcher_has_a_package(self):
        in_temp_dir(self)
        tests = ["-m", "unittest", "discover", "-s", "launcher/tools", "-p", "test_*.py"]
        self.assertEqual(self.commands("launcher"), [["python3", *tests], ["/usr/bin/python3", *tests]])
        Path("launcher").mkdir()
        Path("launcher/Package.swift").write_text("")
        self.assertEqual(self.commands("launcher")[2], ["python3", "launcher/tools/swift_test.py"])

    def test_each_workflow_job_runs_only_its_own_ci_job(self):
        jobs = workflow_jobs()
        self.assertEqual(sorted(jobs), sorted(ci.JOBS))
        for job, keys in jobs.items():
            lines = [value for _, key, value in keys if key == "run"]
            with self.subTest(job=job):
                self.assertIn(f"python3 tools/ci.py {job}", lines)
                self.assertLessEqual(set(lines), {"brew install ninja", f"python3 tools/ci.py {job}"})

    def test_the_app_job_follows_the_kit_job_and_takes_its_artifact(self):
        jobs = workflow_jobs()
        needs = {job: value for job, keys in jobs.items() for _, key, value in keys if key == "needs"}
        self.assertEqual(needs, {"app": "kit"})
        workspace = "${{ github.workspace }}"

        def artifacts(job: str) -> list[tuple[str, str, str]]:
            return [k for k in jobs[job] if k[0] in ("actions/upload-artifact", "actions/download-artifact")]

        self.assertEqual(artifacts("kit"), [
            ("actions/upload-artifact", "name", "engine-kit"),
            ("actions/upload-artifact", "path", f"{workspace}/{ci.KIT}"),
            ("actions/upload-artifact", "if-no-files-found", "error")])
        self.assertEqual(artifacts("app"), [
            ("actions/download-artifact", "name", "engine-kit"),
            ("actions/download-artifact", "path", f"{workspace}/{ci.KIT}"),
            ("actions/upload-artifact", "path", f"{workspace}/{ci.ZIP}"),
            ("actions/upload-artifact", "archive", "false"),
            ("actions/upload-artifact", "if-no-files-found", "error")])


def workflow_jobs() -> dict[str, list[tuple[str, str, str]]]:
    """Each workflow job's `key: value` lines in order, each as (action, key, value). The action
    is the step's `uses:` without its pin, for the keys under its `with:`, and "" elsewhere."""
    jobs: dict[str, list[tuple[str, str, str]]] = {}
    job = None
    action = ""
    in_jobs = False
    for line in WORKFLOW.read_text().splitlines():
        if line == "jobs:":
            in_jobs = True
        elif in_jobs and re.fullmatch(r"  [\w-]+:", line):
            job, action = line.strip()[:-1], ""
            jobs[job] = []
        elif job and (m := re.fullmatch(r"\s+(- )?([\w-]+):\s*(.*?)", line.split(" #", 1)[0])):
            step, key, value = m.groups()
            if step:
                action = value.split("@", 1)[0] if key == "uses" else ""
            if key not in ("uses", "with"):
                jobs[job].append((action, key, value))
    return jobs


class KitSteps(unittest.TestCase):
    """link_stub with an xcrun that prints a path with a space, or fails when XCRUN_FAILS is
    set, and a make that logs where and with what it ran and links only when MAKE_LINKS is set."""

    def setUp(self) -> None:
        self.root = in_temp_dir(self)
        Path("tests/kit").mkdir(parents=True)
        Path("tests/kit/stub_tables.c").write_text("// stub tables\n")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        self.tool(bin_dir / "xcrun", '#!/bin/sh\n[ -n "$XCRUN_FAILS" ] && exit 1\necho "/sdk dir"\n')
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

    def test_a_missing_stub_fails_without_a_traceback(self):
        Path("tests/kit/stub_tables.c").unlink()
        code, out = self.link(MAKE_LINKS="1")
        self.assertEqual(code, 1)
        self.assertIn("couldn't set up stub game", out)
        self.assertFalse(self.log.exists())

    def test_a_failing_xcrun_fails_without_a_traceback(self):
        code, out = self.link(MAKE_LINKS="1", XCRUN_FAILS="1")
        self.assertEqual(code, 1)
        self.assertIn("couldn't set up stub game", out)
        self.assertFalse(self.log.exists())

    def test_clear_kit_deletes_the_last_kit_and_stub_game(self):
        for path in ("engine kit/lib", "stub game/gen"):
            Path(path).mkdir(parents=True)
        self.assertEqual(ci.clear_kit(), 0)
        self.assertFalse(Path("engine kit").exists() or Path("stub game").exists())

    def test_the_app_job_links_the_unzipped_apps_own_kit(self):
        with mock.patch.dict(os.environ, {"MAKE_LINKS": "1"}):
            self.assertEqual(run_main(lambda argv: ci.link_app_stub())[0], 0)
        kit = f"{self.root}/app job/unzipped/Dragoon.app/Contents/Resources/kit"
        self.assertEqual(self.log.read_text().splitlines(), [
            f"{self.root}/app job/stub game", "-f", f"{kit}/Makefile", f"KIT={kit}", "SDK=/sdk dir",
            "CC=clang", "CXX=clang++"])
        self.assertEqual(Path("app job/stub game/gen/stub_tables.c").read_text(), "// stub tables\n")
        self.assertFalse(Path("stub game").exists())

    def test_the_app_jobs_failures_name_its_own_stub_game(self):
        code, out, err = run_main(lambda argv: ci.link_app_stub())
        self.assertEqual(code, 1)
        self.assertIn("app job/stub game/dragoon wasn't linked", out)
        with mock.patch.dict(os.environ, {"XCRUN_FAILS": "1"}):
            code, out, err = run_main(lambda argv: ci.link_app_stub())
        self.assertEqual(code, 1)
        self.assertIn("couldn't set up app job/stub game", out)

    def test_clear_app_deletes_the_last_app_job_and_leaves_the_kit(self):
        for path in ("app job/unzipped/Dragoon.app", "engine kit/lib"):
            Path(path).mkdir(parents=True)
        self.assertEqual(ci.clear_app(), 0)
        self.assertFalse(Path("app job").exists())
        self.assertTrue(Path("engine kit/lib").is_dir())


if __name__ == "__main__":
    unittest.main()
