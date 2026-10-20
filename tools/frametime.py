#!/usr/bin/env python3
"""Summarize a GCN_FRAMETIME=1 log: frame pacing, render cost and shader stalls.

Usage: frametime.py LOG [--from N] [--slow MS] [--json]

LOG is a run's stdout.txt from tools/probe.sh, or any log with [ft], [rt] and [shaders]
lines. Prints the guest's interval between presents and the renderer's issue time from
frame N on (mean, p95, p99, worst), then each frame whose render time is over MS
(default 16.7) with its batch shape and the shaders compiled in it. A [shaders] line
belongs to the next [rt] line, since both come from the render thread.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import asdict, dataclass, field

FT = re.compile(r"^\[ft\] f(\d+) guest\s+([\d.]+)ms.*?(draws\s+\d+/\s*\d+\s+verts\s+\d+\s+idx\s+\d+)")
RT = re.compile(r"^\[rt\] f(\d+) render\s+([\d.]+)ms")
SHADER = re.compile(r"^\[shaders\] compiled program \d+ in ([\d.]+) ms")


@dataclass
class Frame:
    guest_ms: float | None = None
    shape: str = ""
    render_ms: float | None = None
    compiles: list[float] = field(default_factory=list)


def parse(lines) -> dict[int, Frame]:
    frames: dict[int, Frame] = {}
    pending: list[float] = []
    for line in lines:
        if m := FT.match(line):
            f = frames.setdefault(int(m[1]), Frame())
            f.guest_ms, f.shape = float(m[2]), " ".join(re.sub(r"/\s+", "/", m[3]).split())
        elif m := SHADER.match(line):
            pending.append(float(m[1]))
        elif m := RT.match(line):
            f = frames.setdefault(int(m[1]), Frame())
            f.render_ms, f.compiles, pending = float(m[2]), pending, []
    return frames


def percentile(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[max(0, math.ceil(p * len(s) / 100) - 1)]


def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    return {"n": len(values), "mean": sum(values) / len(values), "p95": percentile(values, 95),
            "p99": percentile(values, 99), "worst": max(values)}


def summary(frames: dict[int, Frame], start: int) -> dict:
    later = [f for n, f in frames.items() if n >= start]
    return {"guest": _stats([f.guest_ms for f in later if f.guest_ms is not None]),
            "render": _stats([f.render_ms for f in later if f.render_ms is not None])}


def slow(frames: dict[int, Frame], start: int, ms: float) -> list[tuple[int, Frame]]:
    return [(n, f) for n, f in sorted(frames.items())
            if n >= start and f.render_ms is not None and f.render_ms > ms]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Summarize a GCN_FRAMETIME=1 log.")
    ap.add_argument("log")
    ap.add_argument("--from", dest="start", type=int, default=300)
    ap.add_argument("--slow", type=float, default=16.7)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    with open(args.log, errors="replace") as f:
        frames = parse(f)
    result = {"summary": summary(frames, args.start),
              "slow": [{"frame": n, **asdict(f)} for n, f in slow(frames, args.start, args.slow)]}
    if args.json:
        print(json.dumps(result, indent=1))
        return 0
    for name, s in result["summary"].items():
        if s["n"]:
            print(f"{name:6} from {args.start}: n {s['n']}  mean {s['mean']:.2f}  p95 {s['p95']:.2f}"
                  f"  p99 {s['p99']:.2f}  worst {s['worst']:.2f} ms")
    print(f"frames over {args.slow} ms: {len(result['slow'])}")
    for s in result["slow"]:
        shaders = f"  {len(s['compiles'])} shaders, {sum(s['compiles']):.0f} ms" if s["compiles"] else ""
        print(f"  f{s['frame']}  render {s['render_ms']:.2f} ms  {s['shape']}{shaders}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
