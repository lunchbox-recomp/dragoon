"""What one scorecard run's recordings and log say, scored with audio_clicks.py's functions.

The mixer stage is the DMA's blocks before the audio ring (GCN_AIDWAV, raw 32 kHz stereo),
with the clicks within 2 samples of a 160-sample block join counted. The device stage is what
went to the device (GCN_WAV), with the clicks within 2 samples of a ring cut counted when the
build logs its cuts. The log gives the ring's cuts and underruns, the highest main L peak
before the output clamp and the samples the clamp changed, when the build prints them. A
value the build doesn't record or print is None.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from audio_clicks import Report, analyse, read_raw, read_wav

MIXER_RATE = 32000
BLOCK = 160  # samples in one of the DMA's 5 ms blocks

RING_FILL = re.compile(r"^\[ring\] fill=\d+ avg=\S+ trim=\S+ underruns=(\d+)(?: cuts=(\d+))?$", re.M)
RING_CUT = re.compile(r"^\[ring\] cut \d+ frames at output frame (\d+)$", re.M)
AX_PEAK = re.compile(r"^\[ax\] frames=\d+ voices\(running, last frame\)=\d+ peak=(\d+) out=[0-9A-F]+$", re.M)
AX_CLAMP = re.compile(r"^\[ax\] bus list=\d+ .* clipped=(\d+)$", re.M)


@dataclass
class Stage:
    seconds: float
    clicks: int
    per_minute: float
    gaps: int
    clipped_runs: int
    clipped_samples: int
    on_joins: int | None = None     # mixer: clicks on a 160-sample block join
    joins_by_chance: float | None = None
    on_cuts: int | None = None      # device: clicks on a ring cut
    cuts_by_chance: float | None = None


@dataclass
class Score:
    mixer: Stage | None
    device: Stage | None
    cuts: int | None
    underruns: int | None
    peak: int | None
    clamped: int | None


@dataclass
class Ring:
    underruns: int | None
    cut_frames: list[int] | None  # output frames in the GCN_WAV recording; None if not logged


def per_minute(clicks: int, seconds: float) -> float:
    return clicks * 60 / seconds if seconds else 0.0


def stage(r: Report) -> Stage:
    seconds = r.seconds - r.start
    s = Stage(seconds, len(r.clicks), per_minute(len(r.clicks), seconds), len(r.gaps), len(r.clipped),
              sum(c.samples for c in r.clipped))
    if r.joins:
        s.on_joins, s.joins_by_chance = r.joins.on_joins, r.joins.by_chance
    if r.marks:
        s.on_cuts, s.cuts_by_chance = r.marks.clicks_on_marks, r.marks.by_chance
    return s


def ring(log: str) -> Ring:
    """Underruns as of the last "[ring] fill" line. Cuts are logged one line each, and only a
    build whose fill lines carry cuts= logs them."""
    fills = RING_FILL.findall(log)
    cuts = [int(f) for f in RING_CUT.findall(log)]
    logs_cuts = bool(cuts) or any(c for _, c in fills)
    return Ring(int(fills[-1][0]) if fills else None, cuts if logs_cuts else None)


def peak(log: str) -> int | None:
    found = [int(p) for p in AX_PEAK.findall(log)]
    return max(found) if found else None


def clamped(log: str) -> int | None:
    found = [int(c) for c in AX_CLAMP.findall(log)]
    return sum(found) if found else None


def measure(log: Path, mixer: Path, device: Path) -> Score:
    text = log.read_text(errors="replace")
    rg = ring(text)
    mixer_stage = stage(analyse(read_raw(mixer, MIXER_RATE), 0, period=BLOCK)) if mixer.exists() else None
    device_stage = stage(analyse(read_wav(device), 0, marks=rg.cut_frames)) if device.exists() else None
    return Score(mixer_stage, device_stage, None if rg.cut_frames is None else len(rg.cut_frames),
                 rg.underruns, peak(text), clamped(text))


def _sum(values: list) -> int | float | None:
    return None if any(v is None for v in values) else sum(values)


def total_stage(stages: list[Stage | None]) -> Stage | None:
    if not stages or any(s is None for s in stages):
        return None
    seconds, clicks = sum(s.seconds for s in stages), sum(s.clicks for s in stages)
    return Stage(seconds, clicks, per_minute(clicks, seconds), sum(s.gaps for s in stages),
                 sum(s.clipped_runs for s in stages), sum(s.clipped_samples for s in stages),
                 _sum([s.on_joins for s in stages]), _sum([s.joins_by_chance for s in stages]),
                 _sum([s.on_cuts for s in stages]), _sum([s.cuts_by_chance for s in stages]))


def total(scores: list[Score]) -> Score:
    """Every route together: counts and seconds summed, clicks a minute over the summed
    seconds, the highest peak. A value any route lacks is None."""
    peaks = [s.peak for s in scores]
    return Score(total_stage([s.mixer for s in scores]), total_stage([s.device for s in scores]),
                 _sum([s.cuts for s in scores]), _sum([s.underruns for s in scores]),
                 None if not peaks or None in peaks else max(peaks), _sum([s.clamped for s in scores]))
