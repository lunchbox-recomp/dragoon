#!/usr/bin/env python3
"""Where does a recording of the game's output click, drop out or clip?

Usage: audio_clicks.py FILE [--raw RATE] [--from S] [--list N] [--period N] [--marks F] [--json]

FILE is a 16-bit PCM WAV, such as the one GCN_WAV=<path> makes of exactly what went to the
audio device. With --raw RATE it is raw 16-bit little-endian stereo at RATE Hz instead, such
as the one GCN_AIDWAV=<path> makes of every block the DSP handed the DMA, before the sound
ring. Prints its length, then three counts, each with the times it was found at:

  clicks   a sample that breaks from the waveform around it: its second difference is over
           8 times the RMS second difference of the 5 ms either side, and at least 128. A
           splice, such as a skip in the audio ring, shows as one. Detections less than 1 ms
           apart, on any channel, are one click, and they chain: a run of detections each
           under 1 ms from the last is one click, however long the run. A click is reported at
           the run's first sample, so --marks and --period match that sample. Each is given
           with its size, the largest second difference among them in dB from full scale
           (32,768).
  gaps     5 ms or more of digital silence on every channel, starting straight after sound
           (over 300 RMS on some channel in the 5 ms before). A dropout shows as one, and
           usually clicks at either edge too. A sound that fades out first doesn't.
  clipped  a run of two or more samples at full scale on one channel.

--from S skips the first S seconds; times are still from the start of the recording.
--list N prints the times of the first N of each (default 20). --period N counts the
clicks within 2 samples of a multiple of N samples from the start, beside the count chance
would put there: a recording made of N-sample blocks that clicks at their joins has far
more there than chance, and a sound's own sharp edges don't. --marks F does the same for
the sample indices in the text file F, one a line (# starts a comment), such as where the
audio ring cut, and counts the marks with a click near them too. --json prints the whole
result as JSON.

Exits 0 once it has read the recording, 2 on a bad argument (--raw below 1 included) or a
file that isn't 16-bit PCM WAV (without --raw).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import wave
from array import array
from bisect import bisect_left
from dataclasses import asdict, dataclass
from itertools import accumulate
from pathlib import Path

CLICK_RATIO = 8      # how many times the local RMS second difference a click must be
CLICK_FLOOR = 128    # the smallest second difference that can be a click
CONTEXT_MS = 5       # the stretch either side a sample is judged against
MERGE_MS = 1         # detections closer than this are one click
GAP_MS = 5           # the shortest silence that's a gap, and the stretch before it
GAP_LEVEL = 300      # the RMS the stretch before a silence must be over
JOIN_SLACK = 2       # how near a join or a mark a click must be to count as on it
FULL_SCALE = (-32768, 32767)
PART_S = 30          # how much of a recording analyse_long works on at once


@dataclass
class Recording:
    rate: int
    channels: list[array]

    @property
    def frames(self) -> int:
        return len(self.channels[0])


@dataclass
class Click:
    at: float
    db: float


@dataclass
class Gap:
    at: float
    ms: float


@dataclass
class Clip:
    at: float
    samples: int


@dataclass
class Joins:
    period: int
    on_joins: int
    by_chance: float


@dataclass
class Marks:
    marks: int
    clicks_on_marks: int
    marks_with_clicks: int
    by_chance: float


@dataclass
class Report:
    seconds: float
    rate: int
    channels: int
    start: float
    clicks: list[Click]
    gaps: list[Gap]
    clipped: list[Clip]
    joins: Joins | None = None
    marks: Marks | None = None


def read_wav(path: Path) -> Recording:
    try:
        with wave.open(str(path), "rb") as w:
            if w.getsampwidth() != 2:
                raise ValueError(f"{path}: {8 * w.getsampwidth()}-bit samples; only 16-bit PCM is read")
            n, rate = w.getnchannels(), w.getframerate()
            raw = w.readframes(w.getnframes())
    except (wave.Error, EOFError) as e:
        raise ValueError(f"{path}: not a PCM WAV file ({e})") from None
    return split(path, raw, n, rate)


def read_raw(path: Path, rate: int) -> Recording:
    return split(path, path.read_bytes(), 2, rate)


def split(path: Path, raw: bytes, n: int, rate: int) -> Recording:
    """Little-endian 16-bit frames of n channels, as one array per channel."""
    data = array("h")
    data.frombytes(raw[:len(raw) - len(raw) % (2 * n)])  # a recording cut off mid-frame
    if sys.byteorder == "big":
        data.byteswap()
    if not data:
        raise ValueError(f"{path}: no samples")
    return Recording(rate, [data[c::n] for c in range(n)])


def read_marks(path: Path) -> list[int]:
    """Sample indices, one a line. Blank lines and what follows a # are skipped."""
    marks = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        text = line.split("#")[0].strip()
        if text and not (text.isascii() and text.isdigit()):
            raise ValueError(f"{path}:{n}: {text!r} isn't a sample index")
        if text:
            marks.append(int(text))
    return marks


def click_samples(x: array, rate: int) -> list[tuple[int, int]]:
    """(index, size of the second difference) of the samples whose second difference stands
    out from the CONTEXT_MS either side, leaving out the two samples next to it, which a click
    disturbs too."""
    d = [c - 2 * b + a for a, b, c in zip(x, x[1:], x[2:])]  # d[i] is centred on x[i + 1]
    sums = [0, *accumulate(v * v for v in d)]
    w = rate * CONTEXT_MS // 1000
    found = []
    for i, v in enumerate(d):
        if -CLICK_FLOOR < v < CLICK_FLOOR:
            continue
        lo, hi = max(0, i - w), min(len(d), i + w + 1)
        near_lo, near_hi = max(lo, i - 2), min(hi, i + 3)
        count = (hi - lo) - (near_hi - near_lo)
        energy = sums[hi] - sums[lo] - (sums[near_hi] - sums[near_lo])
        if count and v * v * count > CLICK_RATIO * CLICK_RATIO * energy:
            found.append((i + 1, abs(v)))
    return found


def merge(found: list[tuple[int, int]], within: int) -> list[tuple[int, int]]:
    """(first index, largest size) of each run whose neighbours are under `within` apart."""
    runs: list[tuple[int, int]] = []
    last = None
    for i, size in sorted(found):
        if last is None or i - last >= within:
            runs.append((i, size))
        else:
            runs[-1] = (runs[-1][0], max(runs[-1][1], size))
        last = i
    return runs


def gap_runs(rec: Recording) -> list[tuple[int, int]]:
    """(start, length) of each silence on every channel that's long enough and comes
    straight after sound."""
    need = rec.rate * GAP_MS // 1000
    silent = [not any(f) for f in zip(*rec.channels)]
    runs, i = [], 0
    while i < len(silent):
        if not silent[i]:
            i += 1
            continue
        start = i
        while i < len(silent) and silent[i]:
            i += 1
        if i - start >= need and start >= need and loud_before(rec, start, need):
            runs.append((start, i - start))
    return runs


def loud_before(rec: Recording, start: int, length: int) -> bool:
    return any(sum(v * v for v in ch[start - length:start]) > GAP_LEVEL * GAP_LEVEL * length
               for ch in rec.channels)


def clip_runs(x: array) -> list[tuple[int, int]]:
    """(start, length) of each run of two or more full-scale samples."""
    runs, i = [], 0
    while i < len(x):
        if x[i] not in FULL_SCALE:
            i += 1
            continue
        start = i
        while i < len(x) and x[i] == x[start]:
            i += 1
        if i - start >= 2:
            runs.append((start, i - start))
    return runs


def on_joins(indices: list[int], period: int) -> Joins:
    near = sum(min(i % period, period - i % period) <= JOIN_SLACK for i in indices)
    return Joins(period, near, len(indices) * min(1, (2 * JOIN_SLACK + 1) / period))


def near(i: int, points: list[int]) -> bool:
    """Whether i is within JOIN_SLACK of one of the sorted points."""
    k = bisect_left(points, i - JOIN_SLACK)
    return k < len(points) and points[k] <= i + JOIN_SLACK


def on_marks(indices: list[int], marks: list[int], frames: int) -> Marks:
    clicks, marks = sorted(indices), sorted(marks)
    return Marks(len(marks), sum(near(i, marks) for i in clicks), sum(near(m, clicks) for m in marks),
                 len(clicks) * min(1, len(marks) * (2 * JOIN_SLACK + 1) / frames))


def analyse(rec: Recording, start_s: float, period: int = 0, marks: list[int] | None = None) -> Report:
    skip = round(start_s * rec.rate)
    if skip >= rec.frames:
        raise ValueError(f"--from {start_s:g} is past the end, {rec.frames / rec.rate:.2f} s")
    part = Recording(rec.rate, [ch[skip:] for ch in rec.channels])

    def at(i: int) -> float:
        return (skip + i) / rec.rate

    found = merge([f for ch in part.channels for f in click_samples(ch, rec.rate)],
                  rec.rate * MERGE_MS // 1000)
    clicks = [i for i, _ in found]
    clips = sorted(r for ch in part.channels for r in clip_runs(ch))
    return Report(seconds=rec.frames / rec.rate, rate=rec.rate, channels=len(rec.channels),
                  start=skip / rec.rate,
                  clicks=[Click(at(i), 20 * math.log10(size / -FULL_SCALE[0])) for i, size in found],
                  gaps=[Gap(at(s), n * 1000 / rec.rate) for s, n in gap_runs(part)],
                  clipped=[Clip(at(s), n) for s, n in clips],
                  joins=on_joins([skip + i for i in clicks], period) if period else None,
                  marks=None if marks is None else on_marks(
                      [skip + i for i in clicks], [m for m in marks if skip <= m < rec.frames], part.frames))


def analyse_long(rec: Recording, part_s: float = PART_S) -> Report:
    """What analyse(rec, 0) finds, worked out part_s seconds at a time. One pass holds every
    sample's second difference as a Python int, about 5 MB a second of stereo, so an hour's
    session would need gigabytes. Each part is read with enough of its neighbours that every
    sample in it is judged on the same context as in one pass, and a gap or a clipped run that
    starts in a part and goes on past it is followed to its end."""
    n, rate, chans = rec.frames, rec.rate, rec.channels
    part = max(1, round(part_s * rate))
    margin = rate * CONTEXT_MS // 1000 + 3  # a click's context, its two neighbours and the sample itself
    need = rate * GAP_MS // 1000
    found: list[tuple[int, int]] = []
    gaps: list[tuple[int, int]] = []
    clips: list[tuple[int, int]] = []
    for a in range(0, n, part):
        b = min(n, a + part)
        lo, hi = max(0, a - margin), min(n, b + margin)
        for ch in chans:
            found += [(lo + i, size) for i, size in click_samples(ch[lo:hi], rate) if a <= lo + i < b]
        # A gap's run must start in the part, with the stretch before it in hand.
        lo, hi = max(0, a - need - 1), min(n, b + need)
        for s, length in gap_runs(Recording(rate, [ch[lo:hi] for ch in chans])):
            if a <= lo + s < b:
                end = lo + s + length
                if end == hi:  # it runs to the end of what was read, so follow it
                    while end < n and not any(ch[end] for ch in chans):
                        end += 1
                gaps.append((lo + s, end - lo - s))
        for ch in chans:
            for s, length in clip_runs(ch[a:min(n, b + 1)]):
                start = a + s
                if start >= b or (s == 0 and a > 0 and ch[a - 1] == ch[a]):
                    continue  # the next part's, or one that started in the last
                end = start + length
                while end < n and ch[end] == ch[start]:
                    end += 1
                clips.append((start, end - start))
    merged = merge(found, rate * MERGE_MS // 1000)
    return Report(seconds=n / rate, rate=rate, channels=len(chans), start=0.0,
                  clicks=[Click(i / rate, 20 * math.log10(size / -FULL_SCALE[0])) for i, size in merged],
                  gaps=[Gap(s / rate, length * 1000 / rate) for s, length in gaps],
                  clipped=[Clip(s / rate, length) for s, length in sorted(clips)])


def print_report(path: Path, r: Report, limit: int) -> None:
    print(f"{path}: {r.seconds:.2f} s, {r.rate} Hz, {r.channels} channels, from {r.start:.2f} s")
    minutes = (r.seconds - r.start) / 60
    sections = (
        ("clicks", f"{len(r.clicks)} ({len(r.clicks) / minutes:.1f} a minute)",
         [f"{c.at:.3f} s, {c.db:.1f} dB" for c in r.clicks]),
        ("gaps", f"{len(r.gaps)}", [f"{g.at:.3f} s, {g.ms:.1f} ms" for g in r.gaps]),
        ("clipped", f"{len(r.clipped)} runs, {sum(c.samples for c in r.clipped)} samples",
         [f"{c.at:.3f} s, {c.samples} samples" for c in r.clipped]),
    )
    for name, count, lines in sections:
        print(f"{name:8} {count}")
        for line in lines[:limit]:
            print(f"  {line}")
        if len(lines) > limit:
            print(f"  and {len(lines) - limit} more")
    if r.joins:
        print(f"joins    {r.joins.on_joins} of {len(r.clicks)} clicks within {JOIN_SLACK} samples of a "
              f"multiple of {r.joins.period} ({r.joins.by_chance:.1f} by chance)")
    if r.marks:
        print(f"marks    {r.marks.clicks_on_marks} of {len(r.clicks)} clicks within {JOIN_SLACK} samples of a "
              f"mark ({r.marks.by_chance:.1f} by chance), {r.marks.marks_with_clicks} of {r.marks.marks} "
              f"marks with a click")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", type=Path)
    ap.add_argument("--raw", type=int, default=None, metavar="RATE")
    ap.add_argument("--from", dest="start", type=float, default=0.0)
    ap.add_argument("--list", type=int, default=20)
    ap.add_argument("--period", type=int, default=0)
    ap.add_argument("--marks", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.raw is not None and args.raw < 1:
        ap.error("--raw RATE must be at least 1")
    if args.start < 0 or args.list < 0 or args.period < 0:
        ap.error("--from, --list and --period can't be negative")
    try:
        rec = read_raw(args.file, args.raw) if args.raw is not None else read_wav(args.file)
        marks = read_marks(args.marks) if args.marks else None
        report = analyse(rec, args.start, args.period, marks)
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(asdict(report), indent=1))
    else:
        print_report(args.file, report, args.list)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
