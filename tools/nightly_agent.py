"""What launchd job runs the nightly? `plist(clone)` is the job: CLONE's `tools/nightly.py run
--scheduled` at 01:30 every day under /usr/bin/python3, with the system's PATH, its output
appended to ~/Library/Logs/dragoon-nightly.log. CLONE is a clone of its own, dragoon-nightly
beside this one by default, which the scheduled run fast-forwards to origin/main and builds,
so the job never plays a branch or an edit someone left in a working clone.

`install(job, directory)` writes it as LABEL.plist in DIRECTORY, ~/Library/LaunchAgents by
default, and `uninstall` removes that file. Neither loads or unloads the job, which `launchctl
bootstrap gui/UID FILE` and `launchctl bootout gui/UID FILE` do. launchd also loads every file in
~/Library/LaunchAgents at the next login. It has no command line; nightly.py install-agent and
uninstall-agent call it.
"""
from __future__ import annotations

import plistlib
from pathlib import Path

LABEL = "org.lunchbox-recomp.dragoon.nightly"
AGENTS = Path.home() / "Library" / "LaunchAgents"
LOG = Path.home() / "Library" / "Logs" / "dragoon-nightly.log"
CLONE = Path(__file__).resolve().parents[2] / "dragoon-nightly"
PYTHON = "/usr/bin/python3"  # the Command Line Tools' Python, which every tool here runs under
HOUR, MINUTE = 1, 30
PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def plist(clone: Path, python: str = PYTHON, log: Path = LOG) -> bytes:
    return plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": [python, str(clone / "tools" / "nightly.py"), "run", "--scheduled"],
        "WorkingDirectory": str(clone),
        "EnvironmentVariables": {"PATH": PATH},
        "StartCalendarInterval": {"Hour": HOUR, "Minute": MINUTE},
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
    })


def path(directory: Path = AGENTS) -> Path:
    return directory / f"{LABEL}.plist"


def install(job: bytes, directory: Path = AGENTS) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = path(directory)
    target.write_bytes(job)
    return target


def uninstall(directory: Path = AGENTS) -> bool:
    """Remove the job's file. False when there was none."""
    target = path(directory)
    if not target.exists():
        return False
    target.unlink()
    return True
