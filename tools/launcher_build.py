#!/usr/bin/env python3
"""Build the game on the player's Mac from a source snapshot and their disc.

Usage: launcher_build.py --source DIR (--disc FILE | --no-disc) --data DIR --cache DIR
           --cmake FILE --ninja FILE --cc FILE --cxx FILE --python FILE --sdk DIR
           --sdl-tarball FILE --log FILE [--no-warmup] [--keep-build]

The launcher runs this, and a developer can run it from a shell. Every path is absolute and
every tool is the one named, never one found on PATH. The tools get only PATH=/usr/bin:/bin:
/usr/sbin:/sbin, HOME, TMPDIR, LANG, PYTHONDONTWRITEBYTECODE and NINJA_STATUS, and CMake
ignores /opt/homebrew, /usr/local and /opt/local, so Homebrew and MacPorts can't reach the
build. Nothing downloads. The steps are:
  sdl        check --sdl-tarball against gcn-recomp's pin and extract it to <cache>/sdl
  source     copy the snapshot to <data>/source/<dragoon commit> and check it against its
             manifest
  configure  CMake into an empty <cache>/build, which recompiles the disc
  compile    Ninja builds dragoon, or runtime_check under --no-disc, which stops there
  warmup     warm_shaders.py in <cache>/warm, on a copy of the player's shader cache
  package    <data>/game/<id>/Dragoon.app around the game, sealed ad hoc, with a stamp.json
             beside it naming both commits, the SDK and the time
  swap       point <data>/game/current at the new build, then install the warmed cache in
             <data>/saves
Before the swap nothing in <data> changes but the new source/<commit> and game/<id>.
Earlier builds stay in <data>/game for the launcher to delete. After a good build the
intermediates in <cache> are deleted, except build/ and sdl/ under --keep-build.

Prints one JSON object per line on stdout:
  {"event": "step", "step": "configure"}
  {"event": "progress", "step": "compile", "done": 12, "total": 183}
  {"event": "done", "game": "<data>/game/current/Dragoon.app"}   (null under --no-disc)
  {"event": "error", "step": "configure", "message": "...", "log": "<file>"}
--log gets every line every tool prints, with each command and each step's time.

Exits 0 when the new game is current (under --no-disc, when runtime_check built), 1 when a
step failed, 2 on a bad argument and 3 when another build holds <cache>/build.lock.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import itertools
import json
import os
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Optional, TextIO

import export_source
import routes
import sdl_source
import source_info
import warm_shaders

TOOL_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
CODESIGN = "/usr/bin/codesign"
IGNORE_PREFIXES = "/opt/homebrew;/usr/local;/opt/local"
APP = "Dragoon.app"
GAME = "dragoon"
WARMED = (warm_shaders.CACHE, warm_shaders.STAMP)
NINJA_LINE = re.compile(r"\[(\d+)/(\d+)\] ")
PARTIAL = ".partial"
# Until the launcher's own bundle ID is chosen, the game's follows the one that needs no domain.
INFO_PLIST = {
    "CFBundleExecutable": GAME,
    "CFBundleIdentifier": "io.github.lunchbox-recomp.dragoon.game",
    "CFBundleName": "Dragoon",
    "CFBundlePackageType": "APPL",
    "CFBundleInfoDictionaryVersion": "6.0",
    "LSApplicationCategoryType": "public.app-category.games",
    "LSMinimumSystemVersion": "14.0",
    "LSSupportsGameMode": True,
    "GCSupportsGameMode": True,
}

Progress = Callable[[str], Optional[tuple]]


class StepFailed(Exception):
    pass


def tool_env() -> dict[str, str]:
    return {"PATH": TOOL_PATH, "HOME": str(Path.home()), "TMPDIR": tempfile.gettempdir(),
            "LANG": "en_US.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "NINJA_STATUS": "[%f/%t] "}


class Build:
    """The events on stdout, the log and the tools run, for one build."""

    def __init__(self, log: TextIO, log_path: Path):
        self.log = log
        self.log_path = log_path
        self.step = ""
        self.env = tool_env()

    def emit(self, **event: object) -> None:
        print(json.dumps(event), flush=True)

    def note(self, line: str) -> None:
        self.log.write(line + "\n")
        self.log.flush()

    def fail(self, step: str, message: str) -> None:
        self.note(f"== {step} failed: {message}")
        self.emit(event="error", step=step, message=message, log=str(self.log_path))

    @contextlib.contextmanager
    def stage(self, step: str) -> Iterator[None]:
        self.step = step
        self.emit(event="step", step=step)
        self.note(f"== {step}")
        start = time.monotonic()
        yield
        self.note(f"== {step} took {time.monotonic() - start:.1f} s")

    def run(self, cmd: list[str], cwd: Path, name: str = "",
            progress: Progress = lambda line: None) -> None:
        """Run CMD, logging each line it prints and turning the ones PROGRESS counts into
        progress events. Raises StepFailed when it exits nonzero."""
        self.note("$ " + shlex.join(cmd))
        with subprocess.Popen(cmd, cwd=cwd, env=self.env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as p:
            assert p.stdout is not None
            for raw in p.stdout:
                line = raw.decode(errors="replace").rstrip("\r\n")
                self.note(line)
                counts = progress(line)
                if counts:
                    self.emit(event="progress", step=self.step, done=counts[0], total=counts[1])
        if p.returncode != 0:
            raise StepFailed(f"{name or Path(cmd[0]).name} exited {p.returncode}")


def ninja_progress(line: str) -> Optional[tuple]:
    m = NINJA_LINE.match(line)
    return (int(m.group(1)), int(m.group(2))) if m else None


def remove(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def unpack_sdl(snapshot: Path, tarball: Path, cache: Path) -> Path:
    pin = sdl_source.pin((snapshot / "gcn-recomp" / "CMakeLists.txt").read_text())
    found = export_source.sha256_file(tarball)
    if found != pin.sha256:
        raise StepFailed(f"{tarball} has SHA-256 {found}, but gcn-recomp pins {pin.sha256}")
    dest = cache / "sdl"
    remove(dest)
    sdl_source.extract(tarball, dest)
    if not (dest / pin.top).is_dir():
        raise StepFailed(f"{tarball} holds no {pin.top}/")
    return dest / pin.top


def copy_source(snapshot: Path, parent: Path, commit: str) -> Path:
    """Copy SNAPSHOT to PARENT/COMMIT through a temp name and a rename, checked file by file
    against its manifest. A copy already there is replaced."""
    parent.mkdir(parents=True, exist_ok=True)
    for leftover in parent.glob("*" + PARTIAL):  # from a build that was killed
        shutil.rmtree(leftover, ignore_errors=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{commit}.", suffix=PARTIAL, dir=parent))
    try:
        shutil.copytree(snapshot, tmp, symlinks=True, dirs_exist_ok=True)
        want = export_source.parse_manifest((tmp / export_source.MANIFEST).read_text())
        if export_source.manifest(tmp) != want:
            raise StepFailed(f"{snapshot} doesn't match its {export_source.MANIFEST}")
        final = parent / commit
        if final.exists():  # moved aside, and deleted below with the other leftovers
            os.rename(final, Path(tempfile.mkdtemp(suffix=PARTIAL, dir=parent)) / commit)
        os.rename(tmp, final)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    for leftover in parent.glob("*" + PARTIAL):
        shutil.rmtree(leftover, ignore_errors=True)
    return final


def configure_command(a: argparse.Namespace, source: Path, build: Path, sdl: Path) -> list[str]:
    cmd = [str(a.cmake), "-S", str(source), "-B", str(build), "-G", "Ninja",
           f"-DCMAKE_MAKE_PROGRAM={a.ninja}", "-DCMAKE_BUILD_TYPE=RelWithDebInfo",
           f"-DCMAKE_OSX_SYSROOT={a.sdk}", f"-DCMAKE_C_COMPILER={a.cc}",
           f"-DCMAKE_CXX_COMPILER={a.cxx}", f"-DPython3_EXECUTABLE={a.python}"]
    if not a.no_disc:
        cmd.append(f"-DGAME_ISO={a.disc}")
    return cmd + ["-DDRAGOON_WARMUP=OFF", f"-DFETCHCONTENT_SOURCE_DIR_SDL3={sdl}",
                  "-DFETCHCONTENT_FULLY_DISCONNECTED=ON", "-DSDL_HIDAPI_LIBUSB=OFF",
                  f"-DCMAKE_IGNORE_PREFIX_PATH={IGNORE_PREFIXES}"]


def warm_up(b: Build, a: argparse.Namespace, source: Path, game: Path, warm: Path) -> None:
    """Run the source's warm_shaders.py on copies of the player's cache and stamp in WARM."""
    warm.mkdir(parents=True)
    for name in WARMED:
        if (a.data / "saves" / name).is_file():
            shutil.copy2(a.data / "saves" / name, warm / name)
    manifest = source / routes.MANIFEST.relative_to(routes.ROOT)
    total = len(routes.parse_manifest(manifest.read_text()))
    done = itertools.count(1)

    def progress(line: str) -> Optional[tuple]:
        return (next(done), total) if warm_shaders.PASS_LINE.fullmatch(line) else None

    b.run([str(a.python), "-B", str(source / "tools" / "warm_shaders.py"), "--game", str(game),
           "--saves", str(warm)], cwd=a.cache, name="warm_shaders.py", progress=progress)


def new_build_dir(games: Path, commit: str) -> Path:
    """A new games/<time>-<commit>, with -2, -3 and on added when a build in the same second
    already took the name."""
    stem = f"{time.strftime('%Y%m%d-%H%M%S')}-{commit[:12]}"
    path, n = games / stem, 1
    while True:
        try:
            path.mkdir()
            return path
        except FileExistsError:
            n += 1
            path = games / f"{stem}-{n}"


def package(b: Build, a: argparse.Namespace, game: Path, info: dict[str, str]) -> Path:
    """<data>/game/<id>/Dragoon.app around GAME, sealed ad hoc, with stamp.json beside it."""
    games = a.data / "game"
    games.mkdir(parents=True, exist_ok=True)
    build = new_build_dir(games, info["dragoon"])
    contents = build / APP / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    shutil.copy2(game, contents / "MacOS" / GAME)
    with (contents / "Info.plist").open("wb") as f:
        plistlib.dump(INFO_PLIST, f)
    b.run([CODESIGN, "--force", "--sign", "-", str(build / APP)], cwd=a.cache)
    stamp = {"dragoon": info["dragoon"], "gcn-recomp": info["gcn-recomp"], "sdk": str(a.sdk),
             "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    (build / "stamp.json").write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n")
    return build


def swap(data: Path, build: Path, warm: Path) -> None:
    """Point <data>/game/current at BUILD in one rename, then install the warmed files."""
    current = data / "game" / "current"
    link = current.with_name(f".current.{os.getpid()}{PARTIAL}")
    if link.is_symlink():
        link.unlink()
    os.symlink(build.name, link)
    os.replace(link, current)
    for name in WARMED:
        if (warm / name).is_file():
            warm_shaders.install(warm / name, data / "saves" / name)


def build_game(b: Build, a: argparse.Namespace, info: dict[str, str]) -> Optional[Path]:
    """Every step in order. Returns the game's path, or None under --no-disc."""
    warm = a.cache / "warm" / "saves"
    remove(warm.parent)
    with b.stage("sdl"):
        sdl = unpack_sdl(a.source, a.sdl_tarball, a.cache)
    with b.stage("source"):
        source = copy_source(a.source, a.data / "source", info["dragoon"])
    build = a.cache / "build"
    with b.stage("configure"):
        remove(build)
        b.run(configure_command(a, source, build, sdl), cwd=a.cache)
    with b.stage("compile"):
        b.run([str(a.ninja), "-C", str(build), "runtime_check" if a.no_disc else GAME],
              cwd=a.cache, progress=ninja_progress)
    if a.no_disc:
        return None
    if not a.no_warmup:
        with b.stage("warmup"):
            warm_up(b, a, source, build / GAME, warm)
    with b.stage("package"):
        game = package(b, a, build / GAME, info)
    with b.stage("swap"):
        swap(a.data, game, warm)
    return a.data / "game" / "current" / APP


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, required=True, help="the read-only source snapshot")
    disc = ap.add_mutually_exclusive_group(required=True)
    disc.add_argument("--disc", type=Path, help="the player's disc image")
    disc.add_argument("--no-disc", action="store_true",
                      help="configure with no disc and build runtime_check only")
    ap.add_argument("--data", type=Path, required=True, help="~/Library/Application Support/Dragoon")
    ap.add_argument("--cache", type=Path, required=True, help="~/Library/Caches/Dragoon")
    for tool in ("cmake", "ninja", "cc", "cxx", "python"):
        ap.add_argument(f"--{tool}", type=Path, required=True)
    ap.add_argument("--sdk", type=Path, required=True)
    ap.add_argument("--sdl-tarball", type=Path, required=True)
    ap.add_argument("--log", type=Path, required=True, help="every line every tool prints")
    ap.add_argument("--no-warmup", action="store_true", help="skip the shader warm-up")
    ap.add_argument("--keep-build", action="store_true", help="keep <cache>/build and <cache>/sdl")
    return ap.parse_args(argv)


def bad_argument(a: argparse.Namespace) -> Optional[str]:
    for flag in ("source", "disc", "data", "cache", "cmake", "ninja", "cc", "cxx", "python",
                 "sdk", "sdl_tarball", "log"):
        path = getattr(a, flag)
        if path is not None and not path.is_absolute():
            return f"--{flag.replace('_', '-')} {path} isn't an absolute path"
    for flag in ("cmake", "ninja", "cc", "cxx", "python"):
        path = getattr(a, flag)
        if not (path.is_file() and os.access(path, os.X_OK)):
            return f"--{flag} {path} isn't an executable file"
    for flag, path in (("--sdl-tarball", a.sdl_tarball), ("--disc", a.disc)):
        if path is not None and not path.is_file():
            return f"{flag} {path} isn't a file"
    for flag, path in (("--source", a.source), ("--sdk", a.sdk)):
        if not path.is_dir():
            return f"{flag} {path} isn't a directory"
    return None


def main(argv: list[str]) -> int:
    a = parse_args(argv)
    problem = bad_argument(a)
    if not problem:
        try:
            info = source_info.read(a.source / source_info.NAME)
        except (OSError, ValueError) as e:
            problem = str(e)
    if problem:
        print(f"launcher_build.py: {problem}", file=sys.stderr)
        return 2
    a.cache.mkdir(parents=True, exist_ok=True)
    a.log.parent.mkdir(parents=True, exist_ok=True)
    with (a.cache / "build.lock").open("a") as lock, a.log.open("a") as log:
        b = Build(log, a.log)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            b.fail("lock", f"another build holds {a.cache / 'build.lock'}")
            return 3
        try:
            game = build_game(b, a, info)
        except (StepFailed, OSError, ValueError, subprocess.SubprocessError) as e:
            b.fail(b.step, str(e))
            return 1
        for name in ("warm",) + (() if a.keep_build else ("build", "sdl")):
            shutil.rmtree(a.cache / name, ignore_errors=True)
        b.emit(event="done", game=str(game) if game else None)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
