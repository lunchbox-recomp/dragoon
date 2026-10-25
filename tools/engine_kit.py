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
              frameworks and libraries, from game_libs.txt; MACOSX_MIN, the build's
              CMAKE_OSX_DEPLOYMENT_TARGET; ENGINE_COMMIT, the gcn-recomp commit in the
              gcn_engine_sha.h runtime_check was compiled with; and SRC_SHA256, the
              src_digest export_source.py gives the build's src/, which runtime_check
              compiles too. launcher_build.py checks both against the source snapshot's.
              The digest matches a snapshot's only from a clean checkout, so a src/ with
              anything untracked, ignored or changed is refused (by `git status`, with git
              from PATH), and so is one with a file newer than runtime_check's objects of
              src/
  Makefile    launcher/kit/Makefile, which compiles gen/*.c and links the game
  licenses/   gcn-recomp's, SDL's and that of the hidapi inside SDL
`ld -r` turns the objects' DWARF into a debug map naming the build's own .o files, which a
player doesn't have. --strip-debug drops that map and libSDL3.a's DWARF too.

A build with a GAME_ISO is refused, since main.o would carry the disc's path. So is one
missing any of the three files, one whose game_libs.txt names a path, which a player's Mac
may not have, and one whose gcn_engine_sha.h names no commit or one with changes to tracked
files. OUT is written under a temporary name and renamed into place, so a failed run leaves
no OUT.

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

import export_source

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "launcher" / "kit" / "Makefile"
HEADERS = ("recomp.h", "compat.h")
OBJECT_LINE = re.compile(r"^build (CMakeFiles/runtime_check\.dir/\S+\.o): ", re.M)
# The same lines with the source each object is compiled from, after the rule's name. Ninja
# writes a space, a colon or a dollar sign in a path with a dollar sign before it.
SOURCE_LINE = re.compile(r"^build (CMakeFiles/runtime_check\.dir/\S+\.o): \S+ ((?:\$.|\S)+)", re.M)
NINJA_ESCAPE = re.compile(r"\$(.)")
CACHE_LINE = re.compile(r"([A-Za-z0-9_.+-]+):[A-Z]+=(.*)")
VERSION = re.compile(r"\d+(\.\d+)*")
# What gcn-recomp's gcn_engine_sha target writes for runtime_check, and the commit a kit names.
ENGINE_SHA = Path("gcn_engine_sha") / "gcn_engine_sha.h"
ENGINE_SHA_LINE = re.compile(r'#define GCN_ENGINE_SHA "([^"]*)"\n')
COMMIT = re.compile(r"[0-9a-f]{40}")
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
    # A trailing backslash would fold kit.mk's next line into this one.
    if any(c in flags for c in "#$\n") or flags.endswith("\\"):
        raise KitError(f"{where} isn't one line of flags make can take as written")
    return flags


def build_flags(build: Path, name: str, why_missing: str) -> str:
    """The one line of flags gcn-recomp's configure wrote to <build>/NAME."""
    path = build / name
    try:
        flags = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise KitError(f"{path} is missing: {why_missing}") from None
    except OSError as e:
        raise KitError(f"{path}: can't read it ({e.strerror})") from None
    except UnicodeDecodeError:
        raise KitError(f"{path} isn't UTF-8 text") from None
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


def check_src(build: Path, dragoon: Path) -> None:
    """Refuses a src/ under DRAGOON other than the one runtime_check compiled from a commit,
    so that its digest names what engine.o holds."""
    src = dragoon / "src"
    done = subprocess.run(["git", "-C", str(dragoon), "status", "--porcelain", "--ignored", "--", "src"],
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise KitError(f"git can't say whether {src} is clean: {done.stderr.strip()}")
    if done.stdout:
        line = done.stdout.splitlines()[0]
        raise KitError(f"git status shows {line!r} in {src}: make the kit from a clean checkout, with"
                       " nothing untracked, ignored or changed in src/")
    ninja = (build / "build.ninja").read_text()
    objects = [build / name for name, source in SOURCE_LINE.findall(ninja)
               if (build / NINJA_ESCAPE.sub(r"\1", source)).is_relative_to(src)]
    if not objects:
        raise KitError(f"runtime_check compiles nothing in {src}, so engine.o would have no hooks")
    built = min(o.stat().st_mtime_ns for o in objects)
    newer = sorted(p for p in src.rglob("*") if p.is_file() and p.stat().st_mtime_ns > built)
    if newer:
        raise KitError(f"{newer[0]} is newer than runtime_check's objects of src/: build runtime_check"
                       " again")


def engine_commit(build: Path) -> str:
    """The gcn-recomp commit runtime_check was compiled with, which has to be a clean one."""
    path = build / ENGINE_SHA
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise KitError(f"{path} is missing: build runtime_check, whose gcn_engine_sha target"
                       " writes it") from None
    except OSError as e:
        raise KitError(f"{path}: can't read it ({e.strerror})") from None
    m = ENGINE_SHA_LINE.fullmatch(text)
    if not m:
        raise KitError(f"{path} isn't the line gcn-recomp's engine_sha.cmake writes")
    if not COMMIT.fullmatch(m[1]):
        raise KitError(f'{path} names "{m[1]}", not a gcn-recomp commit: build the kit from a gcn-recomp'
                       " checkout with no changes to tracked files")
    return m[1]


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
    engine = engine_commit(build)
    try:
        dragoon_src = Path(cache["dragoon_SOURCE_DIR"])
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
    check_src(build, dragoon_src)
    src_sha = export_source.src_digest(dragoon_src)

    tmp = Path(tempfile.mkdtemp(prefix=f".{out.name}.", dir=out.parent))
    try:
        run([str(ld), "-r", "-arch", "arm64", "-o", str(tmp / "engine.o"), *map(str, objects)])
        for src, rel in copies.items():
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, tmp / rel)
        (tmp / "kit.mk").write_text(
            f"# Written by tools/engine_kit.py from {build.name}'s game_cflags.txt, game_ldflags.txt,\n"
            "# game_libs.txt, CMakeCache.txt, gcn_engine_sha.h and src/. Make a new kit rather than editing it.\n"
            f"GAME_CFLAGS := {flags}\nLINK_FLAGS := {ldflags}\nGAME_LIBS := {libs}\n"
            f"MACOSX_MIN := {target}\nENGINE_COMMIT := {engine}\nSRC_SHA256 := {src_sha}\n")
        if strip_debug:
            run([str(strip), "-S", str(tmp / "engine.o"), str(tmp / "libSDL3.a")])
        tmp.chmod(0o755)  # mkdtemp made it 0700
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
