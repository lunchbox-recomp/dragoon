"""ci.py's runner on stand-in jobs, and its jobs against the workflow that runs them."""
from __future__ import annotations

import os
import re
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
    def test_the_workflow_runs_every_job_by_name(self):
        jobs = re.findall(r"run: python3 tools/ci\.py (\w+)", WORKFLOW.read_text())
        self.assertEqual(sorted(jobs), sorted(ci.JOBS))

    def test_swift_tests_run_only_where_the_launcher_has_a_package(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(tmp.name)
        self.assertNotIn("Swift tests", [name for name, _ in ci.launcher_steps()])
        Path("launcher").mkdir()
        Path("launcher/Package.swift").write_text("")
        self.assertIn("Swift tests", [name for name, _ in ci.launcher_steps()])


if __name__ == "__main__":
    unittest.main()
