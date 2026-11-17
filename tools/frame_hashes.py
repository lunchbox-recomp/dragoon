#!/usr/bin/env python3
"""Did a change alter what the renderer draws? Run routes and compare their frame hashes.

Usage: frame_hashes.py check  [ROUTE ...] [--slow=N] [--aspect=16:9]
       frame_hashes.py record [ROUTE ...] [--aspect=16:9]

Routes and their probe settings are in tests/hashes/manifest.txt; with no ROUTE every route
runs. Goldens are in tests/hashes/gl/<route>.txt, one "frame_NNNNN <sha1>" line per
frame. --aspect=16:9 runs each route with probe.sh --aspect=16:9 and keeps its goldens in
tests/hashes/gl-16x9/ instead. --aspect=4:3 is the default, and gives probe.sh no --aspect,
as the 4:3 goldens were recorded. check prints one status line per route and one line per
frame that changed or wasn't reached. record rewrites the goldens, and writes none for a
route that skipped a dump. A check reads every golden before it runs the game. The frames
come from the player's disc, so they're deleted once hashed and never committed.

--slow=N gives each route N times its seconds, for a build that runs slower than the one the
goldens came from. N is a whole number from 1 and defaults to 1. record refuses it, since
goldens come from a build at full speed.

With N above 1 a route also quits one dump interval past its last frame (probe.sh
--exit-after), so a fast build doesn't spend the extra seconds. Nothing else about a run
changes.

Exits 0 when every route matches (or is recorded), 1 when a frame changed or wasn't reached,
2 on a bad argument, a missing or malformed golden, or a probe.sh run that failed.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

from frame_dumps import frame_files
from probe_dirs import remove_run, run_probe, slow_factor
from routes import MANIFEST, Route, route_file, select_routes

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe.sh"
HASHES = ROOT / "tests" / "hashes"
GOLDEN_LINE = re.compile(r"frame_(\d{5,}) ([0-9a-f]{40})")
# Each aspect a route is hashed at, and the directory under HASHES its goldens are in
GOLDENS = {"4:3": "gl", "16:9": "gl-16x9"}
DEFAULT_ASPECT = "4:3"


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


def probe_args(route: Route, name: str, slow: int, aspect: str = DEFAULT_ASPECT) -> list[str]:
    stop = [f"--exit-after={max(route.required) + route.dump_every}"] if slow > 1 else []
    wide = [] if aspect == DEFAULT_ASPECT else [f"--aspect={aspect}"]
    return [str(PROBE), name, str(route.seconds * slow), str(route_file(route.name)),
            str(route.dump_every), *stop, *wide, *route.extra]


def hash_route(route: Route, slow: int = 1, aspect: str = DEFAULT_ASPECT) -> dict[int, str]:
    out = ROOT / "build" / "probe" / f"hashes-{route.name}"
    if out.exists():
        remove_run(out)  # a blank memory card, and no frames from an older build
    try:
        run_probe(probe_args(route, out.name, slow, aspect), ROOT, route.name)
        return hash_frames(out)
    finally:
        if out.exists():
            remove_run(out)


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


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["check", "record"])
    ap.add_argument("routes", nargs="*")
    ap.add_argument("--slow", default=None, metavar="N",
                    help="check: give each route N times its seconds (default 1)")
    ap.add_argument("--aspect", choices=GOLDENS, default=DEFAULT_ASPECT,
                    help="the picture's aspect, and so which goldens (default 4:3)")
    args = ap.parse_args(argv)
    if args.mode == "record" and args.slow is not None:
        ap.error("--slow is for check")
    try:
        slow = 1 if args.slow is None else slow_factor(args.slow)
        routes = select_routes(args.routes, MANIFEST)
        paths = {r.name: HASHES / GOLDENS[args.aspect] / f"{r.name}.txt" for r in routes}
        goldens = {r.name: read_golden(paths[r.name]) for r in routes} if args.mode == "check" else {}
        failed = 0
        for route in routes:
            got = hash_route(route, slow, args.aspect)
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
