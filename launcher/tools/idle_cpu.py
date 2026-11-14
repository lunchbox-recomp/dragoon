#!/usr/bin/env python3
"""How much of one core does a process use while it sits there?

Usage: idle_cpu.py PID SECONDS

Reads the process's CPU time, user and system for all its threads, from `/bin/ps -o cputime=`
once, waits SECONDS and reads it again. Prints one line with the share of one core it used
over the time that actually passed, such as

  pid 4242: 0.07% of a core, 0.04 s of CPU in 60.0 s

ps gives CPU time to a hundredth of a second, so over 60 s a reading is good to about 0.02%.
It only reads; it never signals the process.

Exits 0 with the line, 1 when the process isn't there at the start or has gone by the end,
and 2 on a bad argument.
"""
from __future__ import annotations

import argparse
import math
import subprocess
import sys
import time
from typing import Callable, NoReturn, Optional

PS = "/bin/ps"


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        print(f"idle_cpu.py: {message}", file=sys.stderr)
        sys.exit(2)


def parse_cputime(text: str) -> float:
    """Seconds from ps's cputime, which macOS prints as minutes and seconds, `634:51.47`. An
    hours field and a `D-` days prefix, as other ps builds print, are read too."""
    days = 0
    if "-" in text:
        day_text, text = text.split("-", 1)
        days = int(day_text)
    fields = text.strip().split(":")
    if not 2 <= len(fields) <= 3:
        raise ValueError(f"not a CPU time: {text!r}")
    seconds = float(fields[-1])
    minutes = int(fields[-2])
    hours = int(fields[0]) if len(fields) == 3 else 0
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def read_cputime(pid: int) -> Optional[float]:
    """The CPU time PID has used, in seconds, or None when there's no such process."""
    done = subprocess.run([PS, "-o", "cputime=", "-p", str(pid)], stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    text = done.stdout.strip()
    return parse_cputime(text) if done.returncode == 0 and text else None


def measure(pid: int, seconds: float, read: Callable[[int], Optional[float]] = read_cputime,
            clock: Callable[[], float] = time.monotonic,
            sleep: Callable[[float], None] = time.sleep) -> Optional[tuple[float, float]]:
    """The CPU seconds PID used and the seconds that passed while waiting SECONDS, or None when
    it wasn't there at either end."""
    before, start = read(pid), clock()
    if before is None:
        return None
    sleep(seconds)
    after, end = read(pid), clock()
    if after is None:
        return None
    return after - before, end - start


def report(pid: int, cpu: float, elapsed: float) -> str:
    share = 100 * cpu / elapsed if elapsed > 0 else 0.0
    return f"pid {pid}: {share:.2f}% of a core, {cpu:.2f} s of CPU in {elapsed:.1f} s"


def main(argv: list[str]) -> int:
    parser = Parser(prog="idle_cpu.py", description="How much of one core a process uses.")
    parser.add_argument("pid", type=int, metavar="PID")
    parser.add_argument("seconds", type=float, metavar="SECONDS")
    args = parser.parse_args(argv)
    if args.pid <= 0:
        parser.error(f"PID must be above 0, not {args.pid}")
    if not (math.isfinite(args.seconds) and args.seconds > 0):
        parser.error(f"SECONDS must be a number above 0, not {args.seconds:g}")
    result = measure(args.pid, args.seconds)
    if result is None:
        print(f"idle_cpu.py: no process {args.pid}", file=sys.stderr)
        return 1
    print(report(args.pid, *result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
