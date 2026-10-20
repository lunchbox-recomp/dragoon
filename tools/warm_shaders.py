#!/usr/bin/env python3
"""Warm the player's shader cache by playing the game once, hidden and silent.

Usage: warm_shaders.py [--game build/dragoon] [--saves saves] [--attract-frames N]
                       [--force] [--no-routes]

Runs the game in a scratch directory with its own blank memory card: one pass at the title
with nobody at the controls, then one pass per route in tests/hashes/manifest.txt. Every
pass is --hidden --fast --no-input-log with SDL's dummy audio driver, so nothing shows or
sounds. The scratch saves/shaders.bin starts as a copy of <saves>/shaders.bin and grows
pass by pass; the player's cache is only replaced once every pass has succeeded, by a copy
to a temp file in <saves> and an os.replace, so a reader never sees half a file. Nothing
else in <saves> is read or written except the stamp, <saves>/.shader-warmup, which holds
the gcn-recomp commit and a SHA-1 of the manifest. If both match the stamp, the run is
skipped. --force runs anyway. --no-routes runs only the attract pass and neither reads nor
writes the stamp (for measuring what the attract demos alone build). --game and --saves
default to build/dragoon and saves under the repository, wherever the tool is run from.

Prints one line per pass and a closing line with the cache's size. A failed pass prints
the game's last output to stderr.

Exits 0 when the cache is warm, whether the passes ran or the stamp was current, 1 when a
pass failed or the game left no shaders.bin (the player's saves are untouched), 2 when it
couldn't run: a bad argument, a missing game, route or git revision.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from frame_hashes import Route, parse_manifest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "hashes" / "manifest.txt"
ROUTES = ROOT / "tests" / "routes"
CACHE = "shaders.bin"
STAMP = ".shader-warmup"
TAIL_LINES = 15
ROUTE_TAIL_FRAMES = 600  # past the last frame a route must reach, to build what follows it


@dataclass
class Pass:
    name: str
    exit_after: int
    pads: int
    script: Path | None  # the route file, or None for nobody at the controls


def script_text(path: Path) -> str:
    """The route file with # lines dropped and spaces and newlines removed, as probe.sh does."""
    lines = (l for l in path.read_text().splitlines() if not l.startswith("#"))
    return "".join(lines).replace(" ", "")


def route_pads(route: Route) -> int:
    pads = [int(a.removeprefix("--pads=")) for a in route.extra if a.startswith("--pads=")]
    return pads[-1] if pads else 1


def passes(routes: list[Route], attract_frames: int) -> list[Pass]:
    return [Pass("attract", attract_frames, 1, None)] + [
        Pass(r.name, max(r.required) + ROUTE_TAIL_FRAMES, route_pads(r), ROUTES / f"{r.name}.txt")
        for r in routes]


def stamp(engine_rev: str, manifest_text: str) -> str:
    return f"{engine_rev} {hashlib.sha1(manifest_text.encode()).hexdigest()}"


def engine_rev() -> str:
    try:
        done = subprocess.run(["git", "-C", str(ROOT / "gcn-recomp"), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        raise ValueError(f"can't read the gcn-recomp commit: {e}") from None
    return done.stdout.strip()


def install(cache_from: Path, saves_dir: Path) -> None:
    """Replace <saves_dir>/shaders.bin with cache_from, whole or not at all."""
    saves_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=CACHE + ".", suffix=".tmp", dir=saves_dir)
    try:
        with os.fdopen(fd, "wb") as out, cache_from.open("rb") as src:
            shutil.copyfileobj(src, out)
        shutil.copymode(cache_from, tmp)
        os.replace(tmp, saves_dir / CACHE)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def run_pass(game: Path, p: Pass, scratch: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k != "GCN_INPUT"}
    env["SDL_AUDIO_DRIVER"] = "dummy"
    if p.script is not None:
        env["GCN_INPUT"] = script_text(p.script)
    cmd = [str(game), "--hidden", "--fast", "--no-input-log", f"--pads={p.pads}",
           f"--exit-after={p.exit_after}"]
    log = scratch / "stdout.txt"
    with log.open("wb") as f:
        code = subprocess.run(cmd, cwd=scratch, env=env, stdout=f, stderr=subprocess.STDOUT).returncode
    if code != 0:
        tail = "\n".join(log.read_text(errors="replace").splitlines()[-TAIL_LINES:])
        raise PassFailed(f"{p.name}: the game exited {code}\n{tail}")


class PassFailed(Exception):
    pass


def warm(game: Path, saves: Path, plan: list[Pass]) -> None:
    with tempfile.TemporaryDirectory(prefix="dragoon-warmup-") as d:
        scratch = Path(d)
        (scratch / "saves").mkdir()
        cache = scratch / "saves" / CACHE
        if (saves / CACHE).exists():
            shutil.copyfile(saves / CACHE, cache)
        for p in plan:
            start = time.monotonic()
            run_pass(game, p, scratch)
            print(f"{p.name}: {p.exit_after} frames, {time.monotonic() - start:.1f} s")
        if not cache.exists():
            raise PassFailed(f"the game wrote no {CACHE}")
        install(cache, saves)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", type=Path, default=ROOT / "build" / "dragoon")
    ap.add_argument("--saves", type=Path, default=ROOT / "saves")
    ap.add_argument("--attract-frames", type=int, default=20000)
    ap.add_argument("--force", action="store_true", help="run even if the stamp is current")
    ap.add_argument("--no-routes", action="store_true", help="run only the attract pass")
    args = ap.parse_args(argv)
    try:
        if not args.game.is_file():
            raise ValueError(f"{args.game}: no such game, build it first")
        manifest_text = MANIFEST.read_text()
        want = stamp(engine_rev(), manifest_text)
        stamp_path = args.saves / STAMP
        if not (args.force or args.no_routes) and stamp_path.exists() \
                and stamp_path.read_text().strip() == want:
            print("shader cache is current, nothing to do (--force to rerun)")
            return 0
        routes = [] if args.no_routes else parse_manifest(manifest_text)
        start = time.monotonic()
        try:
            warm(args.game.resolve(), args.saves, passes(routes, args.attract_frames))
        except PassFailed as e:
            print(f"shader warm-up failed, {args.saves} left as it was: {e}", file=sys.stderr)
            return 1
        if not args.no_routes:
            stamp_path.write_text(want + "\n")
        size = (args.saves / CACHE).stat().st_size
        print(f"warm: {1 + len(routes)} passes, {args.saves / CACHE} is {size} bytes, "
              f"{time.monotonic() - start:.1f} s")
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
