"""May a nightly run start, and on what? nightly.py asks before it plays anything.

  take_lock     an exclusive flock on build/nightly/run.lock, held while the run lives, so a
                second run in the same tree refuses instead of deleting the first one's
                build/probe/ runs
  games_running the dragoon and dragoon_bench processes pgrep finds, since a run plays one
                game at a time and a game already playing would be a second
  in_window     whether a launchd run started between 01:00 and 06:00. One that missed 01:30
                asleep starts when the Mac wakes, perhaps at noon, and a 3-hour run then is
                skipped
  update        for the launchd run's own clone: a clean tree on main, fast-forwarded to
                origin/main with its submodule, then `dragoon` and `dragoon_bench` built by
                name with the cmake the build was configured with. Anything else refuses

Each raises Refused or returns what it found. It has no command line.
"""
from __future__ import annotations

import fcntl
import os
import re
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

LOCK = "run.lock"  # under build/nightly/
GAMES = ("dragoon", "dragoon_bench")
WINDOW = (1, 6)  # the hours a launchd run may start in, from 01:00 to before 06:00
TARGETS = ("dragoon", "dragoon_bench")
CMAKE = re.compile(r"^CMAKE_COMMAND:INTERNAL=(.+)$", re.M)

Run = Callable[[Sequence[str]], subprocess.CompletedProcess]


class Refused(Exception):
    pass


def take_lock(nightly: Path) -> int:
    """The open lock file's descriptor, locked, which the caller keeps open for the run's life."""
    nightly.mkdir(parents=True, exist_ok=True)
    fd = os.open(nightly / LOCK, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise Refused(f"another nightly run holds {nightly / LOCK}") from None
    return fd


def games_running(pgrep: Sequence[str] = ("pgrep", "-x")) -> list[str]:
    """The names in GAMES that a process has, by PGREP NAME, which exits 0 on a match."""
    return [name for name in GAMES
            if subprocess.run([*pgrep, name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0]


def in_window(hour: int) -> bool:
    return WINDOW[0] <= hour < WINDOW[1]


def _run(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), capture_output=True, text=True)


def _git(root: Path, run: Run, *args: str) -> str:
    done = run(["git", "-C", str(root), *args])
    if done.returncode != 0:
        raise Refused(f"git {' '.join(args)} exited {done.returncode}: {(done.stderr or '').strip()}")
    return (done.stdout or "").strip()


def _clean(root: Path, run: Run) -> None:
    dirty = _git(root, run, "status", "--porcelain")
    if dirty:
        raise Refused(f"{root} has changes: {dirty.splitlines()[0]}")


def checked(root: Path, run: Run = _run) -> str:
    """ROOT's HEAD, when its tree is clean and HEAD is origin/main. Refused otherwise."""
    _clean(root, run)
    head, main = _git(root, run, "rev-parse", "HEAD"), _git(root, run, "rev-parse", "origin/main")
    if head != main:
        raise Refused(f"{root} is at {head[:7]}, not origin/main {main[:7]}")
    return head


def cmake_command(build: Path) -> str:
    try:
        m = CMAKE.search((build / "CMakeCache.txt").read_text(errors="replace"))
    except OSError:
        m = None
    if m is None:
        raise Refused(f"{build} isn't a configured build: no CMAKE_COMMAND in its CMakeCache.txt")
    return m[1].strip()


def update(root: Path, run: Run = _run, say: Callable[[str], None] = print) -> str:
    """Fast-forward ROOT, a clean clone on main, to origin/main with its submodule and build the
    game. Returns the commit built."""
    _clean(root, run)
    branch = _git(root, run, "rev-parse", "--abbrev-ref", "HEAD")
    if branch != "main":
        raise Refused(f"{root} is on {branch}, not main")
    _git(root, run, "fetch", "--quiet", "origin")
    _git(root, run, "merge", "--ff-only", "--quiet", "origin/main")
    _git(root, run, "submodule", "update", "--init", "--quiet")
    head = checked(root, run)
    build = root / "build"
    done = run([cmake_command(build), "--build", str(build), "--target", *TARGETS])
    if done.returncode != 0:
        tail = (done.stdout or "").strip().splitlines()[-1:] or [""]
        raise Refused(f"building {' and '.join(TARGETS)} exited {done.returncode}: {tail[0]}")
    say(f"updated {root} to {head[:7]} and built {' and '.join(TARGETS)}")
    return head
