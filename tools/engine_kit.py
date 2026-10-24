#!/usr/bin/env python3
"""Assemble the prebuilt engine kit from a build configured with no disc.

Usage: engine_kit.py --build DIR --out DIR [--strip-debug] [--ld FILE] [--strip FILE]

CI runs this after `ninja runtime_check SDL3-static` in a build configured with no disc and
with CMAKE_OSX_DEPLOYMENT_TARGET set. The kit is everything a player's Mac needs to build the
game besides Apple's Command Line Tools and the recompiler's inputs. OUT gets:
  engine.o    runtime_check's objects joined by `ld -r`, so the link takes every one of them,
              main.o and the static initializers included
  libSDL3.a   SDL3-static as built
  include/    recomp.h and compat.h, the only runtime headers the generated C includes
  kit.mk      what gcn-recomp's configure wrote to <build>: GAME_CFLAGS from
              game_cflags.txt, LINK_FLAGS from game_ldflags.txt and GAME_LIBS, the
              frameworks and libraries, from game_libs.txt; and MACOSX_MIN, the build's
              CMAKE_OSX_DEPLOYMENT_TARGET
  Makefile    launcher/kit/Makefile, which compiles gen/*.c and links the game
  licenses/   gcn-recomp's, SDL's and that of the hidapi inside SDL
`ld -r` turns the objects' DWARF into a debug map naming the build's own .o files, which a
player doesn't have. --strip-debug drops that map and libSDL3.a's DWARF too.

A build with a GAME_ISO is refused, since main.o would carry the disc's path. So is one
missing any of the three files, and one whose game_libs.txt names a path, which a player's
Mac may not have. OUT is written under a temporary name and renamed into place, so a failed
run leaves no OUT.

Exits 0 when the kit is written, 1 when ld or strip failed, and 2 on a bad argument or a build
it can't make a kit from.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "launcher" / "kit" / "Makefile"
HEADERS = ("recomp.h", "compat.h")
OBJECT_LINE = re.compile(r"^build (CMakeFiles/runtime_check\.dir/\S+\.o): ", re.M)
CACHE_LINE = re.compile(r"([A-Za-z0-9_.+-]+):[A-Z]+=(.*)")
VERSION = re.compile(r"\d+(\.\d+)*")
CFLAGS_MISSING = "this gcn-recomp doesn't write the game's flags"
# The configure writes the two link files together, and neither when it can't write every
# library, with a warning saying why.
LINK_MISSING = ("this gcn-recomp doesn't write the game's link, or the configure warned that it"
                " couldn't write it")


class KitError(Exception):
    """A build the kit can't be made from (exit 2)."""


class ToolFailed(Exception):
    """ld or strip exited nonzero (exit 1)."""


def read_cache(path: Path) -> dict[str, str]:
    try:
        text = path.read_text()
    except OSError as e:
        raise KitError(f"{path}: can't read it ({e.strerror})") from None
    return {m[1]: m[2] for m in map(CACHE_LINE.fullmatch, text.splitlines()) if m}


def make_safe(flags: str, where: str) -> str:
    if any(c in flags for c in "#$\n"):
        raise KitError(f"{where} isn't one line of flags make can take as written")
    return flags


def build_flags(build: Path, name: str, why_missing: str) -> str:
    """The one line of flags gcn-recomp's configure wrote to <build>/NAME."""
    path = build / name
    try:
        flags = path.read_text().strip()
    except OSError:
        raise KitError(f"{path} is missing: {why_missing}") from None
    if not flags:
        raise KitError(f"{path} is empty")
    return make_safe(flags, str(path))


def game_libs(build: Path) -> str:
    libs = build_flags(build, "game_libs.txt", LINK_MISSING)
    paths = [word for word in libs.split() if "/" in word]
    if paths:
        raise KitError(f"{build / 'game_libs.txt'} names {paths[0]}, a path a player's Mac may not have")
    return libs


def engine_objects(build: Path) -> list[Path]:
    try:
        ninja = (build / "build.ninja").read_text()
    except OSError:
        raise KitError(f"{build / 'build.ninja'} is missing: configure with -G Ninja") from None
    objects = [build / name for name in OBJECT_LINE.findall(ninja)]
    if not objects:
        raise KitError(f"{build} has no runtime_check target")
    missing = [o for o in objects if not o.is_file()]
    if missing:
        raise KitError(f"runtime_check isn't built: {len(missing)} of {len(objects)} objects are missing,"
                       f" {missing[0]} first")
    return objects


def run(cmd: list[str]) -> None:
    done = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if done.returncode != 0:
        raise ToolFailed(f"{Path(cmd[0]).name} exited {done.returncode}: {done.stdout.strip()}")


def assemble(build: Path, out: Path, ld: Path, strip: Path, strip_debug: bool) -> None:
    cache = read_cache(build / "CMakeCache.txt")
    if cache.get("GAME_ISO"):
        raise KitError(f"{build} was configured with GAME_ISO={cache['GAME_ISO']}; a kit's build has no disc")
    target = cache.get("CMAKE_OSX_DEPLOYMENT_TARGET", "")
    if not VERSION.fullmatch(target):
        raise KitError(f"{build} has no CMAKE_OSX_DEPLOYMENT_TARGET, which the game's link has to match")
    flags = build_flags(build, "game_cflags.txt", CFLAGS_MISSING)
    ldflags = build_flags(build, "game_ldflags.txt", LINK_MISSING)
    libs = game_libs(build)
    objects = engine_objects(build)
    try:
        engine_src = Path(cache["gcn_recomp_SOURCE_DIR"])
        sdl_src = Path(cache["SDL3_SOURCE_DIR"])
        sdl_lib = Path(cache["SDL3_BINARY_DIR"]) / "libSDL3.a"
    except KeyError as e:
        raise KitError(f"{build / 'CMakeCache.txt'} has no {e.args[0]}") from None
    copies = {sdl_lib: "libSDL3.a", MAKEFILE: "Makefile",
              engine_src / "LICENSE": "licenses/gcn-recomp.txt",
              sdl_src / "LICENSE.txt": "licenses/SDL3.txt",
              sdl_src / "src" / "hidapi" / "LICENSE-bsd.txt": "licenses/hidapi.txt"}
    copies.update({engine_src / "runtime" / h: f"include/{h}" for h in HEADERS})
    for src in copies:
        if not src.is_file():
            raise KitError(f"{src} is missing")

    tmp = Path(tempfile.mkdtemp(prefix=f".{out.name}.", dir=out.parent))
    try:
        run([str(ld), "-r", "-arch", "arm64", "-o", str(tmp / "engine.o"), *map(str, objects)])
        for src, rel in copies.items():
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, tmp / rel)
        (tmp / "kit.mk").write_text(
            f"# Written by tools/engine_kit.py from {build.name}'s game_cflags.txt, game_ldflags.txt,\n"
            "# game_libs.txt and CMakeCache.txt. Make a new kit rather than editing it.\n"
            f"GAME_CFLAGS := {flags}\nLINK_FLAGS := {ldflags}\nGAME_LIBS := {libs}\n"
            f"MACOSX_MIN := {target}\n")
        if strip_debug:
            run([str(strip), "-S", str(tmp / "engine.o"), str(tmp / "libSDL3.a")])
        tmp.rename(out)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", type=Path, required=True, help="the no-disc build directory")
    ap.add_argument("--out", type=Path, required=True, help="the kit directory, which mustn't exist")
    ap.add_argument("--strip-debug", action="store_true", help="drop debug info from engine.o and libSDL3.a")
    ap.add_argument("--ld", type=Path, default=Path("/usr/bin/ld"))
    ap.add_argument("--strip", type=Path, default=Path("/usr/bin/strip"))
    a = ap.parse_args(argv)
    try:
        if a.out.exists() or a.out.is_symlink():
            raise KitError(f"{a.out} already exists")
        if not a.out.parent.is_dir():
            raise KitError(f"{a.out.parent} isn't a directory")
        assemble(a.build.resolve(), a.out.resolve(), a.ld, a.strip, a.strip_debug)
    except KitError as e:
        print(f"engine_kit.py: {e}", file=sys.stderr)
        return 2
    except (ToolFailed, OSError) as e:
        print(f"engine_kit.py: {e}", file=sys.stderr)
        return 1
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
