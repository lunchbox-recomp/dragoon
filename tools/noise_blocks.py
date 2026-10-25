#!/usr/bin/env python3
"""Where do the DMA's blocks turn to loud noise?

Usage: noise_blocks.py FILE [--list N] [--json]

FILE is a GCN_AIDWAV recording (aid_blocks.py). It weighs each 160-sample block's
high-frequency energy against its total, as the RMS of its first difference over its RMS, on
each channel. White noise gives about 1.41, and music and effects give far less, since their
energy sits low. A block is noise-like when that's over 1 on some channel whose peak in the
block is over 8,000. Noise-like blocks that start 100 ms apart or less are one stretch. A
bright sound of the game's own, such as a crash, makes a short stretch too. It prints the
noise-like blocks and their seconds, then the first N stretches (20 by default) with where
each starts and ends. --json prints the whole result.

It reads the DMA's 32 kHz only. The ring interpolates to 48 kHz for the device, which leaves
little above 16 kHz, and noise that flags every block at 32 kHz flags far fewer after a
linear interpolation to 48 kHz (test_noise_blocks.py). A GCN_WAV recording isn't a fair input.

Exits 0 once it has read the recording, 2 on a bad argument or a file it can't read.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from array import array
from dataclasses import asdict, dataclass
from pathlib import Path

from aid_blocks import BLOCK, RATE, plural
from audio_clicks import Recording, Source, read_raw

NOISE_RATIO = 1.0   # RMS first difference over RMS above which a block is noise-like
NOISE_PEAK = 8000   # the peak a noise-like block must pass, so quiet hiss doesn't count
JOIN_BLOCKS = 20    # noise-like blocks this close (100 ms) are one stretch
PART_BLOCKS = 2000  # how many blocks find_source reads at once (10 s)


@dataclass
class Stretch:
    start: float
    end: float
    blocks: int


@dataclass
class Noise:
    seconds: float
    blocks: int
    noisy_blocks: int
    noisy_seconds: float
    stretches: list[Stretch]


def noisy(x: array) -> bool:
    """Whether one channel's block is loud and has more energy high than its total."""
    if max(abs(v) for v in x) <= NOISE_PEAK:
        return False
    energy = sum(v * v for v in x)
    rises = sum((b - a) ** 2 for a, b in zip(x, x[1:]))
    return math.sqrt(rises / (len(x) - 1)) > NOISE_RATIO * math.sqrt(energy / len(x))


def noisy_blocks(rec: Recording) -> list[int]:
    """The indices of the whole blocks that are noise-like on some channel."""
    return [k for k in range(rec.frames // BLOCK)
            if any(noisy(ch[k * BLOCK:(k + 1) * BLOCK]) for ch in rec.channels)]


def stretches(found: list[int]) -> list[Stretch]:
    runs: list[list[int]] = []
    for k in found:
        if runs and k - runs[-1][-1] <= JOIN_BLOCKS:
            runs[-1].append(k)
        else:
            runs.append([k])
    return [Stretch(r[0] * BLOCK / RATE, (r[-1] + 1) * BLOCK / RATE, len(r)) for r in runs]


def summarise(frames: int, found: list[int]) -> Noise:
    return Noise(frames / RATE, frames // BLOCK, len(found), len(found) * BLOCK / RATE, stretches(found))


def find(rec: Recording) -> Noise:
    return summarise(rec.frames, noisy_blocks(rec))


def find_source(src: Source, part_blocks: int = PART_BLOCKS) -> Noise:
    """What find(the recording) finds, read part_blocks blocks at a time, so what it holds is
    about one part and not the recording. A part is whole blocks, so none straddles an edge, and
    the blocks found are numbered from the start of the recording, so a stretch that crosses an
    edge joins as it does in one pass."""
    blocks = src.frames // BLOCK
    found: list[int] = []
    for first in range(0, blocks, part_blocks):
        last = min(blocks, first + part_blocks)
        part = Recording(src.rate, src.read(first * BLOCK, last * BLOCK))
        found += [first + k for k in noisy_blocks(part)]
    return summarise(src.frames, found)


def print_noise(path: Path, n: Noise, limit: int) -> None:
    print(f"{path}: {n.seconds:.2f} s, {plural(n.blocks, 'block')}, {n.noisy_blocks} noise-like "
          f"({n.noisy_seconds:.2f} s) in {plural(len(n.stretches), 'stretch', 'stretches')}")
    for s in n.stretches[:limit]:
        print(f"  {s.start:.3f} s to {s.end:.3f} s, {plural(s.blocks, 'block')}")
    if len(n.stretches) > limit:
        print(f"  and {len(n.stretches) - limit} more")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", type=Path)
    ap.add_argument("--list", type=int, default=20)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.list < 0:
        ap.error("--list can't be negative")
    try:
        result = find(read_raw(args.file, RATE))
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(asdict(result), indent=1))
    else:
        print_noise(args.file, result, args.list)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
