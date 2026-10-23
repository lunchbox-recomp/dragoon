#!/usr/bin/env python3
"""Which clicks does one build's unpaced recording of a route have that another's doesn't, and
what differs there?

Usage: click_diff.py A B [--seconds S] [--list N] [--json]

A and B are GCN_AIDWAV recordings (aid_blocks.py) of one route from unpaced runs of two builds.
An unpaced run's game time doesn't follow the host's, so the two line up sample for sample and
differ only where the builds made different sound. Both are cut to the shorter one, or to S
seconds when both are that long. Clicks are found in each with audio_clicks.py's functions, and
a click is shared when the other recording has one within 1 ms. It prints how many each has,
how many only one has and the share of samples that are the same in both, then for each click
only one has (the first N, 20 by default):

  where    its time, the build that has it, its size in dB and its offset in its 160-sample
           block
  B-A      the largest |B - A| within 5 ms either side, and the second difference of B - A at
           the click. When that's 0 both builds have the same edge there, and only the sound
           around it, which the click is judged against, differs.
  silent   whether A, and whether B, is digital silence on every channel within 5 ms either side
  join     whether B - A steps at the nearest block join, its first difference across the join
           over 8 times the RMS first difference within 5 ms either side on some channel

--json prints the whole result. Exits 0 once it has read both recordings, 2 on a bad argument,
a recording it can't read or one shorter than S.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from bisect import bisect_left
from dataclasses import asdict, dataclass
from pathlib import Path

from aid_blocks import BLOCK, RATE
from audio_clicks import CLICK_RATIO, CONTEXT_MS, MERGE_MS, Recording, analyse, read_raw

WINDOW = RATE * CONTEXT_MS // 1000  # 5 ms either side
SHARED = RATE * MERGE_MS // 1000    # how near a click in the other recording makes it shared


@dataclass
class OneSided:
    at: float
    build: str  # "A" or "B"
    db: float
    offset: int
    diff_peak: int      # the largest |B - A| within WINDOW either side
    diff_d2: int        # the largest |second difference of B - A| at the click, over the channels
    a_silent: bool
    b_silent: bool
    join_step: bool


@dataclass
class Diff:
    seconds: float
    a_clicks: int
    b_clicks: int
    only_a: int
    only_b: int
    same_samples: float  # the share of frames where every channel is the same
    other_silent: int    # one-sided clicks where the build without it is silent
    same_edge: int       # one-sided clicks where B - A has no second difference
    join_steps: int      # one-sided clicks where B - A steps at the nearest join
    clicks: list[OneSided]


def cut(a: Recording, b: Recording, seconds: float | None, paths: tuple[Path, Path]) -> tuple[Recording, Recording]:
    frames = min(a.frames, b.frames) if seconds is None else round(seconds * RATE)
    for rec, path in ((a, paths[0]), (b, paths[1])):
        if rec.frames < frames:
            raise ValueError(f"{path}: {rec.frames / RATE:.2f} s recorded, short of {seconds:g} s")
    return tuple(Recording(RATE, [ch[:frames] for ch in r.channels]) for r in (a, b))


def unmatched(mine: list[int], theirs: list[int]) -> list[int]:
    """The indices in MINE with none in the sorted THEIRS within SHARED."""
    out = []
    for i in mine:
        k = bisect_left(theirs, i - SHARED)
        if not (k < len(theirs) and theirs[k] <= i + SHARED):
            out.append(i)
    return out


def silent(rec: Recording, lo: int, hi: int) -> bool:
    return not any(any(ch[lo:hi]) for ch in rec.channels)


def steps_at(d: list[int], j: int) -> bool:
    """Whether D's first difference across J stands out from the WINDOW either side. An RMS
    under 1 counts as 1, so a step out of digital silence counts."""
    if not 0 < j < len(d):
        return False
    step = abs(d[j] - d[j - 1])
    around = [d[k] - d[k - 1] for k in range(max(1, j - WINDOW), min(len(d), j + WINDOW)) if k != j]
    rms = math.sqrt(sum(v * v for v in around) / len(around)) if around else 0.0
    return step > CLICK_RATIO * max(1.0, rms)


def describe(i: int, build: str, db: float, a: Recording, b: Recording, diffs: list[list[int]]) -> OneSided:
    """The click at I that only BUILD has, given B - A on each channel."""
    n = a.frames
    lo, hi = max(0, i - WINDOW), min(n, i + WINDOW + 1)
    peak = max(abs(v) for d in diffs for v in d[lo:hi])
    d2 = max(abs(d[i + 1] - 2 * d[i] + d[i - 1]) for d in diffs) if 0 < i < n - 1 else 0
    join = round(i / BLOCK) * BLOCK
    return OneSided(i / RATE, build, db, i % BLOCK, peak, d2, silent(a, lo, hi), silent(b, lo, hi),
                    any(steps_at(d, join) for d in diffs))


def diff(a_path: Path, b_path: Path, seconds: float | None = None) -> Diff:
    a, b = cut(read_raw(a_path, RATE), read_raw(b_path, RATE), seconds, (a_path, b_path))
    found = {}
    for name, rec in (("A", a), ("B", b)):
        found[name] = {round(c.at * RATE): c.db for c in analyse(rec, 0).clicks}
    at_a, at_b = sorted(found["A"]), sorted(found["B"])
    only = sorted([(i, "A") for i in unmatched(at_a, at_b)] + [(i, "B") for i in unmatched(at_b, at_a)])
    diffs = [[y - x for x, y in zip(ca, cb)] for ca, cb in zip(a.channels, b.channels)]
    clicks = [describe(i, build, found[build][i], a, b, diffs) for i, build in only]
    same = sum(not any(frame) for frame in zip(*diffs))
    return Diff(a.frames / RATE, len(at_a), len(at_b), sum(c.build == "A" for c in clicks),
                sum(c.build == "B" for c in clicks), same / a.frames if a.frames else 0.0,
                sum(c.b_silent if c.build == "A" else c.a_silent for c in clicks),
                sum(c.diff_d2 == 0 for c in clicks), sum(c.join_step for c in clicks), clicks)


def print_diff(d: Diff, limit: int) -> None:
    print(f"{d.seconds:.2f} s compared, {d.same_samples:.1%} of samples the same")
    print(f"clicks   A {d.a_clicks}, B {d.b_clicks}, only A {d.only_a}, only B {d.only_b}")
    print(f"of those one-sided, the other build silent {d.other_silent}, the same edge in both "
          f"{d.same_edge}, B-A stepping at a join {d.join_steps}")
    for c in d.clicks[:limit]:
        print(f"  {c.at:.3f} s only {c.build}, {c.db:.1f} dB, {c.offset} samples into its block, "
              f"B-A peak {c.diff_peak} and second difference {c.diff_d2}, "
              f"A {'silent' if c.a_silent else 'sounding'}, B {'silent' if c.b_silent else 'sounding'}"
              f"{', B-A steps at a join' if c.join_step else ''}")
    if len(d.clicks) > limit:
        print(f"  and {len(d.clicks) - limit} more")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--list", type=int, default=20)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.list < 0 or (args.seconds is not None and args.seconds <= 0):
        ap.error("--list can't be negative and --seconds must be over 0")
    try:
        result = diff(args.a, args.b, args.seconds)
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(asdict(result), indent=1))
    else:
        print_diff(result, args.list)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
