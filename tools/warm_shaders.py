#!/usr/bin/env python3
"""Warm the player's shader cache by playing the game once, hidden and silent.

Usage: warm_shaders.py [--game build/dragoon] [--saves saves] [--disc FILE] [--force]
                       [--jobs N] [--report DIR]

Runs the game, one pass per route in tests/hashes/manifest.txt but the warm-from= ones (see
below), each in a scratch directory
of its own with a blank memory card as a fresh install has. (A route that finds the card an
earlier pass made takes other menus and builds other keys.) Every pass is --hidden --fast
--no-input-log with SDL's dummy audio driver, so nothing shows or sounds, and the caller's
GCN_INPUT, GCN_WAV, GCN_PROFILE, GCN_FEED_DUMP and GCN_SESSION are dropped. A pass's
saves/shaders.bin starts as a copy of <saves>/shaders.bin and gains the keys its route
builds. --jobs passes play at once (by default a third of the cores, 6 at most), the longest
first. Once every pass has succeeded their caches are merged, each key once, in the
manifest's order, and the merge replaces the player's cache. Nothing else in <saves> is read
or written except the stamp, <saves>/.shader-warmup. It holds the gcn-recomp commit (from
git, or from source-info.json in a source snapshot), a SHA-1 of the manifest with the route
files' text and a SHA-1 of this script. If all three
match and shaders.bin exists, the run is skipped. A pass that outlasts twice its real-time
length plus 30 s is killed and fails, and the others are stopped. --force runs anyway. --game
and --saves default to build/dragoon and saves under the repository, wherever the tool is
run from. --disc names the disc image every pass plays. A game built from the engine kit
has no disc of its own, so it needs one. --report DIR keeps each pass's output and the cache
it left in DIR, and prints a table of what each pass added and where its time went (see
write_report).

A pass plays to the frame its route's warm= setting in the manifest names, or else 900
frames past the route's last required frame. A route with a warm-from=ROUTE setting gets no
pass, since ROUTE's pass plays what it does.

Prints one line per pass and a closing line with the cache's size. A failed pass prints
the game's last output to stderr.

Exits 0 when the cache is warm, whether the passes ran or the stamp was current, 1 when a
pass failed or the game left no shaders.bin (the player's saves are untouched), 2 when it
couldn't run: a bad argument, a missing game or route, or neither a gcn-recomp checkout nor a
readable source-info.json.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import frametime
import shader_cache
import source_info
from routes import MANIFEST, Route, parse_manifest, route_file

def default_jobs(cores: Optional[int]) -> int:
    """How many passes to play at once: a game uses about two cores, and past 6 at once the
    two longest passes, which set the time, only slow down (21 passes took 67 s at 6 and 71 s
    at 8 on a 16-core M4 Max)."""
    return max(1, min(6, (cores or 1) // 3))


ROOT = Path(__file__).resolve().parents[1]
CACHE = "shaders.bin"
STAMP = ".shader-warmup"
JOBS = default_jobs(os.cpu_count())  # passes played at once
STOP_POLL_S = 0.25  # how often a running pass looks for the order to stop
# The game's switches that a pass must not inherit: the route is its own, and the others write
# a file at one path, which up to six games at once would all write.
OWN_ENV = ("GCN_INPUT", "GCN_WAV", "GCN_PROFILE", "GCN_FEED_DUMP", "GCN_SESSION")
PRINT_LOCK = threading.Lock()
TAIL_LINES = 15
ROUTE_TAIL_FRAMES = 900  # past the last frame a route must reach, to build what follows it
# The --report columns' frame stretches end here. Up to frame 2,000 every route is in the boot,
# the title and the menus, which each pass plays from a blank card, though the title pass stops at
# 1,860. The Air Ride routes' races are under way by 3,400.
STRETCH_ENDS = (2000, 3400)
# The line each finished pass prints, which the launcher's build counts as progress.
PASS_LINE = re.compile(r"\S+: \d+ frames, \d+\.\d s")
# Ends the message of a warm-up that can't run, for whichever build ran it.
SKIP_HINT = ("(-DDRAGOON_WARMUP=OFF skips the warm-up in a CMake build, and --no-warmup in "
             "launcher_build.py)")
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


def pass_frames(route: Route) -> int:
    """The manifest's warm= frame for ROUTE, or ROUTE_TAIL_FRAMES past its last required one.

    parse_manifest only takes a warm= frame past the last required one, so it's never 0.
    """
    return route.warm or max(route.required) + ROUTE_TAIL_FRAMES


def passes(routes: list[Route]) -> list[Pass]:
    """A pass for each of ROUTES but the ones a warm-from= gives to another route's pass."""
    return [Pass(r.name, pass_frames(r), route_pads(r), route_file(r.name))
            for r in routes if r.warm_from is None]


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
                         f"name the engine {SKIP_HINT}")
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


class PassStopped(Exception):
    """A pass cut short because another one failed."""


def last_compile_frame(log: str) -> int:
    """The frame the game built its last program in, 0 for none or without GCN_FRAMETIME=1."""
    return max((n for n, f in frametime.parse(log.splitlines()).items() if f.compiles), default=0)


def run_pass(game: Path, p: Pass, scratch: Path, stop: threading.Event,
             disc: Optional[Path] = None) -> None:
    """Play P in SCRATCH, killing the game if STOP is set or it outlasts its time limit."""
    env = {k: v for k, v in os.environ.items() if k not in OWN_ENV}
    env["SDL_AUDIO_DRIVER"] = "dummy"
    env["GCN_INPUT"] = script_text(p.route_file)
    cmd = [str(game), "--hidden", "--fast", "--no-input-log", f"--pads={p.pads}",
           f"--exit-after={p.exit_after}"] + ([str(disc)] if disc else [])
    log = scratch / "stdout.txt"
    limit = pass_timeout(p.exit_after)
    with log.open("wb") as f:
        proc = subprocess.Popen(cmd, cwd=scratch, env=env, stdout=f, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + limit
        try:
            while True:
                try:
                    code = proc.wait(timeout=STOP_POLL_S)
                    break
                except subprocess.TimeoutExpired:
                    if stop.is_set():
                        raise PassStopped from None
                    if time.monotonic() > deadline:
                        raise PassFailed(f"{p.name}: the game didn't exit within {limit:.0f} s") from None
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    if code != 0:
        tail = "\n".join(log.read_text(errors="replace").splitlines()[-TAIL_LINES:])
        raise PassFailed(f"{p.name}: the game exited {code}\n{tail}")


def stretches(log: str, seconds: float) -> list[float]:
    """A pass's SECONDS split into starting the game, then frames up to each of STRETCH_ENDS
    and the frames past the last.

    A frame's share is its [ft] guest interval, the time since the frame before it was shown,
    and starting the game is the rest, the time before the first frame and after the last.
    Without GCN_FRAMETIME=1 there are no intervals and every share is 0.
    """
    spans = [0.0] * (len(STRETCH_ENDS) + 1)
    timed = [(n, f.guest_ms) for n, f in frametime.parse(log.splitlines()).items()
             if f.guest_ms is not None]
    if not timed:
        return [0.0] * (len(spans) + 1)
    for n, ms in timed:
        spans[bisect.bisect_left(STRETCH_ENDS, n)] += ms / 1000
    return [seconds - sum(spans), *spans]


# The --report table's columns, each a label and a width. The last four are stretches' shares.
REPORT_COLUMNS = (("pass", 28), ("frames", 7), ("s", 7), ("boot", 6), ("boot ms", 8), ("own", 5),
                  ("only", 5), ("+keys", 6), ("+progs", 7), ("keys", 6), ("last", 7),
                  ("start", 7), ("0-2k", 7), ("2k-3.4k", 8), ("rest", 7))


def report_line(cells: list[str]) -> str:
    """CELLS under REPORT_COLUMNS, the first left-aligned and the rest right-aligned."""
    (_, first), *rest = REPORT_COLUMNS
    return f"{cells[0]:<{first}}" + "".join(f"{c:>{w}}" for c, (_, w) in zip(cells[1:], rest))


REPORT_HEADER = report_line([label for label, _ in REPORT_COLUMNS])


def write_report(directory: Path, plan: list[Pass], seconds: list[float], scratch: list[Path],
                 start: Path) -> str:
    """Keep each pass's output and cache in DIRECTORY and write report.txt there, a table.

    NAME.log is the game's output and NAME.bin the cache the pass left. A row gives the
    programs the game built from the cache before its first frame and how long that took,
    the keys the pass built itself (own), the ones of those no other pass built (only),
    and the keys and programs (distinct generated sources) it adds that START and the
    passes before it in the plan lack. Under
    GCN_FRAMETIME=1 the "last" column is the frame the pass built its last program in, which
    is the frame it had to reach, and the four after it split the pass's seconds (see
    stretches). Without it those columns are 0. A closing "all" row adds up the frames, the
    seconds and the four splits.
    """
    directory.mkdir(parents=True, exist_ok=True)
    keys: set[bytes] = set()
    programs: set[int] = set()
    if start.exists():
        held = shader_cache.load(start)
        keys, programs = set(held.keys), set(held.hashes)
    held_keys = set(keys)
    caches = [d / "saves" / CACHE for d in scratch]
    made = [shader_cache.load(c) if c.exists() else None for c in caches]
    built = [set(m.keys) - held_keys if m else set() for m in made]
    rows = [REPORT_HEADER]
    totals = [0.0] * (len(STRETCH_ENDS) + 2)
    for i, (p, secs, d) in enumerate(zip(plan, seconds, scratch)):
        log = (d / "stdout.txt").read_text(errors="replace")
        (directory / f"{p.name}.log").write_text(log)
        boot = BOOT_LINE.search(log)
        new_keys = new_programs = 0
        others = set().union(*built[:i], *built[i + 1:])
        if made[i]:
            shutil.copyfile(caches[i], directory / f"{p.name}.bin")
            new_keys = len(set(made[i].keys) - keys)
            new_programs = len(set(made[i].hashes) - programs)
            keys |= set(made[i].keys)
            programs |= set(made[i].hashes)
        shares = stretches(log, secs)
        totals = [t + s for t, s in zip(totals, shares)]
        rows.append(report_line([p.name, str(p.exit_after), f"{secs:.1f}",
                                 boot[1] if boot else "0", boot[2] if boot else "0",
                                 str(len(built[i])), str(len(built[i] - others)),
                                 str(new_keys), str(new_programs), str(len(keys)),
                                 str(last_compile_frame(log)), *(f"{s:.1f}" for s in shares)]))
    rows.append(report_line(["all", str(sum(p.exit_after for p in plan)), f"{sum(seconds):.1f}",
                             *["-"] * 8, *(f"{t:.1f}" for t in totals)]))
    text = "\n".join(rows) + "\n"
    (directory / "report.txt").write_text(text)
    return text


def start_order(plan: list[Pass], jobs: int) -> list[int]:
    """The order passes start in: the plan's for one job at a time, otherwise the longest
    first, so the last to start isn't the one that takes the longest."""
    order = list(range(len(plan)))
    return order if jobs == 1 else sorted(order, key=lambda i: -plan[i].exit_after)


def warm(game: Path, saves: Path, plan: list[Pass], jobs: int = 1,
         report: Optional[Path] = None, disc: Optional[Path] = None) -> None:
    """Play every pass, JOBS at a time, and install the cache they build between them.

    A pass runs in a scratch directory of its own, with a blank memory card and a copy of
    the cache in SAVES, so it builds every key its route needs and no other pass is in its
    way. The caches the passes leave are merged in the plan's order.
    """
    start = saves / CACHE
    with tempfile.TemporaryDirectory(prefix="dragoon-warmup-") as tmp:
        scratch = [Path(tmp) / f"{i:02d}-{p.name}" for i, p in enumerate(plan)]
        for d in scratch:
            (d / "saves").mkdir(parents=True)
            if start.exists():
                shutil.copyfile(start, d / "saves" / CACHE)
        seconds = [0.0] * len(plan)
        stop = threading.Event()

        def play(i: int) -> None:
            if stop.is_set():
                raise PassStopped
            began = time.monotonic()
            try:
                run_pass(game, plan[i], scratch[i], stop, disc)
            except PassFailed:
                stop.set()  # here, so that no queued pass starts before the caller hears of it
                raise
            seconds[i] = time.monotonic() - began
            with PRINT_LOCK:
                print(f"{plan[i].name}: {plan[i].exit_after} frames, {seconds[i]:.1f} s", flush=True)

        failed: dict[int, PassFailed] = {}
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {pool.submit(play, i): i for i in start_order(plan, jobs)}
            try:
                for future in as_completed(futures):
                    try:
                        future.result()
                    except PassStopped:
                        pass
                    except PassFailed as e:
                        failed[futures[future]] = e
            except BaseException:
                stop.set()
                raise
        if failed:
            raise failed[min(failed)]
        caches = [d / "saves" / CACHE for d in scratch if (d / "saves" / CACHE).exists()]
        if not caches:
            raise PassFailed(f"the game wrote no {CACHE}")
        try:
            merged = shader_cache.merge([shader_cache.load(c) for c in caches])
        except ValueError as e:
            raise PassFailed(f"the passes' caches can't be joined: {e}") from None
        joined = Path(tmp) / CACHE
        joined.write_bytes(merged)
        if report:
            print(write_report(report, plan, seconds, scratch, start), end="")
        install(joined, start)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", type=Path, default=ROOT / "build" / "dragoon")
    ap.add_argument("--saves", type=Path, default=ROOT / "saves")
    ap.add_argument("--disc", type=Path, help="the disc image to play, for a game built without one")
    ap.add_argument("--force", action="store_true", help="run even if the stamp is current")
    ap.add_argument("--jobs", type=int, default=JOBS, metavar="N",
                    help=f"passes to play at once (default {JOBS})")
    ap.add_argument("--report", type=Path, metavar="DIR",
                    help="keep each pass's output and cache in DIR, with a table of what each added")
    args = ap.parse_args(argv)
    try:
        if args.jobs < 1:
            raise ValueError(f"--jobs is a number of passes, 1 or more, not {args.jobs}")
        if not args.game.is_file():
            raise ValueError(f"{args.game}: no such game, build it first")
        if args.disc and not args.disc.is_file():
            raise ValueError(f"{args.disc}: no such disc image")
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
            warm(args.game.resolve(), args.saves, plan, args.jobs, args.report,
                 args.disc.resolve() if args.disc else None)
        except PassFailed as e:
            print(f"shader warm-up failed, {args.saves} left as it was: {e}\n{SKIP_HINT}",
                  file=sys.stderr)
            return 1
        stamp_path.write_text(want + "\n")
        size = (args.saves / CACHE).stat().st_size
        print(f"warm: {len(plan)} passes, {args.saves / CACHE} is {size} bytes, "
              f"{time.monotonic() - start:.1f} s")
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
