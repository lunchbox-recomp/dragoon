#!/usr/bin/env python3
"""Download the launcher's pinned third-party pieces, check each one's SHA-256 and extract it.

Usage: fetch_third_party.py --dest DIR [--pins FILE] [--gcn-recomp DIR] [NAME ...]

This is the only tool that downloads anything. launcher/third_party.txt (or --pins) pins CMake
and Ninja by version, URL and SHA-256. SDL's pin is read from the sdl3 FetchContent_Declare in
--gcn-recomp's CMakeLists.txt (by default this checkout's gcn-recomp/) with tools/sdl_source.py,
so its hash has one home. With NAME arguments, such as cmake ninja, only those are fetched,
and SDL's pin is read only when sdl3 is one of them. DIR is where make_app.py looks:
  <archive>          each download, kept so a rerun that finds it intact downloads nothing
  <name>-<version>/  what an archive holds, made afresh on every run. SDL has none, since its
                     tarball ships whole and the launcher extracts it itself after hashing it
https: and file: URLs are allowed. A download whose SHA-256 differs from its pin is deleted
and nothing is extracted. Extraction checks every member before it writes anything: only
files, directories and symlinks, no absolute path or .. and no symlink that leads out of the
tree. The tree is made beside its final name and renamed into place once it is whole.

Exits 0 when every item is fetched and extracted, 1 when a download, a hash or an extraction
failed, which stops the run, and 2 on a bad argument or pins file.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import stat
import sys
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, NamedTuple
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import export_source  # noqa: E402
import sdl_source  # noqa: E402

PINS = ROOT / "launcher" / "third_party.txt"
GCN_RECOMP = ROOT / "gcn-recomp"
SDL = "sdl3"
TIMEOUT_SECONDS = 60
SCHEMES = ("https", "file")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_NAME = re.compile(r"[a-z0-9][a-z0-9_.]*")


@dataclass(frozen=True)
class Item:
    name: str
    version: str
    url: str
    sha256: str
    extract: bool = True

    @property
    def archive(self) -> str:
        """The file name the download is kept under, the URL's last path segment."""
        return PurePosixPath(unquote(urlsplit(self.url).path)).name

    @property
    def folder(self) -> str:
        return f"{self.name}-{self.version}"

    def __str__(self) -> str:
        return f"{self.name} {self.version}"


class Entry(NamedTuple):
    """A member of an archive: its name, 'file', 'dir' or 'link', its mode and a function that
    reads its data, or a link's target."""
    name: str
    kind: str
    mode: int
    read: Callable[[], bytes]


def archive_kind(name: str) -> str:
    """'tar' for a .tar.gz, 'zip' for a .zip, otherwise ''."""
    return "tar" if name.endswith(".tar.gz") else "zip" if name.endswith(".zip") else ""


def parse_pins(text: str) -> list[Item]:
    """The items of a third_party.txt: one 'name version url sha256' per line, with blank lines
    and # comment lines left out. Raises ValueError naming the line that is malformed."""
    items: list[Item] = []
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 4:
            raise ValueError(f"line {n} isn't 'name version url sha256': {line!r}")
        item = Item(*fields)
        if not _NAME.fullmatch(item.name) or item.name == SDL or item.name in [i.name for i in items]:
            raise ValueError(f"line {n}: {item.name!r} isn't a new lower-case name")
        if urlsplit(item.url).scheme not in SCHEMES or not archive_kind(item.archive):
            raise ValueError(f"line {n}: {item.url!r} isn't an https: or file: URL of a "
                             ".tar.gz or .zip")
        if not _SHA256.fullmatch(item.sha256):
            raise ValueError(f"line {n}: {item.sha256!r} isn't a lower-case SHA-256")
        items.append(item)
    return items


def sdl_item(cmake_text: str) -> Item:
    """SDL's item, from gcn-recomp's CMakeLists.txt. It is kept as a tarball, not extracted."""
    pin = sdl_source.pin(cmake_text)
    version = pin.top.partition("-")[2] or pin.top
    return Item(SDL, version, pin.url, pin.sha256, extract=False)


def download(item: Item, dest: Path) -> tuple[Path, bool]:
    """Put ITEM's archive in DEST: (path, whether it was already there and intact). Raises
    ValueError, having deleted what it wrote, when the download fails or hashes wrong."""
    path = dest / item.archive
    if path.is_file() and export_source.sha256_file(path) == item.sha256:
        return path, True
    part = dest / (item.archive + ".part")
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(item.url, timeout=TIMEOUT_SECONDS) as response, \
                part.open("wb") as out:
            for block in iter(lambda: response.read(1 << 20), b""):
                digest.update(block)
                out.write(block)
        if digest.hexdigest() != item.sha256:
            raise ValueError(f"{item.url} has SHA-256 {digest.hexdigest()}, but the pin says "
                             f"{item.sha256}")
        os.replace(part, path)
    except OSError as e:  # urllib's errors are OSErrors too
        raise ValueError(f"can't download {item.url}: {e}") from None
    finally:
        part.unlink(missing_ok=True)
    return path, False


def _inside(name: str, root_ok: bool = False) -> str:
    """NAME, which mustn't be absolute or hold .., since it names a place in a tree. It can be
    empty, as ./ is, only when ROOT_OK."""
    parts = PurePosixPath(name).parts
    if name.startswith("/") or ".." in parts or not (parts or root_ok):
        raise ValueError(f"{name!r} is outside the tree it is extracted into")
    return name


def _tar_entry(tar: tarfile.TarFile, m: tarfile.TarInfo) -> Entry:
    if m.isdir():
        return Entry(_inside(m.name, root_ok=True), "dir", m.mode, lambda: b"")
    if m.isfile():
        return Entry(_inside(m.name), "file", m.mode, lambda: tar.extractfile(m).read())  # type: ignore
    if m.issym():
        return Entry(_inside(m.name), "link", m.mode, m.linkname.encode)
    raise ValueError(f"{m.name!r} isn't a file, a directory or a symlink")


def _zip_entry(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> Entry:
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise ValueError(f"{info.filename!r} is a symlink, which a zip can't hold here")
    return Entry(_inside(info.filename, root_ok=info.is_dir()),
                 "dir" if info.is_dir() else "file", mode, lambda: zf.read(info))


def _write(entries: list[Entry], dest: Path) -> None:
    """Make DEST from ENTRIES, which have all been checked. Files and directories go first and
    symlinks last, so nothing is written through one. Once all exist, each must resolve to
    somewhere inside DEST, or ValueError names it."""
    dest.mkdir(parents=True)
    links = []
    for e in entries:
        target = dest.joinpath(*PurePosixPath(e.name).parts)
        if e.kind == "dir":
            target.mkdir(parents=True, exist_ok=True)
        elif e.kind == "file":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(e.read())
            target.chmod(0o755 if e.mode & 0o111 else 0o644)
        else:
            links.append((target, e.read().decode()))
    for target, to in links:
        target.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(to, target)
    inside = Path(os.path.realpath(dest))
    for target, to in links:
        if inside not in Path(os.path.realpath(target)).parents:
            raise ValueError(f"the symlink {target.relative_to(dest)} -> {to} leads out of the tree")


def extract(archive: Path, dest: Path) -> None:
    """Extract ARCHIVE, a .tar.gz or .zip, into DEST, which mustn't exist yet. Raises ValueError,
    before writing anything, for a member that isn't a file, a directory or a symlink or whose
    name leaves DEST, and after writing for a symlink that leads out of DEST. The caller removes
    DEST then."""
    if archive_kind(archive.name) == "tar":
        with tarfile.open(archive, "r:gz") as tar:
            _write([_tar_entry(tar, m) for m in tar.getmembers()], dest)
    else:
        with zipfile.ZipFile(archive) as zf:
            _write([_zip_entry(zf, i) for i in zf.infolist()], dest)


def fetch(item: Item, dest: Path) -> str:
    """Download ITEM into DEST and extract it, unless it ships whole. Returns what happened."""
    path, cached = download(item, dest)
    got = f"{'cached' if cached else 'downloaded'} {path.name}, SHA-256 matches"
    if not item.extract:
        return got
    tree, partial = dest / item.folder, dest / (item.folder + ".partial")
    shutil.rmtree(partial, ignore_errors=True)
    try:
        extract(path, partial)
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as e:
        shutil.rmtree(partial, ignore_errors=True)
        raise ValueError(f"can't extract {path.name}: {e}") from None
    shutil.rmtree(tree, ignore_errors=True)
    os.replace(partial, tree)
    return f"{got}, extracted to {tree}"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", metavar="NAME", help="what to fetch, by default everything")
    ap.add_argument("--dest", type=Path, required=True, help="where downloads and trees go")
    ap.add_argument("--pins", type=Path, default=PINS, help="default %(default)s")
    ap.add_argument("--gcn-recomp", type=Path, default=GCN_RECOMP,
                    help="the checkout whose CMakeLists.txt pins SDL, default %(default)s")
    a = ap.parse_args(argv)
    try:
        items = parse_pins(a.pins.read_text())
    except (OSError, ValueError) as e:
        print(f"fetch_third_party.py: {a.pins}: {e}", file=sys.stderr)
        return 2
    unknown = sorted(set(a.names) - {i.name for i in items} - {SDL})
    if unknown:
        known = ", ".join([i.name for i in items] + [SDL])
        print(f"fetch_third_party.py: no pin named {', '.join(unknown)}. The pins are {known}",
              file=sys.stderr)
        return 2
    if not a.names or SDL in a.names:
        try:
            items.append(sdl_item((a.gcn_recomp / "CMakeLists.txt").read_text()))
        except (OSError, ValueError) as e:
            print(f"fetch_third_party.py: SDL's pin: {e}. Name the items to fetch instead, or "
                  "check out gcn-recomp or point --gcn-recomp at one", file=sys.stderr)
            return 2
    a.dest.mkdir(parents=True, exist_ok=True)
    for item in items:
        if a.names and item.name not in a.names:
            continue
        try:
            result = fetch(item, a.dest)
        except ValueError as e:
            print(f"fetch_third_party.py: {item}: {e}", file=sys.stderr)
            return 1
        print(f"{item}: {result}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
