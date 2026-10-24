"""launcher/bundle-manifest.txt: what Dragoon.app may hold besides its source snapshot.

One directive per line. A # starts a comment. Paths are relative to the .app, separated by /,
and have no spaces.
  source PATH        the directory holding the source snapshot
  budget app BYTES   the most the app's files may add up to
  budget dmg BYTES   the most the DMG file may weigh
  file PATH          a plain file that may be there
  dir PATH           anything below this directory may be there
  macho PATH         a Mach-O executable that may be there
  object PATH        a static library or object file that may be there. PATH ends in .a or .o
  engine PATH        the kit's engine object, an object line whose file may also hold the disc
                     ID, which the engine carries as a public constant. One at most
  link PATH TARGET   a symlink that may be there, and the target it has to point at
check_bundle.py reads it. A path that no line allows is a finding. A file named .a or .o, or
that is an ar archive, needs an object or engine line of its own.
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path

BUDGETS = ("app", "dmg")
ARITY = {"source": 1, "budget": 2, "file": 1, "dir": 1, "macho": 1, "object": 1, "engine": 1, "link": 2}
OBJECT_SUFFIXES = (".a", ".o")


def is_object_name(path: str) -> bool:
    """Is PATH named like a static library or an object file, in any letter case?"""
    return path.lower().endswith(OBJECT_SUFFIXES)


@dataclass(frozen=True)
class BundleManifest:
    source: str
    budgets: dict[str, int]
    files: frozenset[str]
    dirs: tuple[str, ...]  # each ends in /
    machos: frozenset[str]
    links: dict[str, str]
    objects: frozenset[str]  # the engine's included
    engine: str | None

    def under_dir(self, path: str) -> bool:
        """Is PATH, a directory ending in /, a listed directory or inside one?"""
        return any(path.startswith(d) for d in self.dirs)

    def allows_file(self, path: str) -> bool:
        return path in self.files or path in self.machos or path in self.objects or self.under_dir(path)


def _relative(path: str) -> str:
    if path in ("", ".") or path.startswith("/") or posixpath.normpath(path) != path:
        raise ValueError(f"{path!r} isn't a plain relative path")
    return path


def parse(text: str) -> BundleManifest:
    """The manifest TEXT holds. Raises ValueError naming the line it can't read."""
    source = None
    budgets: dict[str, int] = {}
    files: set[str] = set()
    dirs: list[str] = []
    machos: set[str] = set()
    links: dict[str, str] = {}
    objects: set[str] = set()
    engine = None
    listed: set[str] = set()
    for n, raw in enumerate(text.splitlines(), 1):
        words = raw.split("#", 1)[0].split()
        if not words:
            continue
        directive, args = words[0], words[1:]
        try:
            if directive not in ARITY:
                raise ValueError(f"unknown directive {directive!r}")
            if len(args) != ARITY[directive]:
                raise ValueError(f"{directive} takes {ARITY[directive]} word(s), not {len(args)}")
            if directive == "budget":
                name = args[0]
                if name not in BUDGETS or name in budgets:
                    raise ValueError(f"budget {name} isn't one of {BUDGETS}, or is listed twice")
                if not args[1].isdigit() or int(args[1]) == 0:
                    raise ValueError(f"{args[1]!r} isn't a positive number of bytes")
                budgets[name] = int(args[1])
                continue
            path = _relative(args[0].rstrip("/") if directive == "dir" else args[0])
            if path in listed:
                raise ValueError(f"{path} is listed twice")
            listed.add(path)
            if directive == "source":
                if source is not None:
                    raise ValueError("source is listed twice")
                source = path
            elif directive == "file":
                files.add(path)
            elif directive == "dir":
                dirs.append(path + "/")
            elif directive == "macho":
                machos.add(path)
            elif directive in ("object", "engine"):
                if not is_object_name(path):
                    raise ValueError(f"{path} isn't named .a or .o")
                if directive == "engine":
                    if engine is not None:
                        raise ValueError("engine is listed twice")
                    engine = path
                objects.add(path)
            else:
                if args[1].startswith("/"):
                    raise ValueError(f"link target {args[1]} isn't relative")
                links[path] = args[1]
        except ValueError as e:
            raise ValueError(f"line {n}: {e}") from None
    if source is None:
        raise ValueError("no source line")
    for name in BUDGETS:
        if name not in budgets:
            raise ValueError(f"no budget for {name}")
    return BundleManifest(source, budgets, frozenset(files), tuple(dirs), frozenset(machos), links,
                          frozenset(objects), engine)


def read(path: Path) -> BundleManifest:
    try:
        return parse(path.read_text())
    except ValueError as e:
        raise ValueError(f"{path}: {e}") from None
