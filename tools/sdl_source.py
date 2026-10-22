"""SDL's source for a build with no download: gcn-recomp's pin and a checked extraction.

gcn-recomp's CMakeLists.txt pins SDL in its sdl3 FetchContent_Declare by URL and SHA-256, and
the hash lives only there. The launcher carries the release tarball, checks it against that
pin and extracts it itself, then points FetchContent at the result.
"""
from __future__ import annotations

import re
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
_SUFFIX = ".tar.gz"


@dataclass(frozen=True)
class Pin:
    url: str
    sha256: str

    @property
    def top(self) -> str:
        """The directory the release tarball holds, SDL3-3.4.18 for .../SDL3-3.4.18.tar.gz."""
        return self.url.rsplit("/", 1)[-1][:-len(_SUFFIX)]


def pin(cmake_text: str) -> Pin:
    """The URL and SHA-256 of the sdl3 FetchContent_Declare in gcn-recomp's CMakeLists.txt."""
    declare = re.search(r"\bFetchContent_Declare\s*\(\s*sdl3\s([^)]*)\)", cmake_text)
    url = declare and re.search(r"\bURL\s+(\S+)", declare.group(1))
    sha = declare and re.search(r"\bURL_HASH\s+SHA256=([0-9a-f]{64})\s", declare.group(1) + "\n")
    if not (url and sha and url.group(1).endswith(_SUFFIX)):
        raise ValueError("gcn-recomp's CMakeLists.txt has no sdl3 FetchContent_Declare with a "
                         ".tar.gz URL and a SHA256 URL_HASH")
    return Pin(url.group(1), sha.group(1))


def _check(member: tarfile.TarInfo) -> None:
    parts = PurePosixPath(member.name).parts
    if member.name.startswith("/") or ".." in parts:
        raise ValueError(f"SDL's tarball has a member outside its directory: {member.name}")
    if not (member.isfile() and parts or member.isdir()):
        raise ValueError(f"SDL's tarball has a member that isn't a file or directory: {member.name}")


def extract(tarball: Path, dest: Path) -> None:
    """Extract TARBALL into DEST, which mustn't exist yet.

    Every member is checked before anything is written. Only regular files and directories
    are allowed, and each must stay inside DEST, or ValueError names the first that doesn't.
    The tools' Python 3.9 has no tarfile extraction filter, so the checks are made here.
    """
    with tarfile.open(tarball, "r:gz") as tar:
        members = tar.getmembers()
        for m in members:
            _check(m)
        dest.mkdir(parents=True)
        for m in members:
            target = dest.joinpath(*PurePosixPath(m.name).parts)
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tar.extractfile(m)
            with src, target.open("wb") as out:
                shutil.copyfileobj(src, out)
            target.chmod(0o755 if m.mode & 0o111 else 0o644)
