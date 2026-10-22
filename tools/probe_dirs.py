"""What the hash tools and the scorecard do with probe.sh and a probe run's directory in build/probe/."""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path


def trash(directory: Path) -> None:
    """Move DIRECTORY into ~/.Trash under a time-stamped name, so its game data isn't kept."""
    dest = Path.home() / ".Trash" / f"{directory.name}-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.move(str(directory), str(dest))


def run_probe(args: list[str], cwd: Path, what: str, env: dict[str, str] | None = None) -> None:
    """Run the probe.sh command line ARGS from CWD with its output dropped. A nonzero exit is a
    ValueError that starts with WHAT."""
    try:
        subprocess.run(args, check=True, cwd=cwd, stdout=subprocess.DEVNULL, env=env)
    except subprocess.CalledProcessError as e:
        raise ValueError(f"{what}: probe.sh exited {e.returncode}") from None
