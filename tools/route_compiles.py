#!/usr/bin/env python3
"""Which routes compile a shader in play after the warm-up?

Usage: route_compiles.py --cache FILE [ROUTE ...] [--aspect=16:9]

Plays each route in tests/hashes/manifest.txt, or the ROUTEs named, from a copy of the shader
cache FILE, unpaced to the frame its warm-up pass plays it to (its warm= frame, or 900 past its
last required frame, as warm_shaders.py plays it), and counts the "[shaders] compiled program"
lines. Each run is

  tools/probe.sh compiles-ROUTE SECONDS tests/routes/ROUTE.txt 100000 --exit-after=N GCN_FRAMETIME=1

plus the route's manifest settings and --aspect, as status.md's "Shaders compiled at 16:9" row
ran them. SECONDS is the warm-up's own limit for a pass of N frames. The run's directory,
build/probe/compiles-ROUTE/, starts with only the cache in saves/, so the memory card is blank,
and it's deleted after the run. It prints one line per route with the frames it compiled in.

Exits 0 when no route compiled, 1 when one did or stopped short of its frame N, 2 on a bad
argument, a missing cache or a probe.sh run that failed.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import frametime
from probe_dirs import remove_run, run_probe
from routes import MANIFEST, Route, route_file, select_routes
from warm_shaders import CACHE, pass_frames, pass_timeout

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe.sh"


@dataclass
class Compiles:
    frames: list[int]  # the frame each program was compiled in, one entry a program
    reached: int  # the last frame the log has an [rt] line for
    wanted: int  # the frame the run plays to

    @property
    def ok(self) -> bool:
        return not self.frames and self.reached >= self.wanted


def read_log(text: str, wanted: int) -> Compiles:
    frames = frametime.parse(text.splitlines())
    compiled = [n for n, f in sorted(frames.items()) for _ in f.compiles]
    return Compiles(compiled, max((n for n, f in frames.items() if f.render_ms is not None), default=0), wanted)


def probe_args(route: Route, name: str, aspect: str, probe: Path = PROBE,
               settings: tuple[str, ...] = ()) -> list[str]:
    frames = pass_frames(route)
    wide = [] if aspect == "4:3" else [f"--aspect={aspect}"]
    return [str(probe), name, str(round(pass_timeout(frames))), str(route_file(route.name)), "100000",
            f"--exit-after={frames}", "GCN_FRAMETIME=1", *route.extra, *wide, *settings]


def play(route: Route, cache: Path, aspect: str = "4:3", root: Path = ROOT, probe: Path = PROBE,
         settings: tuple[str, ...] = (), keep: Optional[Path] = None) -> Compiles:
    """Play ROUTE from a copy of CACHE and count its compiles. KEEP, when given, gets a copy of the
    run's log when the route compiled or stopped short. The run's directory is deleted after."""
    name = f"compiles-{route.name}"
    out = root / "build" / "probe" / name
    if out.exists():
        remove_run(out)
    (out / "saves").mkdir(parents=True)
    shutil.copyfile(cache, out / "saves" / CACHE)
    try:
        run_probe(probe_args(route, name, aspect, probe, settings), root, route.name)
        result = read_log((out / "stdout.txt").read_text(errors="replace"), pass_frames(route))
        if keep is not None and not result.ok:
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(out / "stdout.txt", keep)
        return result
    finally:
        remove_run(out)


def describe(c: Compiles) -> str:
    if c.reached < c.wanted:
        return f"reached frame {c.reached} of {c.wanted}"
    if c.frames:
        return f"compiled {len(c.frames)} at frame{'s' if len(c.frames) > 1 else ''} {', '.join(map(str, c.frames))}"
    return f"compiled 0 to frame {c.wanted}"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("routes", nargs="*")
    ap.add_argument("--cache", type=Path, required=True, help="the shader cache to copy into each run")
    ap.add_argument("--aspect", choices=["4:3", "16:9"], default="4:3")
    args = ap.parse_args(argv)
    try:
        if not args.cache.is_file():
            raise ValueError(f"{args.cache}: no such cache")
        failed = 0
        for route in select_routes(args.routes, MANIFEST):
            c = play(route, args.cache.resolve(), args.aspect)
            print(f"{route.name}: {describe(c)}")
            failed += not c.ok
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
