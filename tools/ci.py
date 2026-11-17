#!/usr/bin/env python3
"""Run the steps CI runs, on a runner or on your own Mac.

Usage: tools/ci.py [JOB ...]

Run it from the repository's root, with the gcn-recomp submodule checked out. With no JOB it
runs every job: tools, macos, kit, launcher and app. A job's steps run in order, and the first
one that fails stops the run. .github/workflows/ci.yml installs what a runner lacks and runs
each job by name, so a step changes here and nowhere else.

The kit job leaves the engine kit in `engine kit/` and links it against stub tables in
`stub game/`. Both names have a space, as a player's path may, and the job deletes both
before it starts.

The app job takes the kit from `engine kit/`, where the kit job or the workflow's download
of its artifact left it, and works in `app job/`, which it deletes before it starts. It builds
the launcher with `swift build -c release`, exports a source snapshot and builds the unsigned
app with make_app.py. It zips the app with `ditto -c -k --keepParent` into
`app job/Dragoon.zip`, unzips that into a fresh directory, runs check_bundle.py on the copy and
links the copy's own kit against the stub tables, as a release's zip would be checked.

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
APP_JOB = "app job"
SNAPSHOT = f"{APP_JOB}/source"
BUILT = f"{APP_JOB}/build"
ZIP = f"{APP_JOB}/Dragoon.zip"
UNZIPPED = f"{APP_JOB}/unzipped"
APP_STUB = f"{APP_JOB}/stub game"
LAUNCHER = "launcher/.build/release/Dragoon"  # what `swift build -c release` makes
APP_VERSION = "0.0.0"  # CI's app is never released, so it has no version of its own

Step = tuple[str, "list[str] | Callable[[], int]"]


def clear_kit() -> int:
    """Delete the last run's kit and stub game, since engine_kit.py won't write over a kit."""
    for path in (KIT, STUB):
        shutil.rmtree(path, ignore_errors=True)
    return 0


def link_stub(kit: str = KIT, stub: str = STUB) -> int:
    """Link KIT, in a new directory STUB, against stub tables that stand in for the
    recompiler's output, so a framework missing from game_libs.txt fails the link."""
    gen = Path(stub, "gen")
    try:
        gen.mkdir(parents=True, exist_ok=True)
        shutil.copy("tests/kit/stub_tables.c", gen)
        sdk = subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True, text=True,
                             check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"couldn't set up {stub}: {e}", flush=True)
        return 1
    kit = os.path.abspath(kit)
    code = subprocess.run(["make", "-f", f"{kit}/Makefile", f"KIT={kit}", f"SDK={sdk}",
                           "CC=clang", "CXX=clang++"], cwd=stub).returncode
    if code:
        return code
    if not os.access(Path(stub, "dragoon"), os.X_OK):
        print(f"{stub}/dragoon wasn't linked", flush=True)
        return 1
    return 0


def clear_app() -> int:
    """Delete the last app job's work, since make_app.py won't write over an app."""
    shutil.rmtree(APP_JOB, ignore_errors=True)
    return 0


def link_app_stub() -> int:
    """Link the unzipped app's own kit against the stub tables, which shows the copy a player
    downloads still builds a game."""
    return link_stub(f"{UNZIPPED}/Dragoon.app/Contents/Resources/kit", APP_STUB)


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
                                      "-DDRAGOON_TESTS=ON", "-DGAME_ISO="]),
        ("Compile the runtime", ["ninja", "-C", "build-nodisc", "runtime_check"]),
        ("Engine and src/ unit tests", ["ninja", "-C", "build-nodisc", "unit"]),
    ],
    "kit": lambda: [
        ("Delete the last kit", clear_kit),
        ("Configure without a disc", ["cmake", "-S", ".", "-B", "build-kit", "-G", "Ninja",
                                      "-DCMAKE_BUILD_TYPE=RelWithDebInfo",
                                      "-DCMAKE_OSX_DEPLOYMENT_TARGET=14.0", "-DGAME_ISO="]),
        ("Compile the engine, Dear ImGui and SDL", ["ninja", "-C", "build-kit", "runtime_check", "gcn_imgui",
                                                    "SDL3-static"]),
        ("Make the kit", ["python3", "tools/engine_kit.py", "--build", "build-kit", "--out",
                          os.path.abspath(KIT), "--strip-debug"]),
        ("Link the kit against stub tables", link_stub),
    ],
    "launcher": launcher_steps,
    "app": lambda: [
        ("Delete the last app", clear_app),
        ("Build the launcher", ["swift", "build", "-c", "release", "--package-path", "launcher"]),
        ("Export the source snapshot", ["python3", "tools/export_source.py", os.path.abspath(SNAPSHOT)]),
        ("Build the app", ["python3", "launcher/tools/make_app.py", "--out", os.path.abspath(BUILT),
                           "--version", APP_VERSION, "--launcher", LAUNCHER, "--kit", os.path.abspath(KIT),
                           "--source", os.path.abspath(SNAPSHOT)]),
        ("Zip the app", ["ditto", "-c", "-k", "--keepParent", f"{BUILT}/Dragoon.app", ZIP]),
        ("Unzip it into a fresh directory", ["ditto", "-x", "-k", ZIP, UNZIPPED]),
        ("Check the unzipped app", ["python3", "tools/check_bundle.py", f"{UNZIPPED}/Dragoon.app",
                                    "--commit", "HEAD"]),
        ("Link the unzipped app's kit against stub tables", link_app_stub),
    ],
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
