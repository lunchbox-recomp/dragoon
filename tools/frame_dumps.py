"""The frames tools/probe.sh dumps: frame_NNNNN.png, NNNNN the presented frame's number."""
from __future__ import annotations

import re
from pathlib import Path

FRAME_NAME = re.compile(r"frame_(\d+)\.png")


def frame_files(directory: Path) -> dict[int, Path]:
    return {int(m[1]): p for p in directory.iterdir() if (m := FRAME_NAME.fullmatch(p.name))}
