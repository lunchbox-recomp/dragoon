#!/usr/bin/env python3
"""Build the game on the player's Mac from a source snapshot, the engine kit and their disc.

Usage: launcher_build.py --source DIR --kit DIR --disc FILE --data DIR --cache DIR
           --make FILE --cc FILE --cxx FILE --python FILE --sdk DIR --log FILE
           [--no-warmup] [--keep-build]

The launcher runs this, and a developer can run it from a shell. Every path is absolute and
every tool is the one named, never one found on PATH. The tools get only PATH=/usr/bin:/bin:
/usr/sbin:/sbin, HOME, TMPDIR, LANG, PYTHONDONTWRITEBYTECODE and PYTHONNOUSERSITE, so nothing
from Homebrew, MacPorts or the user's site-packages reaches the build. Nothing downloads, and the
snapshot and the kit are only read.
The kit's engine.o and headers have to match the generated C, so its kit.mk has to name the
gcn-recomp commit the snapshot's source-info.json does and the SHA-256 of the snapshot's src/.
The steps are:
  recompile  in an empty <cache>/build, the snapshot's extract_dol.py takes main.dol from the
             disc, checked against the disc ID and SHA-1 in its source-info.json, and its
             recomp.py writes the game's C to gen/
  compile    the kit's Makefile, run by make with a job per core, compiles gen/*.c there and
             links dragoon with the kit's engine.o and libSDL3.a
  warmup     warm_shaders.py in <cache>/warm, on a copy of the player's shader cache
  package    <data>/game/<id>/Dragoon.app around the game, sealed ad hoc, with a stamp.json
             beside it naming both commits, the SDK and the time
  swap       point <data>/game/current at the new build, then install the warmed cache in
             <data>/saves, where a file that can't be installed is left as it was and is a
             warning, since the new game is current
Before the swap nothing in <data> changes but the new game/<id>, and a package step that fails
removes it. Earlier builds stay in <data>/game for the launcher to delete. After a good build
the intermediates in <cache> are deleted, except build/ under --keep-build.

Prints one JSON object per line on stdout:
  {"event": "step", "step": "recompile"}
  {"event": "progress", "step": "compile", "done": 12, "total": 135}
  {"event": "done", "game": "<data>/game/current/Dragoon.app"}
  {"event": "error", "step": "compile", "message": "...", "log": "<file>"}
  {"event": "warning", "step": "swap", "message": "...", "log": "<file>"}
--log gets every line every tool prints, with each command, and each step's time and what
<data> and <cache> hold after it. A build that loses the lock doesn't open it. A step's closing
note and a warning's note are lost if --log can't take them, so a full disk fails no build
that has swapped.

Exits 0 when the new game is current, 1 when a step failed before the swap, 2 on a bad argument
and 3 when another build holds <cache>/build.lock. A kit of another gcn-recomp commit or another src/ is a
bad argument, which prints an error event at step "kit" too. A SIGTERM ends the build with 143
once the step it stopped has cleaned up, so no half-made <data>/game/<id> or temp file in
<data>/saves is left. It prints no event, since it's the launcher's cancel.
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
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Optional, TextIO

import export_source
import routes
import source_info
import warm_shaders
from tool_env import TOOL_PATH, tool_env  # TOOL_PATH stays here for test_mutant.py

CODESIGN = "/usr/bin/codesign"
APP = "Dragoon.app"
GAME = "dragoon"
WARMED = (warm_shaders.CACHE, warm_shaders.STAMP)
PARTIAL = ".partial"
# The recompiler in the snapshot, and the SYMBOLS and TABLES Dragoon's CMakeLists.txt gives
# gcn_add_game.
EXTRACT_DOL = "gcn-recomp/recomp/extract_dol.py"
RECOMP = "gcn-recomp/recomp/recomp.py"
SYMBOLS = "analysis/symbols.txt"
TABLES = "recomp"
# The line make prints for each object the kit's Makefile compiles.
COMPILE_LINE = re.compile(r".* -c gen/[^ ]+\.c -o obj/[^ ]+\.o")
# The lines in kit.mk naming the gcn-recomp commit and the digest of src/, as engine_kit.py
# writes them.
KIT_COMMIT = re.compile(r"ENGINE_COMMIT := ([0-9a-f]{40})")
KIT_SRC = re.compile(r"SRC_SHA256 := ([0-9a-f]{64})")
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


def emit(**event: object) -> None:
    print(json.dumps(event), flush=True)


@contextlib.contextmanager
def exit_on_sigterm() -> Iterator[None]:
    """Turn a SIGTERM into SystemExit(143) wherever the build is, so the cleanups in the steps
    run, the lock and the log close, and the exit says what stopped it."""
    def stop(signum: int, frame: object) -> None:
        raise SystemExit(128 + signum)

    before = signal.signal(signal.SIGTERM, stop)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, before)


@contextlib.contextmanager
def sigterm_held() -> Iterator[Callable[[], None]]:
    """Hold a SIGTERM that comes inside the block, and give back the function that lets it
    through. A block that makes something calls it from inside the try that cleans the something
    up, so a SIGTERM can't land between the two. The block's end lets it through too."""
    held = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})

    def release() -> None:
        signal.pthread_sigmask(signal.SIG_SETMASK, held)

    try:
        yield release
    finally:
        release()


def disk_use(*roots: Path) -> int:
    """Bytes the files under ROOTS take on disk, as du counts them, links not followed. A file
    removed between the listing and the measuring counts as nothing."""
    total = 0
    for root in roots:
        for parent, _, names in os.walk(root):
            for name in names:
                try:
                    total += os.lstat(os.path.join(parent, name)).st_blocks * 512
                except FileNotFoundError:
                    pass
    return total


class Build:
    """The log and the tools run, for one build, and the events its steps print."""

    def __init__(self, log: TextIO, log_path: Path, *watched: Path):
        self.log = log
        self.log_path = log_path
        self.watched = watched
        self.step = ""
        self.env = tool_env()

    def note(self, line: str, best_effort: bool = False) -> None:
        """Write LINE to the log. A BEST_EFFORT line the log can't take is lost, and no more."""
        try:
            self.log.write(line + "\n")
            self.log.flush()
        except OSError:
            if not best_effort:
                raise

    def fail(self, step: str, message: str) -> None:
        self.note(f"== {step} failed: {message}")
        emit(event="error", step=step, message=message, log=str(self.log_path))

    def warn(self, message: str) -> None:
        self.note(f"== {self.step} warning: {message}", best_effort=True)
        emit(event="warning", step=self.step, message=message, log=str(self.log_path))

    @contextlib.contextmanager
    def stage(self, step: str) -> Iterator[None]:
        """Print the step's event and write its notes. The closing note is best-effort in every
        step, since it holds a measurement and a measurement never fails a step. A line whose
        flush failed stays pending, so a log that stays full fails the next strict write, and a
        full log before the swap still stops the run with the old game current."""
        self.step = step
        emit(event="step", step=step)
        self.note(f"== {step}")
        start = time.monotonic()
        yield
        took = f"== {step} took {time.monotonic() - start:.1f} s"
        try:
            held = f"with {disk_use(*self.watched) / 1e6:.1f} MB in --data and --cache"
        except OSError as e:  # the measurement is a note, and never fails the step
            held = f"and --data and --cache couldn't be measured ({e})"
        self.note(f"{took}, {held}", best_effort=True)

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
                    emit(event="progress", step=self.step, done=counts[0], total=counts[1])
        if p.returncode != 0:
            raise StepFailed(f"{name or Path(cmd[0]).name} exited {p.returncode}")


def remove(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def recompile(b: Build, a: argparse.Namespace, info: dict[str, str], build: Path) -> None:
    """main.dol and gen/ in BUILD, which is emptied first."""
    remove(build)
    build.mkdir(parents=True)
    dol = build / "main.dol"
    b.run([str(a.python), "-B", str(a.source / EXTRACT_DOL), str(a.disc), str(dol),
           info["disc_id"], info["dol_sha1"]], cwd=build, name="extract_dol.py")
    b.run([str(a.python), "-B", str(a.source / RECOMP), str(dol), str(a.source / SYMBOLS),
           str(build / "gen"), str(a.source / TABLES)], cwd=build, name="recomp.py")


def make_command(a: argparse.Namespace) -> list[str]:
    return [str(a.make), "-f", str(a.kit / "Makefile"), f"-j{os.cpu_count() or 1}",
            f"KIT={a.kit}", f"SDK={a.sdk}", f"CC={a.cc}", f"CXX={a.cxx}", GAME]


def compile_game(b: Build, a: argparse.Namespace, build: Path) -> None:
    """BUILD/dragoon from BUILD/gen, with one progress event per object compiled."""
    total = len(list((build / "gen").glob("*.c")))
    done = itertools.count(1)

    def progress(line: str) -> Optional[tuple]:
        return (next(done), total) if COMPILE_LINE.fullmatch(line) else None

    b.run(make_command(a), cwd=build, progress=progress)


def warm_up(b: Build, a: argparse.Namespace, game: Path, warm: Path) -> None:
    """Run the snapshot's warm_shaders.py on copies of the player's cache and stamp in WARM."""
    warm.mkdir(parents=True)
    for name in WARMED:
        if (a.data / "saves" / name).is_file():
            shutil.copy2(a.data / "saves" / name, warm / name)
    manifest = a.source / routes.MANIFEST.relative_to(routes.ROOT)
    total = len(warm_shaders.passes(routes.parse_manifest(manifest.read_text())))
    done = itertools.count(1)

    def progress(line: str) -> Optional[tuple]:
        return (next(done), total) if warm_shaders.PASS_LINE.fullmatch(line) else None

    b.run([str(a.python), "-B", str(a.source / "tools" / "warm_shaders.py"), "--game", str(game),
           "--saves", str(warm), "--disc", str(a.disc)], cwd=a.cache, name="warm_shaders.py",
          progress=progress)


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
    with sigterm_held() as release:
        build = new_build_dir(games, info["dragoon"])
        try:
            release()  # a SIGTERM that came during the mkdir raises here, in the cleanup's reach
            contents = build / APP / "Contents"
            (contents / "MacOS").mkdir(parents=True)
            shutil.copy2(game, contents / "MacOS" / GAME)
            with (contents / "Info.plist").open("wb") as f:
                plistlib.dump(INFO_PLIST, f)
            b.run([CODESIGN, "--force", "--sign", "-", str(build / APP)], cwd=a.cache)
            stamp = {"dragoon": info["dragoon"], "gcn-recomp": info["gcn-recomp"],
                     "sdk": str(a.sdk),
                     "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
            (build / "stamp.json").write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n")
        except BaseException:  # no half-made build for the launcher's cleanup to find
            shutil.rmtree(build, ignore_errors=True)
            raise
    return build


def swap(data: Path, build: Path) -> None:
    """Point <data>/game/current at BUILD in one rename."""
    games = data / "game"
    current = games / "current"
    for leftover in games.glob(f".current.*{PARTIAL}"):  # from a swap that was killed
        leftover.unlink()
    link = games / f".current.{os.getpid()}{PARTIAL}"
    os.symlink(build.name, link)
    try:
        os.replace(link, current)
    except BaseException:
        link.unlink(missing_ok=True)  # a SIGTERM can land just after the rename
        raise


def install_warmed(b: Build, data: Path, warm: Path) -> None:
    """Install the warmed shader files from WARM in <data>/saves. The new game is current by
    now, so a file that can't be installed is a warning and stays as it was. The files after it
    are left alone, since a new stamp beside an old cache would skip the next warm-up. A stamp
    that can't be installed leaves the new cache beside the old stamp, which warms again."""
    for name in WARMED:
        if (warm / name).is_file():
            try:
                warm_shaders.install(warm / name, data / "saves" / name)
            except OSError as e:
                b.warn(f"couldn't install {name} in {data / 'saves'}: {e.strerror or e}")
                return


def build_game(b: Build, a: argparse.Namespace, info: dict[str, str]) -> Path:
    """Every step in order. Returns the game's path."""
    warm = a.cache / "warm" / "saves"
    build = a.cache / "build"
    with b.stage("recompile"):
        remove(warm.parent)  # from a build that was killed, which the swap mustn't install from
        recompile(b, a, info, build)
    with b.stage("compile"):
        compile_game(b, a, build)
    if not a.no_warmup:
        with b.stage("warmup"):
            warm_up(b, a, build / GAME, warm)
    with b.stage("package"):
        game = package(b, a, build / GAME, info)
    with b.stage("swap"):
        swap(a.data, game)
        install_warmed(b, a.data, warm)
    return a.data / "game" / "current" / APP


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, required=True, help="the read-only source snapshot")
    ap.add_argument("--kit", type=Path, required=True, help="the engine kit engine_kit.py made")
    ap.add_argument("--disc", type=Path, required=True, help="the player's disc image")
    ap.add_argument("--data", type=Path, required=True, help="~/Library/Application Support/Dragoon")
    ap.add_argument("--cache", type=Path, required=True, help="~/Library/Caches/Dragoon")
    for tool in ("make", "cc", "cxx", "python"):
        ap.add_argument(f"--{tool}", type=Path, required=True)
    ap.add_argument("--sdk", type=Path, required=True)
    ap.add_argument("--log", type=Path, required=True, help="every line every tool prints")
    ap.add_argument("--no-warmup", action="store_true", help="skip the shader warm-up")
    ap.add_argument("--keep-build", action="store_true", help="keep <cache>/build")
    return ap.parse_args(argv)


def kit_problem(kit: Path, engine: str, source: Path) -> Optional[str]:
    """Why KIT can't build SOURCE, a snapshot of gcn-recomp commit ENGINE, or None when it can."""
    mk = kit / "kit.mk"
    try:
        lines = mk.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return f"{mk}: can't read it ({e.strerror})"
    commits = [m[1] for m in map(KIT_COMMIT.fullmatch, lines) if m]
    if len(commits) != 1:
        return f"{mk} doesn't name one gcn-recomp commit, as engine_kit.py writes it"
    if commits[0] != engine:
        return (f"the kit is from gcn-recomp {commits[0]} and the source snapshot from gcn-recomp"
                f" {engine}: the kit's engine.o and headers wouldn't match the generated C")
    digests = [m[1] for m in map(KIT_SRC.fullmatch, lines) if m]
    if len(digests) != 1:
        return f"{mk} doesn't name one src/ digest, as engine_kit.py writes it"
    try:
        digest = export_source.src_digest(source)
    except OSError as e:
        return f"{e.filename}: can't read it ({e.strerror})"
    if digests[0] != digest:
        return (f"the kit's src/ has SHA-256 {digests[0]} and the source snapshot's {digest}: the hooks"
                " in the kit's engine.o wouldn't match the generated C")
    return None


def bad_argument(a: argparse.Namespace) -> Optional[str]:
    for flag in ("source", "kit", "disc", "data", "cache", "make", "cc", "cxx", "python", "sdk",
                 "log"):
        path = getattr(a, flag)
        if not path.is_absolute():
            return f"--{flag} {path} isn't an absolute path"
    for flag in ("make", "cc", "cxx", "python"):
        path = getattr(a, flag)
        if not (path.is_file() and os.access(path, os.X_OK)):
            return f"--{flag} {path} isn't an executable file"
    if not a.disc.is_file():
        return f"--disc {a.disc} isn't a file"
    for flag, path in (("--source", a.source), ("--kit", a.kit), ("--sdk", a.sdk)):
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
    mismatch = kit_problem(a.kit, info["gcn-recomp"], a.source)
    if mismatch:
        # Before the lock, so the log isn't opened, as for a bad argument.
        emit(event="error", step="kit", message=mismatch, log=str(a.log))
        print(f"launcher_build.py: {mismatch}", file=sys.stderr)
        return 2
    a.cache.mkdir(parents=True, exist_ok=True)
    with exit_on_sigterm(), (a.cache / "build.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # The log isn't opened yet. The build that holds the lock may be writing to it.
            emit(event="error", step="lock", log=str(a.log),
                 message=f"another build holds {a.cache / 'build.lock'}")
            return 3
        a.log.parent.mkdir(parents=True, exist_ok=True)
        log = a.log.open("a")
        try:
            b = Build(log, a.log, a.data, a.cache)
            try:
                game = build_game(b, a, info)
            except (StepFailed, OSError, ValueError, subprocess.SubprocessError) as e:
                b.fail(b.step, str(e))
                return 1
            for name in ("warm",) + (() if a.keep_build else ("build",)):
                shutil.rmtree(a.cache / name, ignore_errors=True)
            emit(event="done", game=str(game))
        finally:
            with contextlib.suppress(OSError):  # a flush that failed fails again as the log closes
                log.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
