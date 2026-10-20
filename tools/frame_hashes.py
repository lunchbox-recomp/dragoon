#!/usr/bin/env python3
"""Run routes and compare their frame hashes with committed goldens.

Usage:
  frame_hashes.py check  [--backend gl|metal] [ROUTE ...]
  frame_hashes.py record [--backend gl|metal] [ROUTE ...]

Routes and their probe settings are in tests/hashes/manifest.txt. Goldens are in
tests/hashes/<backend>/<route>.txt, one "frame_NNNNN <sha1>" line per frame. The frames come
from the player's disc, so they're moved to the Trash once hashed and never committed.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe.sh"
HASHES = ROOT / "tests" / "hashes"
FRAME = re.compile(r"frame_(\d+)\.png$")


@dataclass
class Route:
    name: str
    seconds: int
    dump_every: int
    required: list[int]
    extra: list[str]


def parse_manifest(text: str) -> list[Route]:
    routes = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, seconds, every, required, *extra = line.split()
        routes.append(Route(name, int(seconds), int(every),
                            [int(f) for f in required.split(",")], extra))
    return routes


def hash_frames(directory: Path) -> dict[int, str]:
    out = {}
    for p in directory.iterdir():
        m = FRAME.search(p.name)
        if m:
            out[int(m.group(1))] = hashlib.sha1(p.read_bytes()).hexdigest()
    return out


def read_golden(text: str) -> dict[int, str]:
    out = {}
    for line in text.splitlines():
        m = re.fullmatch(r"frame_(\d+) ([0-9a-f]{40})", line.strip())
        if m:
            out[int(m.group(1))] = m.group(2)
    return out


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


def run_route(route: Route, backend: str) -> Path:
    name = f"hashes-{backend}-{route.name}"
    args = [str(PROBE), name, str(route.seconds),
            str(ROOT / "tests" / "routes" / f"{route.name}.txt"), str(route.dump_every),
            *route.extra, f"--renderer={backend}"]
    subprocess.run(args, check=True, cwd=ROOT)
    return ROOT / "build" / "probe" / name


def trash(directory: Path) -> None:
    dest = Path.home() / ".Trash" / f"{directory.name}-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.move(str(directory), str(dest))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Compare route frame hashes with goldens.")
    ap.add_argument("mode", choices=["check", "record"])
    ap.add_argument("--backend", choices=["gl", "metal"], default="gl")
    ap.add_argument("routes", nargs="*")
    args = ap.parse_args(argv)
    routes = parse_manifest((HASHES / "manifest.txt").read_text())
    unknown = set(args.routes) - {r.name for r in routes}
    if unknown:
        print(f"not in the manifest: {sorted(unknown)}", file=sys.stderr)
        return 2
    if args.routes:
        routes = [r for r in routes if r.name in args.routes]
    failed = 0
    for route in routes:
        out = run_route(route, args.backend)
        got = hash_frames(out)
        trash(out)
        golden_path = HASHES / args.backend / f"{route.name}.txt"
        if args.mode == "record":
            missing = [f for f in route.required if f not in got]
            if missing:
                print(f"{route.name}: didn't reach frames {missing}")
                failed += 1
                continue
            golden_path.parent.mkdir(parents=True, exist_ok=True)
            golden_path.write_text(format_golden(got, max(route.required)))
            print(f"{route.name}: recorded {len(read_golden(golden_path.read_text()))} frames, "
                  f"{reached(got, max(route.required))}")
            continue
        problems = compare(read_golden(golden_path.read_text()), got)
        status = 'OK' if not problems else f'{len(problems)} problem(s)'
        print(f"{route.name}: {status}, {reached(got, max(route.required))}")
        for p in problems:
            print(f"  {p}")
        failed += bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
