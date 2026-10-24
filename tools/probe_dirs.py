"""What the hash tools and the scorecard do with probe.sh and a probe run's directory in build/probe/."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def remove_run(directory: Path) -> None:
    """Delete DIRECTORY and everything in it, so its game data isn't kept. A link inside is
    unlinked and what it points at stays. A DIRECTORY that's itself a link is a ValueError and
    nothing changes. One that's missing, or a file that can't be deleted, is an OSError."""
    if directory.is_symlink():
        raise ValueError(f"{directory}: is a link, not a probe run's directory")
    shutil.rmtree(directory)


def run_probe(args: list[str], cwd: Path, what: str, env: dict[str, str] | None = None) -> None:
    """Run the probe.sh command line ARGS from CWD with its output dropped. A nonzero exit is a
    ValueError that starts with WHAT."""
    try:
        subprocess.run(args, check=True, cwd=cwd, stdout=subprocess.DEVNULL, env=env)
    except subprocess.CalledProcessError as e:
        raise ValueError(f"{what}: probe.sh exited {e.returncode}") from None
