"""What a route's two scorecard runs say, scored with audio_clicks.py's functions.

The mixer stage is the unpaced run's DMA blocks before the audio ring (GCN_AIDWAV, raw 32 kHz
stereo), cut to the route's seconds, with the clicks within 2 samples of a 160-sample block
join counted. Its log gives the highest main L peak before the output clamp and the samples
the clamp changed, from the [ax] lines whose list count is within the cut. The device stage is
the real-time run's GCN_WAV, what went to the device, with the clicks within 2 samples of a
ring cut counted when the build logs its cuts. Its log gives the ring's cuts and underruns. A
value the build doesn't record or print is None.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from audio_clicks import Recording, Report, analyse, read_raw, read_wav
from scorecard_runs import Runs

MIXER_RATE = 32000
BLOCK = 160  # samples in one of the DMA's 5 ms blocks, and in one AX command list's output

RING_FILL = re.compile(r"^\[ring\] fill=\d+ avg=\S+ trim=\S+ underruns=(\d+)(?: cuts=(\d+))?$", re.M)
RING_CUT = re.compile(r"^\[ring\] cut \d+ frames at output frame (\d+)$", re.M)
AX_PEAK = re.compile(r"^\[ax\] frames=(\d+) voices\(running, last frame\)=\d+ peak=(\d+) out=[0-9A-F]+$", re.M)
AX_CLAMP = re.compile(r"^\[ax\] bus list=(\d+) .* clipped=(\d+)$", re.M)


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


def peak(log: str, lists: int) -> int | None:
    """The highest peak the [ax] frames lines give up to LISTS command lists."""
    found = [int(p) for n, p in AX_PEAK.findall(log) if int(n) <= lists]
    return max(found) if found else None


def clamped(log: str, lists: int) -> int | None:
    """The clamp counts of the [ax] bus lines up to LISTS command lists, summed."""
    found = [int(c) for n, c in AX_CLAMP.findall(log) if int(n) <= lists]
    return sum(found) if found else None


def cut(rec: Recording, seconds: float, path: Path) -> Recording:
    """The first SECONDS of the recording, refused if it's shorter."""
    frames = round(seconds * rec.rate)
    if rec.frames < frames:
        raise ValueError(f"{path}: {rec.frames / rec.rate:.2f} s recorded, short of the {seconds:g} s "
                         f"the mixer stage scores")
    return Recording(rec.rate, [ch[:frames] for ch in rec.channels])


def measure(runs: Runs, mixer_seconds: float) -> Score:
    """The device stage and the ring from the real-time run, the mixer stage from the first
    MIXER_SECONDS of the unpaced run's blocks."""
    text = runs.paced.log.read_text(errors="replace")
    rg = ring(text)
    device = runs.paced.device
    device_stage = stage(analyse(read_wav(device), 0, marks=rg.cut_frames)) if device.exists() else None
    mixer_stage = mixer_peak = mixer_clamped = None
    if runs.unpaced is not None:
        mixer, lists = runs.unpaced.mixer, round(mixer_seconds * MIXER_RATE) // BLOCK
        unpaced_text = runs.unpaced.log.read_text(errors="replace")
        mixer_peak, mixer_clamped = peak(unpaced_text, lists), clamped(unpaced_text, lists)
        if mixer.exists():
            rec = cut(read_raw(mixer, MIXER_RATE), mixer_seconds, mixer)
            mixer_stage = stage(analyse(rec, 0, period=BLOCK))
    return Score(mixer_stage, device_stage, None if rg.cut_frames is None else len(rg.cut_frames),
                 rg.underruns, mixer_peak, mixer_clamped)


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
