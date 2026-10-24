#!/usr/bin/env python3
"""Summarize a GCN_FRAMETIME=1 log: frame pacing, render cost and shader stalls.

Usage: frametime.py LOG [--from N] [--slow MS] [--late MS] [--json]

LOG is a run's stdout.txt from tools/probe.sh, or any log with [ft], [rt] and [shaders]
lines. Prints the guest's interval between presents and the renderer's issue time from
frame N on (mean, sd, p95, p99, worst), then each frame whose render time is over --slow MS
(default 16.7) with its batch shape and the shaders compiled in it, then each frame whose
guest interval is over --late MS (default 25). The sd is the population standard deviation.
--from N (default 300) starts the summary at frame N. A [shaders] line belongs to the next
[rt] line, since both come from the render thread. --json prints the same result as JSON.

Frame numbers are the [rt] lines'; a frame's batch is the [ft] line one lower. A game that
copies a frame to the display in strips prints more than one [ft] line a batch, which this
pairing doesn't follow.

Exits 0 once it has read the log, 2 on a bad argument or a log it can't read or that has no
frame from N on.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# The trailing \s: a line cut off mid-number must not parse.
FT = re.compile(r"^\[ft\] f(\d+) guest\s+([\d.]+)ms.*?"
                r"(draws\s+\d+/\s*\d+\s+verts\s+\d+\s+idx\s+\d+)\s")
RT = re.compile(r"^\[rt\] f(\d+) render\s+([\d.]+)ms")
SHADER = re.compile(r"^\[shaders\] compiled program \d+ in ([\d.]+) ms")


@dataclass
class Frame:
    guest_ms: float | None = None
    shape: str = ""
    render_ms: float | None = None
    compiles: list[float] = field(default_factory=list)


def parse(lines) -> dict[int, Frame]:
    """Frames keyed by their [rt] number. [ft] fN is printed before the engine counts the
    frame (xf.cpp:1928-1935) and [rt] after (render_gl.cpp:3981), so the batch [ft] fN
    describes is drawn as [rt] f(N+1)."""
    frames: dict[int, Frame] = {}
    pending: list[float] = []
    for line in lines:
        if m := FT.match(line):
            frame = frames.setdefault(int(m[1]) + 1, Frame())
            frame.guest_ms = float(m[2])
            frame.shape = " ".join(re.sub(r"/\s+", "/", m[3]).split())
        elif m := SHADER.match(line):
            pending.append(float(m[1]))
        elif m := RT.match(line):
            frame = frames.setdefault(int(m[1]), Frame())
            frame.render_ms = float(m[2])
            frame.compiles = pending
            pending = []
    return frames


def percentile(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[max(0, math.ceil(p * len(s) / 100) - 1)]


def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    return {"n": len(values), "mean": sum(values) / len(values), "sd": statistics.pstdev(values),
            "p95": percentile(values, 95), "p99": percentile(values, 99), "worst": max(values)}


def summary(frames: dict[int, Frame], start: int) -> dict:
    later = [f for n, f in frames.items() if n >= start]
    return {"guest": _stats([f.guest_ms for f in later if f.guest_ms is not None]),
            "render": _stats([f.render_ms for f in later if f.render_ms is not None])}


def slow(frames: dict[int, Frame], start: int, ms: float) -> list[tuple[int, Frame]]:
    return [(n, f) for n, f in sorted(frames.items())
            if n >= start and f.render_ms is not None and f.render_ms > ms]


def late(frames: dict[int, Frame], start: int, ms: float) -> list[tuple[int, float]]:
    """Frames from `start` on whose guest interval is over `ms`, with that interval."""
    return [(n, f.guest_ms) for n, f in sorted(frames.items())
            if n >= start and f.guest_ms is not None and f.guest_ms > ms]


def read_frames(log: Path, start: int) -> dict[int, Frame]:
    with log.open(errors="replace") as lines:
        frames = parse(lines)
    if not frames:
        raise ValueError(f"{log}: no [ft] or [rt] lines; was GCN_FRAMETIME=1 set?")
    if max(frames) < start:
        raise ValueError(f"{log}: no frames from {start} on; the log ends at frame {max(frames)}")
    return frames


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log", type=Path)
    ap.add_argument("--from", dest="start", type=int, default=300)
    ap.add_argument("--slow", type=float, default=16.7)
    ap.add_argument("--late", type=float, default=25.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        frames = read_frames(args.log, args.start)
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    stats = summary(frames, args.start)
    over = slow(frames, args.start, args.slow)
    behind = late(frames, args.start, args.late)
    if args.json:
        print(json.dumps({"summary": stats, "slow": [{"frame": n, **asdict(f)} for n, f in over],
                          "late": [{"frame": n, "guest_ms": ms} for n, ms in behind]}, indent=1))
        return 0
    for name, s in stats.items():
        if s["n"]:
            print(f"{name:6} from {args.start}: n {s['n']}  mean {s['mean']:.2f}  sd {s['sd']:.2f}"
                  f"  p95 {s['p95']:.2f}  p99 {s['p99']:.2f}  worst {s['worst']:.2f} ms")
    print(f"frames over {args.slow} ms: {len(over)}")
    for n, f in over:
        shaders = f"  {len(f.compiles)} shaders, {sum(f.compiles):.0f} ms" if f.compiles else ""
        print(f"  f{n}  render {f.render_ms:.2f} ms  {f.shape}{shaders}")
    print(f"guest intervals over {args.late} ms: {len(behind)}")
    for n, ms in behind:
        print(f"  f{n}  guest {ms:.2f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
