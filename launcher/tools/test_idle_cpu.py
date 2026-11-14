from __future__ import annotations

import io
import re
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Optional

import idle_cpu

TOOL = Path(__file__).resolve().with_name("idle_cpu.py")
LINE = re.compile(r"pid [0-9]+: [0-9]+\.[0-9][0-9]% of a core, [0-9]+\.[0-9][0-9] s of CPU in "
                  r"[0-9]+\.[0-9] s\n")


def run_main(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            status = idle_cpu.main(list(argv))
        except SystemExit as e:
            status = int(e.code)
    return status, out.getvalue(), err.getvalue()


class Fakes:
    """CPU readings and clock times handed out in turn, and the waits asked for."""

    def __init__(self, readings: list[Optional[float]], times: list[float]) -> None:
        self.readings, self.times, self.sleeps, self.pids = readings, times, [], []

    def read(self, pid: int) -> Optional[float]:
        self.pids.append(pid)
        return self.readings.pop(0)

    def clock(self) -> float:
        return self.times.pop(0)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def measure(self, pid: int, seconds: float) -> Optional[tuple[float, float]]:
        return idle_cpu.measure(pid, seconds, read=self.read, clock=self.clock, sleep=self.sleep)


class ParseTest(unittest.TestCase):
    def test_macos_minutes_and_seconds(self) -> None:
        self.assertAlmostEqual(idle_cpu.parse_cputime("0:00.05"), 0.05)
        self.assertAlmostEqual(idle_cpu.parse_cputime("  5:10.75\n"), 310.75)
        self.assertAlmostEqual(idle_cpu.parse_cputime("634:51.47"), 634 * 60 + 51.47)

    def test_hours_and_days(self) -> None:
        self.assertAlmostEqual(idle_cpu.parse_cputime("1:02:03.50"), 3723.5)
        self.assertAlmostEqual(idle_cpu.parse_cputime("2-01:00:00"), 2 * 86400 + 3600)

    def test_what_is_not_a_cpu_time(self) -> None:
        for text in ("", "12", "1:2:3:4", "a:b", "1:xx"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                idle_cpu.parse_cputime(text)


class MeasureTest(unittest.TestCase):
    def test_cpu_and_time_between_the_two_readings(self) -> None:
        fakes = Fakes([10.0, 10.3], [100.0, 160.5])
        cpu, elapsed = fakes.measure(4242, 60)
        self.assertAlmostEqual(cpu, 0.3)
        self.assertAlmostEqual(elapsed, 60.5)
        self.assertEqual(fakes.sleeps, [60])
        self.assertEqual(fakes.pids, [4242, 4242])

    def test_a_process_that_is_not_there_is_not_waited_on(self) -> None:
        fakes = Fakes([None], [100.0])
        self.assertIsNone(fakes.measure(4242, 60))
        self.assertEqual(fakes.sleeps, [])

    def test_a_process_that_goes_during_the_wait(self) -> None:
        self.assertIsNone(Fakes([10.0, None], [100.0, 160.0]).measure(4242, 60))

    def test_the_report_is_a_share_of_one_core(self) -> None:
        self.assertEqual(idle_cpu.report(7, 0.3, 60.0),
                         "pid 7: 0.50% of a core, 0.30 s of CPU in 60.0 s")
        self.assertEqual(idle_cpu.report(7, 3.0, 2.0),
                         "pid 7: 150.00% of a core, 3.00 s of CPU in 2.0 s")


class ArgumentTest(unittest.TestCase):
    def test_bad_arguments_exit_2_with_one_line(self) -> None:
        for argv in ((), ("42",), ("pid", "60"), ("0", "60"), ("-5", "60"), ("42", "0"),
                     ("42", "-1"), ("42", "nan"), ("42", "inf"), ("42", "60", "extra")):
            with self.subTest(argv=argv):
                status, out, err = run_main(*argv)
                self.assertEqual(status, 2)
                self.assertEqual(out, "")
                self.assertEqual(len(err.splitlines()), 1)
                self.assertTrue(err.startswith("idle_cpu.py: "))


class RealProcessTest(unittest.TestCase):
    """Runs ps on children this test starts and stops."""

    def start(self, *cmd: str) -> subprocess.Popen:
        child = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        return child

    def test_reads_a_running_process(self) -> None:
        self.assertGreaterEqual(idle_cpu.read_cputime(self.start("/bin/sleep", "30").pid), 0)

    def test_a_sleeping_process_uses_almost_nothing(self) -> None:
        cpu, elapsed = idle_cpu.measure(self.start("/bin/sleep", "30").pid, 0.5)
        self.assertGreaterEqual(elapsed, 0.5)
        self.assertLess(cpu / elapsed, 0.05)

    def test_a_busy_process_uses_more_than_5_percent(self) -> None:
        """A spinning `yes` over one second. On a loaded Mac it has had as little as 16% of a
        core, so the bar is 5%."""
        cpu, elapsed = idle_cpu.measure(self.start("/usr/bin/yes").pid, 1.0)
        self.assertGreater(cpu / elapsed, 0.05)

    def test_a_process_that_has_exited_exits_1(self) -> None:
        child = subprocess.Popen(["/usr/bin/true"])
        child.wait()
        self.assertIsNone(idle_cpu.read_cputime(child.pid))
        status, out, err = run_main(str(child.pid), "0.1")
        self.assertEqual((status, out), (1, ""))
        self.assertEqual(err, f"idle_cpu.py: no process {child.pid}\n")

    def test_the_command_line_prints_one_line(self) -> None:
        pid = self.start("/bin/sleep", "30").pid
        done = subprocess.run([sys.executable, "-B", str(TOOL), str(pid), "0.3"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertRegex(done.stdout, LINE)
        self.assertTrue(done.stdout.startswith(f"pid {pid}: "))


if __name__ == "__main__":
    unittest.main()
