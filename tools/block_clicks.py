#!/usr/bin/env python3
"""Do a run's mixer-stage clicks sit on the blocks the DMA played twice or delivered catching
up, more than chance would put there?

Usage: block_clicks.py FILE [--list N] [--json]

FILE is a GCN_AIDWAV recording and FILE.txt its block log (aid_blocks.py). Clicks are found with
audio_clicks.py's functions. Two kinds of block are marked.

  replayed   its address is the block before's. The guest hadn't queued the next buffer, so
             the DMA played the same one again.
  caught up  delivered while the clock caught up with the host

A click is on a marked block when its first sample is in the block or within 2 samples of
either end. For each kind, and for the two together, it prints the marked blocks, the clicks on
them and the count chance would put there, which is the clicks times the share of the recording
those blocks and their 2 samples either side cover. A --real-time run's clock catches up where
the host falls behind, and an unpaced run's never does. --list N prints the first N clicks on a
marked block (default 20), each with its offset in its block and the kinds it's on. --json
prints the whole result.

Exits 0 once it has read both files, 2 on a bad argument or a file it can't read.
"""
from __future__ import annotations

import argparse
import json
import sys
from bisect import bisect_right
from dataclasses import asdict, dataclass
from pathlib import Path

from aid_blocks import RATE, Block, log_path, plural, read_blocks
from audio_clicks import JOIN_SLACK, analyse, read_raw

KINDS = ("replayed", "caught up")


@dataclass
class OnBlocks:
    kind: str
    blocks: int
    clicks_on: int
    by_chance: float


@dataclass
class Placed:
    at: float
    db: float
    offset: int        # samples from the start of the block it falls in
    kinds: list[str]


@dataclass
class Result:
    seconds: float
    blocks: int
    clicks: int
    counts: list[OnBlocks]  # each kind, then the two together
    placed: list[Placed]


def marked(blocks: list[Block]) -> dict[str, list[Block]]:
    """Each kind's blocks, and the blocks of either kind, in the log's order."""
    replayed = {k for k in range(1, len(blocks)) if blocks[k].address == blocks[k - 1].address}
    caught_up = {k for k, b in enumerate(blocks) if b.caught_up}
    return {kind: [blocks[k] for k in sorted(found)]
            for kind, found in (("replayed", replayed), ("caught up", caught_up), ("either", replayed | caught_up))}


def spans(blocks: list[Block], frames: int) -> list[tuple[int, int]]:
    """The samples each block and its JOIN_SLACK either side cover, [first, end), merged where
    they meet and kept within the recording. The blocks come in the recording's order."""
    merged: list[tuple[int, int]] = []
    for b in blocks:
        lo, hi = max(0, b.start - JOIN_SLACK), min(frames, b.start + b.length + JOIN_SLACK + 1)
        if lo >= hi:
            continue
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def inside(i: int, covered: list[tuple[int, int]]) -> bool:
    k = bisect_right(covered, (i, float("inf"))) - 1
    return k >= 0 and covered[k][0] <= i < covered[k][1]


def place(path: Path) -> Result:
    rec = read_raw(path, RATE)
    blocks = read_blocks(log_path(path))
    if not blocks:
        raise ValueError(f"{log_path(path)}: no blocks")
    report = analyse(rec, 0)
    clicks = [round(c.at * RATE) for c in report.clicks]
    kinds = marked(blocks)
    covered = {kind: spans(found, rec.frames) for kind, found in kinds.items()}
    counts = [OnBlocks(kind, len(found), sum(inside(i, covered[kind]) for i in clicks),
                       len(clicks) * sum(hi - lo for lo, hi in covered[kind]) / rec.frames)
              for kind, found in kinds.items()]
    starts = [b.start for b in blocks]
    placed = []
    for c, i in zip(report.clicks, clicks):
        on = [kind for kind in KINDS if inside(i, covered[kind])]
        if on:
            k = max(0, bisect_right(starts, i) - 1)  # the block it falls in, or the first
            placed.append(Placed(c.at, c.db, i - starts[k], on))
    return Result(rec.frames / RATE, len(blocks), len(clicks), counts, placed)


def print_result(path: Path, r: Result, limit: int) -> None:
    print(f"{path}: {r.seconds:.2f} s, {plural(r.blocks, 'block')}, {plural(r.clicks, 'click')}")
    for c in r.counts:
        print(f"{c.kind:10} {plural(c.blocks, 'block')}, {plural(c.clicks_on, 'click')} on them "
              f"({c.by_chance:.1f} by chance)")
    for p in r.placed[:limit]:
        print(f"  {p.at:.3f} s, {p.db:.1f} dB, {plural(p.offset, 'sample')} into its block, {' and '.join(p.kinds)}")
    if len(r.placed) > limit:
        print(f"  and {len(r.placed) - limit} more")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", type=Path)
    ap.add_argument("--list", type=int, default=20)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.list < 0:
        ap.error("--list can't be negative")
    try:
        result = place(args.file)
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(asdict(result), indent=1))
    else:
        print_result(args.file, result, args.list)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
