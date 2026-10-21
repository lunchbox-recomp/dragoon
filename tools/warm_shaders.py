#!/usr/bin/env python3
"""Warm the player's shader cache by playing the game once, hidden and silent.

Usage: warm_shaders.py [--game build/dragoon] [--saves saves] [--force]

Runs the game in a scratch directory, one pass per route in tests/hashes/manifest.txt, each
from a blank memory card as a fresh install is. (A route that finds the card an earlier
pass made takes other menus and builds other keys.) Every pass is --hidden --fast
--no-input-log with SDL's dummy audio driver, so nothing shows or sounds. The scratch
saves/shaders.bin starts as a copy of <saves>/shaders.bin and grows pass by pass, and the
player's cache is only replaced once every pass has succeeded. Nothing else in <saves> is
read or written except the stamp, <saves>/.shader-warmup. It holds the gcn-recomp commit, a
SHA-1 of the manifest with the route files' text and a SHA-1 of this script. If all three
match and shaders.bin exists, the run is skipped. A pass that outlasts twice its real-time
length plus 30 s is killed and fails. --force runs anyway. --game and --saves default to
build/dragoon and saves under the repository, wherever the tool is run from.

Prints one line per pass and a closing line with the cache's size. A failed pass prints
the game's last output to stderr.

Exits 0 when the cache is warm, whether the passes ran or the stamp was current, 1 when a
pass failed or the game left no shaders.bin (the player's saves are untouched), 2 when it
couldn't run: a bad argument, or a missing game, route or gcn-recomp checkout.
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
CARD_GLOB = "memcard_*.raw"
STAMP = ".shader-warmup"
TAIL_LINES = 15
ROUTE_TAIL_FRAMES = 900  # past the last frame a route must reach, to build what follows it


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
    return [Pass(r.name, max(r.required) + ROUTE_TAIL_FRAMES, route_pads(r), ROUTES / f"{r.name}.txt")
            for r in routes]


def stamp(engine_rev: str, inputs_text: str, tool_sha: str) -> str:
    return f"{engine_rev} {hashlib.sha1(inputs_text.encode()).hexdigest()} {tool_sha}"


def tool_sha() -> str:
    return hashlib.sha1(Path(__file__).read_bytes()).hexdigest()


def engine_rev() -> str:
    """The commit of the gcn-recomp checkout the game was built from."""
    if not (ROOT / "gcn-recomp" / ".git").exists():
        raise ValueError("no gcn-recomp checkout, so the stamp can't name the engine "
                         "(configure with -DDRAGOON_WARMUP=OFF to skip the warm-up)")
    try:
        done = subprocess.run(["git", "-C", str(ROOT / "gcn-recomp"), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        raise ValueError(f"can't read the gcn-recomp commit: {e}") from None
    return done.stdout.strip()


def pass_timeout(exit_after: int) -> float:
    """Twice the pass's length at 60 fps, plus 30 s; --fast should finish well inside it."""
    return 2 * exit_after / 60 + 30


def install(cache_from: Path, saves_dir: Path) -> None:
    """Replace <saves_dir>/shaders.bin with cache_from, whole or not at all.

    The copy goes to a temp file in saves_dir and an os.replace puts it in place, so a reader
    never sees half a file.
    """
    saves_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=CACHE + ".", suffix=".tmp", dir=saves_dir)
    try:
        with os.fdopen(fd, "wb") as out, cache_from.open("rb") as src:
            shutil.copyfileobj(src, out)
            out.flush()
            os.fsync(out.fileno())
        shutil.copymode(cache_from, tmp)
        os.replace(tmp, saves_dir / CACHE)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class PassFailed(Exception):
    pass


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


def warm(game: Path, saves: Path, plan: list[Pass]) -> None:
    with tempfile.TemporaryDirectory(prefix="dragoon-warmup-") as d:
        scratch = Path(d)
        (scratch / "saves").mkdir()
        cache = scratch / "saves" / CACHE
        if (saves / CACHE).exists():
            shutil.copyfile(saves / CACHE, cache)
        for p in plan:
            for card in (scratch / "saves").glob(CARD_GLOB):
                card.unlink()
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
    ap.add_argument("--force", action="store_true", help="run even if the stamp is current")
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
            warm(args.game.resolve(), args.saves, plan)
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
