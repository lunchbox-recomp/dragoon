"""What the hash tools and the scorecard do with probe.sh: run it, delete a probe run's directory in
build/probe/, and read the N of a --slow=N."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from routes import FRAME


def slow_factor(text: str) -> int:
    """The N of a --slow=N, which multiplies a route's seconds. TEXT has to be a whole number
    from 1, the rule for a frame number, or it's a ValueError that names it."""
    if not FRAME.fullmatch(text):
        raise ValueError(f"--slow={text} isn't a whole number from 1")
    return int(text)


def remove_run(directory: Path) -> None:
    """Delete DIRECTORY and everything in it, so its game data isn't kept. A link inside is
    unlinked and what it points at stays. A DIRECTORY that's itself a link is a ValueError and
    nothing changes. One that's missing, or a file that can't be deleted, is an OSError."""
    if directory.is_symlink():
        raise ValueError(f"{directory}: is a link, not a probe run's directory")
    shutil.rmtree(directory)


class ProbeFailed(ValueError):
    """A probe.sh run that exited nonzero. RETURNCODE is its status."""

    def __init__(self, message: str, returncode: int) -> None:
        super().__init__(message)
        self.returncode = returncode


def run_probe(args: list[str], cwd: Path, what: str, env: dict[str, str] | None = None) -> None:
    """Run the probe.sh command line ARGS from CWD with its output dropped. A nonzero exit is a
    ProbeFailed, a ValueError that starts with WHAT."""
    try:
        subprocess.run(args, check=True, cwd=cwd, stdout=subprocess.DEVNULL, env=env)
    except subprocess.CalledProcessError as e:
        raise ProbeFailed(f"{what}: probe.sh exited {e.returncode}", e.returncode) from None
