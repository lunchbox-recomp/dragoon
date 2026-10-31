#!/usr/bin/env python3
"""Did a change alter what the AX mixer outputs? Run routes and compare their audio hashes.

Usage: audio_hashes.py check  [ROUTE ...] [--slow=N]
       audio_hashes.py record [ROUTE ...] [--lists N,N,...]

Routes and their probe settings are in tests/hashes/manifest.txt; with no ROUTE every route
runs. Each runs through tools/probe.sh --bench with GCN_AXSTATS=1 and SDL's dummy audio
driver, and the game prints "[ax] hash list=N fnv=X" every 400 command lists: a running
FNV-1a over every output block the mixer has written since boot. Goldens are in
tests/hashes/audio/<route>.txt, one "N X" line per list count, with no frame numbers because
lists per presented frame isn't constant. They hold for unpaced runs only. check prints one
status line per route and one line per list count that changed or wasn't reached, and a
run that stops short of a golden's last list count fails. record rewrites the goldens at
--lists, or at the list counts each route's golden already has, and writes none for a route
that didn't reach one. A check reads every golden before it runs the game. No audio is
captured or kept, only the hashes.

--slow=N gives each route N times its seconds, for a build that runs slower than the one the
goldens came from. N is a whole number from 1 and defaults to 1. record refuses it, since
goldens come from a build at full speed.

A bench takes no --exit-after, so a fast build spends all N times the seconds. Nothing else
about a run changes.

A bench that crashes prints no report, and probe.sh exits 1. That counts as a route that doesn't
match, so check says the bench printed no report and fails the lists it didn't reach. record
and any other probe.sh failure are an error, and record writes no golden.

Exits 0 when every route matches (or is recorded), 1 when a hash changed, a list count wasn't
reached or a checked bench printed no report, 2 on a bad argument, a missing or malformed
golden, or a probe.sh run that failed any other way.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from probe_dirs import ProbeFailed, remove_run, run_probe, slow_factor
from routes import MANIFEST, Route, route_file, select_routes

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe.sh"
HASHES = ROOT / "tests" / "hashes"
AX_HASH = re.compile(r"^\[ax\] hash list=(\d+) fnv=([0-9A-F]{16})$", re.MULTILINE)
GOLDEN_LINE = re.compile(r"(\d+) ([0-9A-F]{16})")
LIST_STEP = 400  # the game prints a hash line every 400 command lists
HEADER = """\
# AX output hashes for the {route} route: list count, then the running FNV-1a over every output block
# the mixer has written since boot, as GCN_AXSTATS=1 prints it. They hold for unpaced runs only:
# tools/probe.sh --bench, the way tools/audio_hashes.py runs them. Paced runs make catch-up jumps.
# Rows carry no frame number, because lists per presented frame isn't constant.
"""


def parse_hashes(text: str) -> dict[int, str]:
    return {int(n): h for n, h in AX_HASH.findall(text)}


def read_golden(path: Path) -> dict[int, str]:
    golden: dict[int, str] = {}
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        m = GOLDEN_LINE.fullmatch(line)
        if not m:
            raise ValueError(f"{path}: line {n}: not 'LIST FNV': {line!r}")
        count = int(m[1])
        if count <= 0 or count % LIST_STEP:
            raise ValueError(f"{path}: line {n}: list {count} is not a positive multiple of {LIST_STEP}")
        if count in golden:
            raise ValueError(f"{path}: line {n}: list {count} is there twice")
        golden[count] = m[2]
    if not golden:
        raise ValueError(f"{path}: no rows")
    return golden


def format_golden(route: str, hashes: dict[int, str], lists: list[int]) -> str:
    return HEADER.format(route=route) + "".join(f"{n} {hashes[n]}\n" for n in sorted(lists))


def compare(golden: dict[int, str], got: dict[int, str]) -> list[str]:
    problems = []
    for n, h in sorted(golden.items()):
        if n not in got:
            problems.append(f"list {n}: not reached")
        elif got[n] != h:
            problems.append(f"list {n}: {got[n]} != golden {h}")
    return problems


def reached(got: dict[int, str], needed: int) -> str:
    if not got:
        return f"reached no lists (needs {needed})"
    return f"reached list {max(got)} (needs {needed})"


def probe_args(route: Route, name: str, slow: int) -> list[str]:
    return [str(PROBE), name, str(route.seconds * slow), str(route_file(route.name)),
            str(route.dump_every), "GCN_AXSTATS=1", "--bench", *route.extra]


def hash_route(route: Route, slow: int = 1, allow_crash: bool = False) -> dict[int, str]:
    """The hashes ROUTE's bench printed. A bench that printed no report (probe.sh exits 1) is a
    ProbeFailed, unless ALLOW_CRASH, which says so and returns the hashes it got to."""
    out = ROOT / "build" / "probe" / f"audio-{route.name}"
    if out.exists():
        remove_run(out)  # a blank memory card; the last run stays after this one, for its [ax] lines
    name = out.name
    try:
        run_probe(probe_args(route, name, slow), ROOT, route.name, {**os.environ, "SDL_AUDIO_DRIVER": "dummy"})
    except ProbeFailed as e:
        if e.returncode != 1 or not allow_crash:  # 1 is the bench printing no report, which a crash does
            raise
        print(f"{route.name}: the bench printed no report")
    return parse_hashes((out / "stdout.txt").read_text())


def record_route(route: Route, got: dict[int, str], lists: list[int], path: Path) -> bool:
    missing = [n for n in lists if n not in got]
    if missing:
        print(f"{route.name}: didn't reach lists {missing}, {reached(got, max(lists))}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_golden(route.name, got, lists))
    print(f"{route.name}: recorded {len(lists)} rows, {reached(got, max(lists))}")
    return True


def check_route(route: Route, got: dict[int, str], golden: dict[int, str]) -> bool:
    problems = compare(golden, got)
    where = reached(got, max(golden))
    if problems:
        print(f"{route.name}: {len(problems)} problem(s), {where}")
        for p in problems:
            print(f"  {p}")
    else:
        print(f"{route.name}: OK, {len(golden)} rows match, {where}")
    return not problems


def parse_lists(text: str) -> list[int]:
    chosen = []
    for item in filter(None, text.split(",")):
        n = int(item)
        if n <= 0 or n % LIST_STEP:
            raise ValueError(f"--lists: {n} is not a positive multiple of {LIST_STEP}")
        chosen.append(n)
    if len(set(chosen)) != len(chosen):
        raise ValueError(f"--lists: {text} names a list count twice")
    return chosen


def lists_to_record(path: Path, chosen: list[int]) -> list[int]:
    if chosen:
        return chosen
    if not path.exists():
        raise ValueError(f"{path}: no golden to take list counts from; pass --lists")
    return sorted(read_golden(path))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["check", "record"])
    ap.add_argument("routes", nargs="*")
    ap.add_argument("--lists", default=None, help="record: comma-separated list counts")
    ap.add_argument("--slow", default=None, metavar="N",
                    help="check: give each route N times its seconds (default 1)")
    args = ap.parse_args(argv)
    if args.mode == "check" and args.lists is not None:
        ap.error("--lists is for record")
    if args.mode == "record" and args.slow is not None:
        ap.error("--slow is for check")
    try:
        slow = 1 if args.slow is None else slow_factor(args.slow)
        chosen = parse_lists(args.lists) if args.lists is not None else []
        if args.lists is not None and not chosen:
            raise ValueError("--lists names no list counts")
        routes = select_routes(args.routes, MANIFEST)
        paths = {r.name: HASHES / "audio" / f"{r.name}.txt" for r in routes}
        goldens = {r.name: read_golden(paths[r.name]) for r in routes} if args.mode == "check" else {}
        wanted = ({r.name: lists_to_record(paths[r.name], chosen) for r in routes}
                  if args.mode == "record" else {})
        failed = 0
        for route in routes:
            got = hash_route(route, slow, allow_crash=args.mode == "check")
            if args.mode == "record":
                ok = record_route(route, got, wanted[route.name], paths[route.name])
            else:
                ok = check_route(route, got, goldens[route.name])
            failed += not ok
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
