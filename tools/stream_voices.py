#!/usr/bin/env python3
"""Which voices did the mixer stop that the game didn't? Read a GCN_AXVOICES=1 log.

Usage: stream_voices.py STDOUT

STDOUT is a run's stdout.txt with "[axv]" lines (docs/diagnostics.md in gcn-recomp). It prints
each voice that ran with stream=1 or looping=1, and each one that ended early, by parameter
block address, with the list it started at, the loop address it started with, how many times it
looped, its last level peak and how it ended:

  still running at the end of the log
  stopped by the game       a "stop" line
  ended by the mixer        an "end" line
  ended early               an "end" line on a stream, or on a moved voice with no loop flag

The mixer ends a voice only with its loop flag clear, and the SDK can drop a stream's flag, so
a clear flag says nothing. A voice ended early when any of its lines had a stream's loop address
(018xxxxx, or the PCM16 ring at 0062A280 or 0062A780), or when a "set" line moved its loop or
end address while it ran and no line of it ever had stream=1 or looping=1. The game starts new
samples on blocks that still run an effect, so away from a stream address a voice that had a
flag and lost it isn't called early, and neither is a "set" that puts cur on the new loop
address, which restarts the block and moves nothing. A failure outside the stream addresses
with no "set" between its "run" and its "end" shows only in the count of other voices. Each
early row names the rule, the list and the time (a list is 5 ms), and comes last,
whether or not the voice ever had a flag. The other voices the mixer ended, which never had
stream=1 or looping=1, are counted and not listed. A parameter block that runs again after it
stops or ends is a voice for each run. It only reports, so it never exits 1.

Exits 0 once it has read the log, 2 on a bad argument or a log it can't read or that has no
[axv] lines.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

LIST_MS = 5
# Each ends on its last field's whole value, so a line cut off mid-field doesn't parse.
STATE = re.compile(r"^\[axv\] list=(\d+) pb=([0-9A-F]{8}) (run|stop|set|seek|loop|end) "
                   r"run=\d looping=(\d) stream=(\d) .*\bloop=([0-9A-F]{8}) end=([0-9A-F]{8}) "
                   r"cur=([0-9A-F]{8}) ratio=[0-9A-F]{8}$")
LEVEL = re.compile(r"^\[axv\] list=(\d+) pb=([0-9A-F]{8}) level peak=(\d+) cur=[0-9A-F]{8}$")
STREAM = re.compile(r"^(018[0-9A-F]{5}|0062A280|0062A780)$")
RUNNING = "still running"
GAME = "stopped by the game"
MIXER = "ended by the mixer"
EARLY = "ended early"
AT_STREAM = "its loop address is a stream's"
MOVED = "the game moved its loop or end but it never had a loop flag"


@dataclass
class Voice:
    pb: str
    start: int
    at: str  # its loop address when it started, which tells a stream from a sound effect
    loop: str  # its loop and end address on its last line
    end: str
    loops: int = 0
    peak: int | None = None
    how: str = RUNNING
    end_list: int | None = None
    listed: bool = False  # ran with stream=1 or looping=1
    on_stream: bool = False  # had a stream's loop address on some line
    moved: bool = False  # a line gave another loop or end address than the one before, with cur elsewhere
    why: list[str] = field(default_factory=list)  # what made an end early


def parse(text: str) -> tuple[list[Voice], int, int]:
    """The voices in TEXT that ran with stream=1 or looping=1 or ended early, in the order they
    started, the last list any [axv] line gives, and how many other voices the mixer ended.
    Raises ValueError for a log with no [axv] line."""
    voices: list[Voice] = []
    current: dict[str, Voice] = {}  # the voice each address runs now, or ran last
    last = 0
    seen = False
    for line in text.splitlines():
        if m := LEVEL.match(line):
            seen = True
            last = max(last, int(m[1]))
            if m[2] in current:
                current[m[2]].peak = int(m[3])
            continue
        m = STATE.match(line)
        if not m:
            continue
        seen = True
        n, pb, kind, looping, stream, loop, end, cur = int(m[1]), m[2], m[3], m[4], m[5], m[6], m[7], m[8]
        last = max(last, n)
        if kind == "run" or pb not in current:
            current[pb] = Voice(pb, n, loop, loop, end)
            voices.append(current[pb])
        v = current[pb]
        v.listed = v.listed or "1" in (looping, stream)
        v.on_stream = v.on_stream or bool(STREAM.match(loop))
        # A set that puts cur on the new loop address starts a new sample on the block, not a move.
        v.moved = v.moved or ((loop, end) != (v.loop, v.end) and cur != loop)
        v.loop, v.end = loop, end
        if kind == "loop":
            v.loops += 1
        elif kind == "stop":
            v.end_list, v.how = n, GAME
        elif kind == "end":
            v.end_list = n
            v.why = [why for why, hit in ((AT_STREAM, v.on_stream), (MOVED, v.moved and not v.listed)) if hit]
            v.how = EARLY if v.why else MIXER
    if not seen:
        raise ValueError("no [axv] lines; was GCN_AXVOICES=1 set?")
    others = sum(v.how == MIXER and not v.listed for v in voices)
    return [v for v in voices if v.listed or v.how == EARLY], last, others


def seconds(n: int) -> str:
    return f"{n * LIST_MS / 1000:.3f} s"


def row(v: Voice) -> str:
    peak = "none" if v.peak is None else v.peak
    if v.how == RUNNING:
        how = "still running at the end of the log"
    elif v.how == EARLY:
        how = f"{EARLY} at list {v.end_list} ({seconds(v.end_list)}) because {' and '.join(v.why)}"
    else:
        how = f"{v.how} at list {v.end_list}"
    return f"pb {v.pb}  list {v.start}  at {v.at}  loops {v.loops}  peak {peak}  {how}"


def report(path: Path, voices: list[Voice], last: int, others: int) -> str:
    lines = [f"{path}: {last} lists, {seconds(last)}"]
    if voices:
        counts = [sum(v.how == how for v in voices) for how in (RUNNING, GAME, MIXER, EARLY)]
        plural = "" if len(voices) == 1 else "s"
        lines.append(f"{len(voices)} voice{plural} listed: {counts[0]} still running, "
                     f"{counts[1]} stopped by the game, {counts[2]} ended by the mixer, {counts[3]} {EARLY}")
    else:
        lines.append(f"no voice with stream=1 or looping=1, and none {EARLY}")
    if others:
        plural = "" if others == 1 else "s"
        lines.append(f"{others} other voice{plural} ended by the mixer without stream=1 or looping=1")
    lines += [row(v) for v in voices if v.how != EARLY] + [row(v) for v in voices if v.how == EARLY]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stdout", type=Path)
    args = ap.parse_args(argv)
    try:
        voices, last, others = parse(args.stdout.read_text(errors="replace"))
    except OSError as e:
        print(e, file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"{args.stdout}: {e}", file=sys.stderr)
        return 2
    print(report(args.stdout, voices, last, others))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
