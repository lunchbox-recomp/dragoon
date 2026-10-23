"""What a directory tree holds, without following a symlink."""
from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple


class Tree(NamedTuple):
    files: dict[str, int]  # each regular file's path and size
    links: dict[str, str]  # each symlink's path and the target it holds
    empty_dirs: list[str]  # sorted, and never the root
    others: list[str]  # sorted pipes, sockets and devices


def scan(root: Path) -> Tree:
    """Every entry under ROOT by its /-separated path relative to ROOT."""
    files: dict[str, int] = {}
    links: dict[str, str] = {}
    empty: list[str] = []
    others: list[str] = []

    def walk(directory: str, prefix: str) -> None:
        count = 0
        for entry in os.scandir(directory):
            count += 1
            rel = prefix + entry.name
            if entry.is_symlink():
                links[rel] = os.readlink(entry.path)
            elif entry.is_dir(follow_symlinks=False):
                walk(entry.path, rel + "/")
            elif entry.is_file(follow_symlinks=False):
                files[rel] = entry.stat(follow_symlinks=False).st_size
            else:
                others.append(rel)
        if count == 0 and prefix:
            empty.append(prefix.rstrip("/"))

    walk(str(root), "")
    return Tree(files, links, sorted(empty), sorted(others))
