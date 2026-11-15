#!/usr/bin/env python3
"""Summarize a GCN_FRAMETIME=1 log: frame pacing, render cost and shader stalls.

Usage: frametime.py LOG [--from N] [--slow MS] [--late MS] [--json]
       frametime.py --menu LOG [LOG ...] [--json]

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

--menu reads the overlay menu's lines instead, "[overlay] frame f<n> held <0|1> interval
<ms>ms  cpu <ms>ms  late <ms>ms  present <ms>ms  blur <ms>ms" (gcn-recomp docs/diagnostics.md),
from each LOG, one run each, pooled. An engine before gcn-recomp 236e1f4 prints no late, present
or blur, and a line may end after any of them. A log's first line and each line with interval 0
start an open. It prints the opens, the paused redraw interval from the held 1 lines that have
one, and the late, present and blur of those same lines that have each, then the menu's CPU time
over every frame it drew, each with n, p50, p99 and max, then the CPU time of each log's f0
line, the first frame of the process's first open. A log whose lines don't start at f0 says it
has none. --from, --slow and --late don't apply to it.

Exits 0 once it has read the logs, 2 on a bad argument, a log it can't read, a log with no
frame from N on, or under --menu one with no [overlay] frame line.
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
# The last ms stops a line cut off mid-number, and the $ one with more text after it. A line
# with no held field, from an engine before gcn-recomp 9776d98, doesn't parse. late, present and
# blur came in 236e1f4, in that order, and each one there is read.
MENU = re.compile(r"^\[overlay\] frame f(\d+) held ([01]) interval\s+([\d.]+)ms\s+cpu\s+([\d.]+)ms"
                  r"(?:\s+late\s+([\d.]+)ms)?(?:\s+present\s+([\d.]+)ms)?(?:\s+blur\s+([\d.]+)ms)?$")
# The fields of a held redraw's line that split its interval, as --menu prints them.
PRE_FIELDS = (("late", "held wait's lateness (late)"), ("present", "draw before the menu (present)"),
              ("blur", "blurred backdrop (blur)"))


@dataclass
class Frame:
    guest_ms: float | None = None
    shape: str = ""
    render_ms: float | None = None
    compiles: list[float] = field(default_factory=list)


def parse(lines) -> dict[int, Frame]:
    """Frames keyed by their [rt] number. [ft] fN is printed before the engine counts the
    frame (xf.cpp:1843-1850) and [rt] after (render_gl_batch.cpp:180, 522-523), so the
    batch [ft] fN describes is drawn as [rt] f(N+1)."""
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


@dataclass
class MenuFrame:
    n: int
    held: bool
    interval_ms: float
    cpu_ms: float
    late_ms: float | None = None  # None where the line has no such field
    present_ms: float | None = None
    blur_ms: float | None = None


def parse_menu(lines) -> list[MenuFrame]:
    """The [overlay] frame lines, in the order the log has them."""
    frames = []
    for line in lines:
        if m := MENU.match(line.rstrip("\r\n")):
            late, present, blur = (None if v is None else float(v) for v in m.group(5, 6, 7))
            frames.append(MenuFrame(int(m[1]), m[2] == "1", float(m[3]), float(m[4]), late, present, blur))
    return frames


def menu_opens(frames: list[MenuFrame]) -> list[list[MenuFrame]]:
    """One log's frames by open. An open's first frame has no interval, which the line gives
    as 0, and so does the log's first frame. A reopen during a fade out keeps its interval,
    so it counts with the open before it."""
    opens: list[list[MenuFrame]] = []
    for f in frames:
        if not opens or f.interval_ms == 0:
            opens.append([])
        opens[-1].append(f)
    return opens


def held_redraws(frames: list[MenuFrame]) -> list[MenuFrame]:
    """The paused redraws: the held 1 lines, less an open's first frame, which has an interval
    of 0. A fade out and the frames before the hold lands are paced by the guest."""
    return [f for f in frames if f.held and f.interval_ms > 0]


def redraws(frames: list[MenuFrame]) -> list[float]:
    """The paused redraw intervals."""
    return [f.interval_ms for f in held_redraws(frames)]


def _spread(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    return {"n": len(values), "p50": percentile(values, 50), "p99": percentile(values, 99),
            "max": max(values)}


def menu_summary(logs: dict[str, list[MenuFrame]]) -> dict:
    """Every log's frames pooled, and the CPU time of each log's f0, None where its first line
    isn't f0."""
    frames = [f for fs in logs.values() for f in fs]
    first = {name: fs[0].cpu_ms if fs[0].n == 0 else None for name, fs in logs.items()}
    held = held_redraws(frames)
    pre = {key: _spread([ms for f in held if (ms := getattr(f, f"{key}_ms")) is not None])
           for key, _ in PRE_FIELDS}
    return {"logs": len(logs), "opens": sum(len(menu_opens(fs)) for fs in logs.values()),
            "frames": len(frames), "interval": _spread(redraws(frames)), **pre,
            "cpu": _spread([f.cpu_ms for f in frames]),
            "first_cpu": _spread([ms for ms in first.values() if ms is not None]), "first": first}


def read_menu(log: Path) -> list[MenuFrame]:
    with log.open(errors="replace") as lines:
        try:
            frames = parse_menu(lines)
        except ValueError as e:  # a time such as 1.2.3, which the pattern lets through
            raise ValueError(f"{log}: an [overlay] frame line has a bad number: {e}") from None
    if not frames:
        raise ValueError(f"{log}: no [overlay] frame lines; was GCN_FRAMETIME=1 set and the menu "
                         f"open? An engine before gcn-recomp 9776d98 prints them with no held field")
    return frames


def print_menu(s: dict) -> None:
    print(f"menu: {s['logs']} logs, {s['opens']} opens, {s['frames']} frames")
    for key, label, places in (("interval", "paused redraw interval (held 1)", 2),
                               *((key, f"  {label}", 3) for key, label in PRE_FIELDS),
                               ("cpu", "menu cpu a frame", 3),
                               ("first_cpu", "first menu frame of each process (f0) cpu", 3)):
        v = s[key]
        if v["n"]:
            print(f"{label}: n {v['n']}  p50 {v['p50']:.{places}f}  p99 {v['p99']:.{places}f}"
                  f"  max {v['max']:.{places}f} ms")
        else:
            print(f"{label}: n 0")
    for name, ms in s["first"].items():
        print(f"  {name}  " + (f"f0 cpu {ms:.3f} ms" if ms is not None else "no f0 line"))


def menu_main(logs: list[Path], as_json: bool) -> int:
    try:
        frames = {str(log): read_menu(log) for log in logs}
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    s = menu_summary(frames)
    if as_json:
        print(json.dumps(s, indent=1))
    else:
        print_menu(s)
    return 0


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
    ap.add_argument("logs", type=Path, nargs="+", metavar="LOG")
    ap.add_argument("--from", dest="start", type=int, default=None)
    ap.add_argument("--slow", type=float, default=None)
    ap.add_argument("--late", type=float, default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--menu", action="store_true")
    args = ap.parse_args(argv)
    if args.menu:
        if (args.start, args.slow, args.late) != (None, None, None):
            ap.error("--from, --slow and --late don't apply to --menu")
        return menu_main(args.logs, args.json)
    if len(args.logs) > 1:
        ap.error("one LOG, unless --menu")
    args.log = args.logs[0]
    args.start = 300 if args.start is None else args.start
    args.slow = 16.7 if args.slow is None else args.slow
    args.late = 25.0 if args.late is None else args.late
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
            print(f"{name:6} from {args.start}: n {s['n']}  mean {s['mean']:.2f}  sd {s['sd']:.3f}"
                  f"  p95 {s['p95']:.2f}  p99 {s['p99']:.2f}  worst {s['worst']:.2f} ms")
    print(f"frames over {args.slow} ms: {len(over)}")
    for n, f in over:
        shaders = f"  {len(f.compiles)} shaders, {sum(f.compiles):.0f} ms" if f.compiles else ""
        print(f"  f{n}  render {f.render_ms:.2f} ms  {f.shape}{shaders}")
    if stats["guest"]["n"]:
        print(f"guest intervals over {args.late} ms: {len(behind)}")
        for n, ms in behind:
            print(f"  f{n}  guest {ms:.2f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
