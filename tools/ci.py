#!/usr/bin/env python3
"""Run the steps CI runs, on a runner or on your own Mac.

Usage: tools/ci.py [JOB ...]

Run it from the repository's root, with the gcn-recomp submodule checked out. With no JOB it
runs every job: tools, macos, kit and launcher. A job's steps run in order, and the first
one that fails stops the run. .github/workflows/ci.yml installs what a runner lacks and runs
each job by name, so a step changes here and nowhere else.

The kit job leaves the engine kit in `engine kit/` and links it against stub tables in
`stub game/`. Both names have a space, as a player's path may, and the job deletes both
before it starts.

Exits 0 when every step passed, 1 when a step failed and 2 on an unknown job.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

PYTHONS = ["python3", "/usr/bin/python3"]
KIT = "engine kit"
STUB = "stub game"

Step = tuple[str, "list[str] | Callable[[], int]"]


def clear_kit() -> int:
    """Delete the last run's kit and stub game, since engine_kit.py won't write over a kit."""
    for path in (KIT, STUB):
        shutil.rmtree(path, ignore_errors=True)
    return 0


def link_stub() -> int:
    """Link the kit against stub tables that stand in for the recompiler's output, so a
    framework missing from game_libs.txt fails the link."""
    gen = Path(STUB, "gen")
    try:
        gen.mkdir(parents=True, exist_ok=True)
        shutil.copy("tests/kit/stub_tables.c", gen)
        sdk = subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True, text=True,
                             check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"couldn't set up {STUB}: {e}", flush=True)
        return 1
    kit = os.path.abspath(KIT)
    code = subprocess.run(["make", "-f", f"{kit}/Makefile", f"KIT={kit}", f"SDK={sdk}",
                           "CC=clang", "CXX=clang++"], cwd=STUB).returncode
    if code:
        return code
    if not os.access(Path(STUB, "dragoon"), os.X_OK):
        print(f"{STUB}/dragoon wasn't linked", flush=True)
        return 1
    return 0


def launcher_steps() -> list[Step]:
    steps: list[Step] = [(f"Launcher tool tests ({py})",
                          [py, "-m", "unittest", "discover", "-s", "launcher/tools", "-p", "test_*.py"])
                         for py in PYTHONS]
    if Path("launcher/Package.swift").exists():
        steps.append(("Swift tests", ["python3", "launcher/tools/swift_test.py"]))
    return steps


JOBS: dict[str, Callable[[], list[Step]]] = {
    "tools": lambda: [step for py in PYTHONS for step in (
        (f"No game data in the tree ({py})", [py, "tools/check_no_game_data.py"]),
        (f"Tool tests ({py})", [py, "-m", "unittest", "discover", "-s", "tools", "-p", "test_*.py"]),
    )],
    "macos": lambda: [
        ("Configure without a disc", ["cmake", "-S", ".", "-B", "build-nodisc", "-G", "Ninja",
                                      "-DDRAGOON_TESTS=ON"]),
        ("Compile the runtime", ["ninja", "-C", "build-nodisc", "runtime_check"]),
        ("Engine and src/ unit tests", ["ninja", "-C", "build-nodisc", "unit"]),
    ],
    "kit": lambda: [
        ("Delete the last kit", clear_kit),
        ("Configure without a disc", ["cmake", "-S", ".", "-B", "build-kit", "-G", "Ninja",
                                      "-DCMAKE_BUILD_TYPE=RelWithDebInfo",
                                      "-DCMAKE_OSX_DEPLOYMENT_TARGET=14.0", "-DGAME_ISO="]),
        ("Compile the engine and SDL", ["ninja", "-C", "build-kit", "runtime_check", "SDL3-static"]),
        ("Make the kit", ["python3", "tools/engine_kit.py", "--build", "build-kit", "--out",
                          os.path.abspath(KIT), "--strip-debug"]),
        ("Link the kit against stub tables", link_stub),
    ],
    "launcher": launcher_steps,
}


def run(steps: list[Step], job: str) -> bool:
    for name, step in steps:
        print(f"== {job}: {name}", flush=True)
        code = step() if callable(step) else subprocess.run(step).returncode
        if code:
            print(f"== {job}: {name} exited {code}", flush=True)
            return False
    return True


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("jobs", nargs="*", metavar="JOB")
    jobs = p.parse_args(argv).jobs
    unknown = [j for j in jobs if j not in JOBS]
    if unknown:
        print(f"ci.py: no job {', '.join(unknown)}; the jobs are {', '.join(JOBS)}", file=sys.stderr)
        return 2
    for job in jobs or list(JOBS):
        if not run(JOBS[job](), job):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
