#!/usr/bin/env python3
"""Did a change alter what the renderer draws? Run routes and compare their frame hashes.

Usage: frame_hashes.py check  [ROUTE ...]
       frame_hashes.py record [ROUTE ...]

Routes and their probe settings are in tests/hashes/manifest.txt; with no ROUTE every route
runs. Goldens are in tests/hashes/gl/<route>.txt, one "frame_NNNNN <sha1>" line per
frame. check prints one status line per route and one line per frame that changed or wasn't
reached. record rewrites the goldens, and writes none for a route that skipped a dump. A
check reads every golden before it runs the game. The frames come from the player's disc, so
they're moved to the Trash once hashed and never committed.

Exits 0 when every route matches (or is recorded), 1 when a frame changed or wasn't reached,
2 on a bad argument, a missing or malformed golden, or a probe.sh run that failed.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from frame_dumps import frame_files
from routes import MANIFEST, Route, parse_manifest, route_file

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe.sh"
HASHES = ROOT / "tests" / "hashes"
GOLDEN_LINE = re.compile(r"frame_(\d{5,}) ([0-9a-f]{40})")


def hash_frames(directory: Path) -> dict[int, str]:
    return {n: hashlib.sha1(p.read_bytes()).hexdigest() for n, p in frame_files(directory).items()}


def read_golden(path: Path) -> dict[int, str]:
    golden = {}
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        m = GOLDEN_LINE.fullmatch(line)
        if not m:
            raise ValueError(f"{path}: line {n}: not 'frame_NNNNN <sha1>': {line!r}")
        golden[int(m[1])] = m[2]
    if not golden:
        raise ValueError(f"{path}: no frames")
    return golden


def format_golden(hashes: dict[int, str], last: int) -> str:
    return "".join(f"frame_{f:05d} {h}\n" for f, h in sorted(hashes.items()) if f <= last)


def compare(golden: dict[int, str], got: dict[int, str]) -> list[str]:
    problems = []
    for f, h in sorted(golden.items()):
        if f not in got:
            problems.append(f"frame {f}: not reached")
        elif got[f] != h:
            problems.append(f"frame {f}: {got[f][:8]} != golden {h[:8]}")
    return problems


def reached(got: dict[int, str], needed: int) -> str:
    if not got:
        return f"reached no frames (needs {needed})"
    return f"reached frame {max(got)} (needs {needed})"


def probe_args(route: Route, name: str) -> list[str]:
    return [str(PROBE), name, str(route.seconds), str(route_file(route.name)),
            str(route.dump_every), *route.extra]


def trash(directory: Path) -> None:
    dest = Path.home() / ".Trash" / f"{directory.name}-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.move(str(directory), str(dest))


def hash_route(route: Route) -> dict[int, str]:
    out = ROOT / "build" / "probe" / f"hashes-{route.name}"
    if out.exists():
        trash(out)  # a blank memory card, and no frames from an older build
    try:
        try:
            subprocess.run(probe_args(route, out.name), check=True, cwd=ROOT,
                           stdout=subprocess.DEVNULL)
        except subprocess.CalledProcessError as e:
            raise ValueError(f"{route.name}: probe.sh exited {e.returncode}") from None
        return hash_frames(out)
    finally:
        if out.exists():
            trash(out)


def record_route(route: Route, got: dict[int, str], path: Path) -> bool:
    last = max(route.required)
    missing = [f for f in range(route.dump_every, last + 1, route.dump_every) if f not in got]
    if missing:
        print(f"{route.name}: didn't reach frames {missing}")
        return False
    text = format_golden(got, last)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print(f"{route.name}: recorded {len(text.splitlines())} frames, {reached(got, last)}")
    return True


def check_route(route: Route, got: dict[int, str], golden: dict[int, str]) -> bool:
    problems = compare(golden, got)
    where = reached(got, max(route.required))
    if problems:
        print(f"{route.name}: {len(problems)} problem(s), {where}")
        for p in problems:
            print(f"  {p}")
    else:
        print(f"{route.name}: OK, {len(golden)} frames match, {where}")
    return not problems


def select_routes(names: list[str]) -> list[Route]:
    routes = parse_manifest(MANIFEST.read_text())
    unknown = set(names) - {r.name for r in routes}
    if unknown:
        raise ValueError(f"not in the manifest: {sorted(unknown)}")
    return [r for r in routes if r.name in names] if names else routes


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["check", "record"])
    ap.add_argument("routes", nargs="*")
    args = ap.parse_args(argv)
    try:
        routes = select_routes(args.routes)
        paths = {r.name: HASHES / "gl" / f"{r.name}.txt" for r in routes}
        goldens = {r.name: read_golden(paths[r.name]) for r in routes} if args.mode == "check" else {}
        failed = 0
        for route in routes:
            got = hash_route(route)
            if args.mode == "record":
                ok = record_route(route, got, paths[route.name])
            else:
                ok = check_route(route, got, goldens[route.name])
            failed += not ok
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
