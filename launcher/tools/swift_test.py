#!/usr/bin/env python3
"""Run the launcher's Swift tests on a Mac that has only the Command Line Tools.

Usage: swift_test.py [ARGUMENT ...]

Runs `swift test --package-path launcher` and hands it every ARGUMENT, such as `--filter NAME`,
and exits with its status. Every ARGUMENT goes to swift, `--help` included, so this tool has no
help of its own. A signal that ends swift counts as 128 plus its number.

With Xcode selected, that's all it does. With the Command Line Tools selected, `swift test`
alone stops at `no such module 'Testing'`, because the tools keep Testing.framework in
Library/Developer/Frameworks, where the compiler doesn't look. With only -F, the test runner
can't load that framework. With -F and an rpath to it, the runner can't load
lib_TestingInterop.dylib. So when `xcode-select -p` names a directory that holds
Library/Developer/Frameworks/Testing.framework and has no Platforms directory beside it, as the
Command Line Tools do and Xcode's doesn't, the tool adds these for that directory, whatever the
directory is called:
  -Xswiftc -F -Xswiftc DEV/Library/Developer/Frameworks
  -Xlinker -rpath -Xlinker DEV/Library/Developer/Frameworks
  -Xlinker -rpath -Xlinker DEV/Library/Developer/usr/lib
They stay out of Package.swift, since unsafeFlags there would bake one Mac's paths into the
package. If xcode-select fails, it adds nothing and swift reports what's missing.

The swift command prints on stderr with a "+ " before it runs, and xcode-select prints
nothing. Exits 2 when swift can't be started.
"""
from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional

XCODE_SELECT = "/usr/bin/xcode-select"
SWIFT = "swift"
LAUNCHER = Path(__file__).resolve().parents[1]
PLATFORMS = "Platforms"  # Xcode's developer directory has one, and the Command Line Tools don't
FRAMEWORKS = "Library/Developer/Frameworks"
TESTING = f"{FRAMEWORKS}/Testing.framework"
LIBS = "Library/Developer/usr/lib"


def selected_developer_dir() -> Optional[Path]:
    """What `xcode-select -p` prints, or None when it can't say."""
    try:
        done = subprocess.run([XCODE_SELECT, "-p"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True)
    except OSError:
        return None
    path = done.stdout.strip()
    return Path(path) if done.returncode == 0 and path else None


def needs_flags(developer: Path) -> bool:
    """Does DEVELOPER hold Testing.framework where the Command Line Tools keep it and no
    Platforms directory, which Xcode's developer directory has?"""
    return (developer / TESTING).is_dir() and not (developer / PLATFORMS).is_dir()


def testing_flags(developer: Path) -> list[str]:
    """The flags that let swift build against and load the Command Line Tools' Swift Testing."""
    frameworks, libs = str(developer / FRAMEWORKS), str(developer / LIBS)
    return ["-Xswiftc", "-F", "-Xswiftc", frameworks,
            "-Xlinker", "-rpath", "-Xlinker", frameworks,
            "-Xlinker", "-rpath", "-Xlinker", libs]


def command(arguments: list[str], developer: Optional[Path]) -> list[str]:
    """The swift test command for ARGUMENTS with the DEVELOPER directory selected."""
    flags = testing_flags(developer) if developer and needs_flags(developer) else []
    return [SWIFT, "test", "--package-path", str(LAUNCHER), *flags, *arguments]


def main(argv: list[str]) -> int:
    cmd = command(argv, selected_developer_dir())
    print("+ " + shlex.join(cmd), file=sys.stderr, flush=True)
    try:
        status = subprocess.run(cmd).returncode
    except OSError as e:
        print(f"swift_test.py: can't run {SWIFT}: {e}", file=sys.stderr)
        return 2
    return 128 - status if status < 0 else status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
