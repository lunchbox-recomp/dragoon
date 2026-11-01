#!/usr/bin/env python3
"""Which mods does a mods folder hold, and can the game be built with them?

Usage: mods.py check MODS --dol-sha1 SHA

Each folder in MODS whose name doesn't start with a dot is one mod. A mod's files/ folder
mirrors the disc's root, and its dol.txt is a patch list in the format of gcn-recomp's
docs/dol-patches.md, whose dol line has to name SHA, the game's DOL. Either may be missing, and
either name may come in any letter case. The other files beside dol.txt are the ones its
section lines may name, and in a mod without dol.txt they're left alone. Dotfiles and dot
folders are skipped everywhere, and a loose file in MODS isn't a mod.

check prints one JSON object with each mod's name, file count and bytes, in folder name order
ignoring case, and the digest. A mod holds the files under its files/, its dol.txt and the
other files beside that. The digest is the SHA-256 over each file a mod holds, by the mod's
name and its path in the mod, with its size and its SHA-256. It's "none" when no mod holds a
file, and a missing or empty MODS has no mods.

A refused mod prints one JSON object with the error, the mod and the path in it instead. Under
files/, or anywhere in a mod with a dol.txt, a mod is refused for a link, for anything that
isn't a file or a folder or that can't be read, and for a file of 4 GiB or more. A link or an
unreadable folder in place of the mod is refused too. Under files/ it's refused for a name
that isn't ASCII or holds a control character, and for a main.dol at the top. A dol.txt that's
over 1 MiB, isn't UTF-8 or doesn't start with a dol line naming SHA is refused too. So are two
files that are one disc path ignoring case, in one mod or two, and a file where another needs a
folder. A mod holding files or dol.txt in two letter cases is refused.

Exits 0, 1 for a refused mod and 2 on a bad argument or a MODS that can't be read.

prepare(), for the build, clones every mod's files into a new folder and runs gcn-recomp's
dol_patch.py and disc_overlay.py on the clones.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

import clone_file
from tool_env import tool_env

FILES = "files"
DOL_TXT = "dol.txt"
PATCHES = "patches"
BOOT_DOL = "main.dol"
MANIFEST = "disc-overlay.txt"
MAX_SIZE = 1 << 32  # FST sizes are 32 bits
LIST_MAX = 1 << 20  # dol_patch.py refuses a bigger patch list
CHUNK = 1 << 20
SHA1 = re.compile(r"[0-9a-f]{40}")
COMMENT = re.compile(r"(?:^|\s)#.*$")  # as dol_patch.py strips one
# dol_patch.py's refusal of a list, `patches/N/dol.txt:line: reason` or without the line.
LIST_SAID = re.compile(r"(patches/[0-9]+/)dol\.txt((?::[0-9]+)?): (.+)", re.S)
# The reasons disc_overlay.py gives after a path under its files folder.
OVERLAY_REASONS = ("is a directory on the disc, not a file", "is a file on the disc, not a directory",
                   "is a symbolic link", "has a name that isn't ASCII", "isn't a file or a folder")
CASE_TWINS = re.compile(r"matches .+ on the disc by case alone", re.S)


class ModError(ValueError):
    """A refused mod. MOD is its folder's name, PATH the file in it (empty for the folder
    itself, with a line number for a patch list) and WHY the reason."""

    def __init__(self, mod: str, path: str, why: str) -> None:
        super().__init__(f"{mod}/{path}: {why}" if path else f"{mod}: {why}")
        self.mod = mod
        self.path = path
        self.why = why


class PrepareError(RuntimeError):
    """A gcn-recomp tool failed for a reason that names no mod."""


@dataclass
class Mod:
    name: str
    files: dict[str, Path]  # disc path to host path, from files/
    dol: Optional[Path] = None  # dol.txt
    beside: dict[str, Path] = field(default_factory=dict)  # the other files beside dol.txt

    def held(self) -> list[tuple[str, Path]]:
        """Every file the mod holds, as (its path in the mod, host path), sorted by path."""
        held = [(f"{FILES}/{disc}", host) for disc, host in self.files.items()]
        if self.dol is not None:
            held.append((DOL_TXT, self.dol))
        held += self.beside.items()
        return sorted(held)


@dataclass
class Prepared:
    dol: Path  # the DOL to recompile, which the overlay boots
    manifest: Path
    digest: str  # of the clones


def _entries(folder: Path) -> list[os.DirEntry]:
    """FOLDER's entries but the dotfiles, sorted by name."""
    with os.scandir(folder) as it:
        return sorted((e for e in it if not e.name.startswith(".")), key=lambda e: e.name)


def _is_dir(mod: str, path: str, e: os.DirEntry) -> bool:
    """Whether E is a folder. A link, a file of 4 GiB or more and anything else are refused."""
    if e.is_symlink():
        raise ModError(mod, path, "is a link, and a mod can hold only files and folders")
    if e.is_dir(follow_symlinks=False):
        return True
    if not e.is_file(follow_symlinks=False):
        raise ModError(mod, path, "isn't a file or a folder")
    if e.stat(follow_symlinks=False).st_size >= MAX_SIZE:
        raise ModError(mod, path, "is 4 GiB or more, and a mod's files have to be smaller")
    return False


def _walk(mod: str, folder: Path, prefix: str, skip: tuple[str, ...] = ()) -> Iterator[tuple[str, Path]]:
    """Every file under FOLDER as (its path there, host path), but those under SKIP at the top.
    Each is opened, so one that can't be read is an OSError here."""
    todo = [""]
    while todo:
        rel = todo.pop()
        for e in _entries(folder / rel):
            path = f"{rel}/{e.name}" if rel else e.name
            if path in skip:
                continue
            if _is_dir(mod, prefix + path, e):
                todo.append(path)
            else:
                open(e.path, "rb").close()
                yield path, Path(e.path)


def _part(mod: str, entries: list[os.DirEntry], name: str) -> Optional[os.DirEntry]:
    """The entry called NAME in any letter case, or None. Two spellings of it are refused."""
    found = [e for e in entries if e.name.lower() == name]
    if len(found) > 1:
        raise ModError(mod, found[1].name, f"has the same name as {found[0].name} ignoring case, "
                                           "and a mod can hold only one of them")
    return found[0] if found else None


def _check_disc_path(mod: str, files: str, path: str) -> None:
    shown = f"{files}/{path}"
    if not path.isascii():
        raise ModError(mod, shown, "has a name that isn't ASCII, and the disc's file table takes "
                                   "only ASCII names")
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in path):
        raise ModError(mod, shown, "has a control character in its name")
    if path.lower() == BOOT_DOL:
        raise ModError(mod, shown, "is a whole DOL, and a mod changes the game's code with dol.txt")


def _check_dol_line(mod: str, path: Path, dol_sha1: str) -> None:
    """Refuse a patch list whose first line isn't a dol line naming DOL_SHA1."""
    with open(path, "rb") as f:
        raw = f.read(LIST_MAX + 1)
    if len(raw) > LIST_MAX:
        raise ModError(mod, path.name, "is more than 1 MiB, which a patch list can't be")
    try:
        text = raw.decode("utf-8-sig")
    except ValueError:
        raise ModError(mod, path.name, "isn't UTF-8 text") from None
    for n, line in enumerate(text.split("\n"), 1):
        words = COMMENT.sub("", line).split()
        if not words:
            continue
        if words[0] != "dol" or len(words) != 2:
            raise ModError(mod, f"{path.name}:{n}", "has to be the dol line naming the game's DOL")
        if not SHA1.fullmatch(words[1].lower()):
            raise ModError(mod, f"{path.name}:{n}", f"names {words[1]}, which isn't a SHA-1")
        if words[1].lower() != dol_sha1:
            raise ModError(mod, f"{path.name}:{n}", f"is for the DOL with SHA-1 {words[1].lower()}, "
                                                    f"not this game's {dol_sha1}")
        return
    raise ModError(mod, path.name, "has no dol line")


def _read_mod(name: str, folder: Path, dol_sha1: str) -> Mod:
    mod = Mod(name, {})
    try:
        entries = _entries(folder)
        files = _part(name, entries, FILES)
        if files is not None:
            if not _is_dir(name, files.name, files):
                raise ModError(name, files.name, "isn't a folder")
            for path, host in _walk(name, Path(files.path), f"{files.name}/"):
                _check_disc_path(name, files.name, path)
                mod.files[path] = host
        dol = _part(name, entries, DOL_TXT)
        if dol is not None:
            if _is_dir(name, dol.name, dol):
                raise ModError(name, dol.name, "isn't a file")
            mod.dol = Path(dol.path)
            _check_dol_line(name, mod.dol, dol_sha1)
            skip = tuple(e.name for e in (files, dol) if e is not None)
            mod.beside = dict(_walk(name, folder, "", skip))
    except OSError as e:
        where = os.path.relpath(e.filename, folder) if e.filename else ""
        raise ModError(name, "" if where == "." else where,
                       f"can't be read ({e.strerror or e})") from None
    return mod


def _refuse_shared_paths(mods: list[Mod]) -> None:
    """Refuse two files that are one disc path ignoring case, and a file where another needs a
    folder."""
    owner: dict[str, str] = {}  # each disc path in lower case, to the first file that has it
    for mod in mods:
        for disc in sorted(mod.files):
            first = owner.setdefault(disc.lower(), f"{mod.name}/{FILES}/{disc}")
            if first != f"{mod.name}/{FILES}/{disc}":
                raise ModError(mod.name, f"{FILES}/{disc}",
                               f"changes the same disc file as {first}, and only one of them can")
    for mod in mods:
        for disc in sorted(mod.files):
            parts = disc.split("/")
            for i in range(1, len(parts)):
                folder = "/".join(parts[:i])
                if folder.lower() in owner:
                    raise ModError(mod.name, f"{FILES}/{disc}",
                                   f"needs {FILES}/{folder} to be a folder, and "
                                   f"{owner[folder.lower()]} is a file")


def scan(mods: Path, dol_sha1: str) -> list[Mod]:
    """The mods in MODS, sorted by folder name ignoring case. A missing or empty folder gives
    []. A refused mod is a ModError, and a MODS that can't be read an OSError."""
    if not mods.exists():
        return []
    found = []
    for e in sorted(_entries(mods), key=lambda e: (e.name.lower(), e.name)):
        if e.is_symlink():
            raise ModError(e.name, "", "is a link, and a mod has to be a folder")
        if e.is_dir(follow_symlinks=False):
            found.append(_read_mod(e.name, Path(e.path), dol_sha1.lower()))
    _refuse_shared_paths(found)
    return found


def _hash_file(path: Path) -> tuple[int, str]:
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
            size += len(chunk)
    return size, h.hexdigest()


def digest(mods: list[Mod]) -> str:
    """The SHA-256 over each file a mod holds, as Mod.held() lists them, mod by mod. Each is
    the mod's name, a slash and the file's path in the mod, then a NUL, its size in decimal, a
    NUL, its SHA-256 in hex and a newline. "none" when no mod holds a file."""
    total = hashlib.sha256()
    held = 0
    for mod in mods:
        for path, host in mod.held():
            size, sha = _hash_file(host)
            total.update(os.fsencode(f"{mod.name}/{path}\0{size}\0{sha}\n"))
            held += 1
    return total.hexdigest() if held else "none"


def _place(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    clone_file.clone(src, dst)
    return dst


def _run(python: Path, tool: Path, args: list[str], cwd: Path) -> tuple[int, str]:
    """Run TOOL from CWD. Its exit code, and what it printed on stderr or else on stdout."""
    done = subprocess.run([str(python), "-B", str(tool), *args], cwd=cwd, env=tool_env(),
                          stdin=subprocess.DEVNULL, capture_output=True)
    said = done.stderr if done.stderr.strip() else done.stdout
    return done.returncode, said.decode("utf-8", "replace").strip()


def _blame_list(said: str, lists: list[tuple[str, str]]) -> Optional[ModError]:
    """dol_patch.py's refusal of a list as a ModError naming the list's mod, with every list's
    clone named by its mod. None when it isn't a refusal of one of the lists."""
    names = dict(lists)
    m = LIST_SAID.fullmatch(said)
    if not m or m[1] not in names:
        return None
    why = m[3]
    for other, other_name in lists:
        why = why.replace(other, f"{other_name}/")
    return ModError(names[m[1]], DOL_TXT + m[2], why)


def _disc_paths(mod: Mod) -> list[str]:
    """Every file under the mod's files/ and every folder above one, by disc path."""
    paths = set()
    for disc in mod.files:
        parts = disc.split("/")
        paths.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))
    return sorted(paths)


def _blame_file(said: str, mods: list[Mod]) -> Optional[ModError]:
    """disc_overlay.py's `error: <path> <reason>` for a path under its files folder, as a
    ModError naming the first mod that holds that file or folder. Paths compare ignoring case,
    as the clones' volume does. None for any other reason or a path no mod holds."""
    if not said.startswith("error: "):
        return None
    text = said[len("error: "):]
    for mod in mods:
        for path in _disc_paths(mod):
            if not text.lower().startswith(path.lower() + " "):
                continue
            why = text[len(path) + 1:]
            if why in OVERLAY_REASONS or CASE_TWINS.fullmatch(why):
                return ModError(mod.name, f"{FILES}/{path}", why)
    return None


def prepare(mods: list[Mod], disc: Path, dol: Path, out: Path, python: Path,
            recomp: Path) -> Prepared:
    """Clone every mod's files into OUT, a new folder, and build the disc overlay there.

    files/ under OUT holds every file under the mods' files/, by disc path. A mod with dol.txt
    has it cloned with the files beside it into patches/N/, N counting the mods from 1. When any
    mod has one, RECOMP's dol_patch.py applies the lists in mod order to DOL, the game's checked
    DOL, giving OUT/main.dol and main.dol.syms. RECOMP's disc_overlay.py then builds the overlay
    for DISC from OUT/files, with main.dol as its DOL when there is one. PYTHON runs both, with
    -B and only tool_env.py's environment.

    Returns the DOL to recompile, which is the one the overlay boots, the manifest and the
    digest of the clones. A tool's refusal that names a mod's list or file is a ModError, and
    any other failure a PrepareError. A clone that fails falls back to a copy.
    """
    out.mkdir(parents=True)
    (out / FILES).mkdir()
    clones = []
    lists = []  # each list's folder under OUT with a slash, and its mod's name
    for n, mod in enumerate(mods, 1):
        copy = Mod(mod.name, {disc_path: _place(host, out / FILES / disc_path)
                              for disc_path, host in mod.files.items()})
        if mod.dol is not None:
            folder = f"{PATCHES}/{n}"
            copy.dol = _place(mod.dol, out / folder / DOL_TXT)
            copy.beside = {path: _place(host, out / folder / path)
                           for path, host in mod.beside.items()}
            lists.append((f"{folder}/", mod.name))
        clones.append(copy)
    boot = dol
    if lists:
        boot = out / BOOT_DOL
        args = [os.path.abspath(dol), BOOT_DOL] + [f"{prefix}{DOL_TXT}" for prefix, _ in lists]
        code, said = _run(python, recomp / "dol_patch.py", args, out)
        if code:
            raise _blame_list(said, lists) or PrepareError(f"dol_patch.py exited {code}: {said}")
    args = [os.path.abspath(disc), ".", "--files", FILES] + (["--dol", BOOT_DOL] if lists else [])
    code, said = _run(python, recomp / "disc_overlay.py", args, out)
    if code:
        raise _blame_file(said, mods) or PrepareError(f"disc_overlay.py exited {code}: {said}")
    return Prepared(boot, out / MANIFEST, digest(clones))


def check(mods: Path, dol_sha1: str) -> dict[str, object]:
    found = scan(mods, dol_sha1)
    rows = [{"name": mod.name, "files": len(mod.held()),
             "bytes": sum(host.stat().st_size for _, host in mod.held())} for mod in found]
    return {"mods": rows, "digest": digest(found)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="mods.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = ap.add_subparsers(dest="command", required=True)
    checker = commands.add_parser("check", help="list the mods and their digest, or refuse one")
    checker.add_argument("mods", type=Path, metavar="MODS", help="the mods folder")
    checker.add_argument("--dol-sha1", required=True, metavar="SHA",
                         help="the SHA-1 of the game's DOL, which each dol.txt has to name")
    a = ap.parse_args(argv)
    sha = a.dol_sha1.lower()
    if not SHA1.fullmatch(sha):
        print(f"mods.py: --dol-sha1 {a.dol_sha1} isn't a SHA-1", file=sys.stderr)
        return 2
    try:
        result = check(a.mods, sha)
    except ModError as e:
        print(json.dumps({"error": str(e), "mod": e.mod, "path": e.path}))
        return 1
    except OSError as e:
        print(f"mods.py: {e}", file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
