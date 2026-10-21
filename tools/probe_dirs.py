"""What the hash tools do with a probe run's directory in build/probe/."""
from __future__ import annotations

import shutil
import time
from pathlib import Path


def trash(directory: Path) -> None:
    """Move DIRECTORY into ~/.Trash under a time-stamped name, so its game data isn't kept."""
    dest = Path.home() / ".Trash" / f"{directory.name}-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.move(str(directory), str(dest))
