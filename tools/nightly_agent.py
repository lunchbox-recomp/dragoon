"""What launchd job runs the nightly? `plist(root, python)` is the job: `tools/nightly.py run` in
ROOT at 01:30 every day, with the system's PATH, its output appended to
build/nightly/launchd.log. `install(directory, root, python)` writes it as LABEL.plist in
DIRECTORY, ~/Library/LaunchAgents by default, and `uninstall` removes that file. Neither loads
or unloads the job, which `launchctl bootstrap gui/UID FILE` and `launchctl bootout gui/UID
FILE` do. launchd also loads every file in ~/Library/LaunchAgents at the next login. It has no
command line; nightly.py install-agent and uninstall-agent call it.
"""
from __future__ import annotations

import plistlib
from pathlib import Path

LABEL = "org.lunchbox-recomp.dragoon.nightly"
AGENTS = Path.home() / "Library" / "LaunchAgents"
HOUR, MINUTE = 1, 30
PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def plist(root: Path, python: str) -> bytes:
    log = str(root / "build" / "nightly" / "launchd.log")
    return plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": [python, str(root / "tools" / "nightly.py"), "run"],
        "WorkingDirectory": str(root),
        "EnvironmentVariables": {"PATH": PATH},
        "StartCalendarInterval": {"Hour": HOUR, "Minute": MINUTE},
        "StandardOutPath": log,
        "StandardErrorPath": log,
    })


def path(directory: Path = AGENTS) -> Path:
    return directory / f"{LABEL}.plist"


def install(root: Path, python: str, directory: Path = AGENTS) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (root / "build" / "nightly").mkdir(parents=True, exist_ok=True)
    target = path(directory)
    target.write_bytes(plist(root, python))
    return target


def uninstall(directory: Path = AGENTS) -> bool:
    """Remove the job's file. False when there was none."""
    target = path(directory)
    if not target.exists():
        return False
    target.unlink()
    return True
