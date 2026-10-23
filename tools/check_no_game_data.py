#!/usr/bin/env python3
"""Is anything from a disc tracked by git?

Usage: check_no_game_data.py

Checks every tracked file and prints one "game data tracked: PATH" line per path that looks
like game data:
  - a disc image or executable by suffix (.iso, .gcm, .dol, ...), a .raw memory card or audio
    recording, a .wav recording (anywhere, like .raw) or a .bin shader cache or key list
  - anything under a top-level build*/ or rom/ (except rom/README.md), or under a saves/
    at any depth
  - a frame dump (frame_NNNNN.png or output_NNNNN.png), stdout.txt or panic.txt anywhere
Other .png files are fine. The rules mirror .gitignore, so a file added with `git add -f`
still fails CI. It prints nothing when the tree is clean.

Exits 0 when nothing is tracked that shouldn't be, 1 when something is, 2 when git fails.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path, PurePosixPath

from frame_dumps import FRAME_NAME, OUTPUT_NAME

ROOT = Path(__file__).resolve().parents[1]
DATA_SUFFIXES = (".iso", ".gcm", ".ciso", ".rvz", ".gcz", ".wbfs", ".dol", ".rel", ".gci", ".raw",
                 ".wav", ".bin")
LOG_NAMES = ("stdout.txt", "panic.txt")


def is_frame_dump(name: str) -> bool:
    return bool(FRAME_NAME.fullmatch(name) or OUTPUT_NAME.fullmatch(name))


def is_game_data(path: str) -> bool:
    parts = PurePosixPath(path).parts
    base = parts[-1]
    if path.lower().endswith(DATA_SUFFIXES) or base in LOG_NAMES or is_frame_dump(base):
        return True
    if "saves" in parts[:-1]:
        return True
    if len(parts) > 1:
        return parts[0].startswith("build") or (parts[0] == "rom" and path != "rom/README.md")
    return False


def violations(paths: list[str]) -> list[str]:
    return [p for p in paths if is_game_data(p)]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args(argv)
    try:
        tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True,
                                 text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"git ls-files failed: {getattr(e, 'stderr', None) or e}", file=sys.stderr)
        return 2
    bad = violations(tracked.splitlines())
    for p in bad:
        print(f"game data tracked: {p}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
