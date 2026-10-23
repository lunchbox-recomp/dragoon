#!/usr/bin/env python3
"""Warm the player's shader cache by playing the game once, hidden and silent.

Usage: warm_shaders.py [--game build/dragoon] [--saves saves] [--force] [--report DIR]

Runs the game in a scratch directory, one pass per route in tests/hashes/manifest.txt, each
from a blank memory card as a fresh install is. (A route that finds the card an earlier
pass made takes other menus and builds other keys.) Every pass is --hidden --fast
--no-input-log with SDL's dummy audio driver, so nothing shows or sounds. The scratch
saves/shaders.bin starts as a copy of <saves>/shaders.bin and grows pass by pass, and the
player's cache is only replaced once every pass has succeeded. Nothing else in <saves> is
read or written except the stamp, <saves>/.shader-warmup. It holds the gcn-recomp commit (from
git, or from source-info.json in a source snapshot), a SHA-1 of the manifest with the route
files' text and a SHA-1 of this script. If all three
match and shaders.bin exists, the run is skipped. A pass that outlasts twice its real-time
length plus 30 s is killed and fails. --force runs anyway. --game and --saves default to
build/dragoon and saves under the repository, wherever the tool is run from. --report DIR
keeps each pass's output and the cache it left in DIR, and prints a table of what each pass
added (see Report).

Prints one line per pass and a closing line with the cache's size. A failed pass prints
the game's last output to stderr.

Exits 0 when the cache is warm, whether the passes ran or the stamp was current, 1 when a
pass failed or the game left no shaders.bin (the player's saves are untouched), 2 when it
couldn't run: a bad argument, a missing game or route, or neither a gcn-recomp checkout nor a
readable source-info.json.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import frametime
import shader_cache
import source_info
from routes import MANIFEST, Route, parse_manifest, route_file

ROOT = Path(__file__).resolve().parents[1]
CACHE = "shaders.bin"
CARD_GLOB = "memcard_*.raw"
STAMP = ".shader-warmup"
TAIL_LINES = 15
ROUTE_TAIL_FRAMES = 900  # past the last frame a route must reach, to build what follows it
# The line each finished pass prints, which the launcher's build counts as progress.
PASS_LINE = re.compile(r"\S+: \d+ frames, \d+\.\d s")
# What the game prints once it has built the programs the cache held, before its first frame.
BOOT_LINE = re.compile(r"\[shaders\] (\d+) programs from cache .* in (\d+) ms")


@dataclass
class Pass:
    name: str
    exit_after: int
    pads: int
    route_file: Path


def script_text(path: Path) -> str:
    """The route file with # lines dropped and spaces and newlines removed, as probe.sh does."""
    lines = (l for l in path.read_text().splitlines() if not l.startswith("#"))
    return "".join(lines).replace(" ", "")


def route_pads(route: Route) -> int:
    pads = [int(a.removeprefix("--pads=")) for a in route.extra if a.startswith("--pads=")]
    return pads[-1] if pads else 1


def passes(routes: list[Route]) -> list[Pass]:
    return [Pass(r.name, max(r.required) + ROUTE_TAIL_FRAMES, route_pads(r), route_file(r.name))
            for r in routes]


def stamp(engine_rev: str, inputs_text: str, tool_sha: str) -> str:
    return f"{engine_rev} {hashlib.sha1(inputs_text.encode()).hexdigest()} {tool_sha}"


def tool_sha() -> str:
    return hashlib.sha1(Path(__file__).read_bytes()).hexdigest()


def engine_rev() -> str:
    """The gcn-recomp commit the game was built from.

    A checkout asks git. A source snapshot has no history, so it reads the commit its
    source-info.json names, and git wins in a tree that has both.
    """
    checkout = ROOT / "gcn-recomp"
    if (checkout / ".git").exists():
        try:
            done = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"],
                                  capture_output=True, text=True, check=True)
        except (OSError, subprocess.CalledProcessError) as e:
            raise ValueError(f"can't read the gcn-recomp commit: {e}") from None
        return done.stdout.strip()
    info = ROOT / source_info.NAME
    if not info.exists():
        raise ValueError(f"no gcn-recomp checkout or {source_info.NAME}, so the stamp can't "
                         "name the engine (configure with -DDRAGOON_WARMUP=OFF to skip the warm-up)")
    return source_info.read(info)["gcn-recomp"]


def pass_timeout(exit_after: int) -> float:
    """Twice the pass's length at 60 fps, plus 30 s; --fast should finish well inside it."""
    return 2 * exit_after / 60 + 30


def install(src: Path, dest: Path) -> None:
    """Replace DEST with a copy of SRC, whole or not at all.

    The copy goes to a temp file beside DEST and an os.replace puts it in place, so a reader
    never sees half a file.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=dest.name + ".", suffix=".tmp", dir=dest.parent)
    try:
        with os.fdopen(fd, "wb") as out, src.open("rb") as f:
            shutil.copyfileobj(f, out)
            out.flush()
            os.fsync(out.fileno())
        shutil.copymode(src, tmp)
        os.replace(tmp, dest)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class PassFailed(Exception):
    pass


def last_compile_frame(log: str) -> int:
    """The frame the game built its last program in, 0 for none or without GCN_FRAMETIME=1."""
    return max((n for n, f in frametime.parse(log.splitlines()).items() if f.compiles), default=0)


def run_pass(game: Path, p: Pass, scratch: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k != "GCN_INPUT"}
    env["SDL_AUDIO_DRIVER"] = "dummy"
    env["GCN_INPUT"] = script_text(p.route_file)
    cmd = [str(game), "--hidden", "--fast", "--no-input-log", f"--pads={p.pads}",
           f"--exit-after={p.exit_after}"]
    log = scratch / "stdout.txt"
    limit = pass_timeout(p.exit_after)
    with log.open("wb") as f:
        try:
            code = subprocess.run(cmd, cwd=scratch, env=env, stdout=f, stderr=subprocess.STDOUT,
                                  timeout=limit).returncode
        except subprocess.TimeoutExpired:
            raise PassFailed(f"{p.name}: the game didn't exit within {limit:.0f} s") from None
    if code != 0:
        tail = "\n".join(log.read_text(errors="replace").splitlines()[-TAIL_LINES:])
        raise PassFailed(f"{p.name}: the game exited {code}\n{tail}")


class Report:
    """What each pass did to the cache, kept in a directory for measuring the warm-up.

    Per pass, NAME.log is the game's output and NAME.bin the cache as the pass left it.
    report.txt holds one row per pass: the programs the game built from the cache before its
    first frame and how long that took, and the keys and programs (distinct generated
    sources) the pass added that the starting cache and the passes before it lacked. Run
    under GCN_FRAMETIME=1, the last column is the frame the pass built its last program in,
    which is the frame it had to reach; without it that column is 0.
    """

    HEADER = (f"{'pass':<28}{'frames':>7}{'s':>7}{'boot':>6}{'boot ms':>8}{'+keys':>6}{'+progs':>7}"
              f"{'keys':>6}{'last':>7}")

    def __init__(self, directory: Path, start: Path):
        self.dir = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.keys: set[bytes] = set()
        self.programs: set[int] = set()
        self.rows = [self.HEADER]
        if start.exists():
            self.absorb(shader_cache.load(start))

    def absorb(self, k: shader_cache.KeyFile) -> tuple[int, int]:
        """Take K's keys and programs in; how many of each were new."""
        keys, programs = set(k.keys) - self.keys, set(k.hashes) - self.programs
        self.keys |= keys
        self.programs |= programs
        return len(keys), len(programs)

    def after_pass(self, p: Pass, seconds: float, scratch: Path) -> None:
        log = (scratch / "stdout.txt").read_text(errors="replace")
        (self.dir / f"{p.name}.log").write_text(log)
        loaded = BOOT_LINE.search(log)
        boot, boot_ms = (int(loaded[1]), int(loaded[2])) if loaded else (0, 0)
        cache = scratch / "saves" / CACHE
        new_keys = new_programs = 0
        if cache.exists():
            shutil.copyfile(cache, self.dir / f"{p.name}.bin")
            new_keys, new_programs = self.absorb(shader_cache.load(cache))
        last = last_compile_frame(log)
        self.rows.append(f"{p.name:<28}{p.exit_after:>7}{seconds:>7.1f}{boot:>6}{boot_ms:>8}"
                         f"{new_keys:>6}{new_programs:>7}{len(self.keys):>6}{last:>7}")

    def write(self) -> str:
        text = "\n".join(self.rows) + "\n"
        (self.dir / "report.txt").write_text(text)
        return text


def warm(game: Path, saves: Path, plan: list[Pass], report: Optional[Path] = None) -> None:
    with tempfile.TemporaryDirectory(prefix="dragoon-warmup-") as d:
        scratch = Path(d)
        (scratch / "saves").mkdir()
        cache = scratch / "saves" / CACHE
        if (saves / CACHE).exists():
            shutil.copyfile(saves / CACHE, cache)
        kept = Report(report, cache) if report else None
        for p in plan:
            for card in (scratch / "saves").glob(CARD_GLOB):
                card.unlink()
            start = time.monotonic()
            run_pass(game, p, scratch)
            seconds = time.monotonic() - start
            print(f"{p.name}: {p.exit_after} frames, {seconds:.1f} s", flush=True)
            if kept:
                kept.after_pass(p, seconds, scratch)
        if not cache.exists():
            raise PassFailed(f"the game wrote no {CACHE}")
        if kept:
            print(kept.write(), end="")
        install(cache, saves / CACHE)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", type=Path, default=ROOT / "build" / "dragoon")
    ap.add_argument("--saves", type=Path, default=ROOT / "saves")
    ap.add_argument("--force", action="store_true", help="run even if the stamp is current")
    ap.add_argument("--report", type=Path, metavar="DIR",
                    help="keep each pass's output and cache in DIR, with a table of what each added")
    args = ap.parse_args(argv)
    try:
        if not args.game.is_file():
            raise ValueError(f"{args.game}: no such game, build it first")
        manifest_text = MANIFEST.read_text()
        routes = parse_manifest(manifest_text)
        plan = passes(routes)
        inputs_text = manifest_text + "".join(script_text(p.route_file) for p in plan)
        want = stamp(engine_rev(), inputs_text, tool_sha())
        stamp_path = args.saves / STAMP
        if not args.force and stamp_path.exists() \
                and (args.saves / CACHE).exists() and stamp_path.read_text().strip() == want:
            print("shader cache is current, nothing to do (--force to rerun)")
            return 0
        start = time.monotonic()
        try:
            warm(args.game.resolve(), args.saves, plan, args.report)
        except PassFailed as e:
            print(f"shader warm-up failed, {args.saves} left as it was: {e}\n"
                  "(configure with -DDRAGOON_WARMUP=OFF to skip the warm-up)", file=sys.stderr)
            return 1
        stamp_path.write_text(want + "\n")
        size = (args.saves / CACHE).stat().st_size
        print(f"warm: {len(routes)} passes, {args.saves / CACHE} is {size} bytes, "
              f"{time.monotonic() - start:.1f} s")
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
