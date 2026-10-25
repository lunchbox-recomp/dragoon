"""Which stage made each click the sound device got?

A click in a session's out.wav, the device stage, is put down to the first of these that
explains it:

  mixer        aid.raw, the DMA's blocks before the ring, clicks within MIXER_MS of the
               moment of the stream that output frame was made from
  ring         the ring cut, or a stretch of pulls it couldn't fill began or ended, within
               NEAR_MS of it
  device       a device callback came late within NEAR_MS of it
  unexplained  none of these

The moment of the stream comes from the [audio] position lines in the session's log
(session_log.py): the last one at or before the output frame, moved on at the DMA's rate
over the device's. The ring writes one at least every 0.25 s and at every cut and refill, so
its trim of half a percent at most leaves it within 1.3 ms. An output frame in a pull the
ring couldn't fill was made from nothing, so a click there is never the mixer's. DVD music
is mixed in after the ring, so a click in it is unexplained. It has no command line.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass

from session_log import SessionLog

STAGES = ("mixer", "ring", "device", "unexplained")
MIXER_MS = 2  # how near the matching moment of aid.raw a mixer click must be
NEAR_MS = 5   # how near a ring or device event a click must be


@dataclass
class Placed:
    at: float  # seconds into out.wav
    stage: str
    why: str


def silent_spans(underruns: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """(first, end) output frames of each unbroken stretch of pulls the ring couldn't fill."""
    spans: list[tuple[int, int]] = []
    for at, frames in sorted(underruns):
        if spans and at <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], at + frames))
        else:
            spans.append((at, at + frames))
    return spans


def dma_frame(out_frame: int, positions: list[tuple[int, int]], spans: list[tuple[int, int]],
              ratio: float) -> float | None:
    """The frame of the DMA's stream an output frame was made from, or None when it was made
    from nothing: before the ring first played, or in a pull it couldn't fill."""
    k = bisect_right(positions, (out_frame, float("inf"))) - 1
    if k < 0:
        return None
    s = bisect_right(spans, (out_frame, float("inf"))) - 1
    if s >= 0 and spans[s][0] <= out_frame < spans[s][1]:
        return None
    first, dma = positions[k]
    return dma + (out_frame - first) * ratio


def nearest(points: list[int], x: float, within: float) -> int | None:
    """The sorted point nearest x, if it's within `within` of it."""
    k = bisect_left(points, x)
    best = min(points[max(0, k - 1):k + 1], key=lambda p: abs(p - x), default=None)
    return best if best is not None and abs(best - x) <= within else None


def place(device_clicks: list[float], mixer_clicks: list[float], log: SessionLog, out_rate: int,
          dma_rate: int) -> list[Placed]:
    """Each device click (seconds into out.wav) put down to a stage, given the mixer's clicks
    (seconds into aid.raw) and the log."""
    positions = sorted(log.positions)
    spans = silent_spans(log.underruns)
    mixer = sorted(round(t * dma_rate) for t in mixer_clicks)
    cuts = {at: n for at, n in log.cuts}
    edges = sorted({*cuts, *(s for s, _ in spans), *(e for _, e in spans)})
    late = dict(log.late)
    late_frames = sorted(late)
    near = NEAR_MS * out_rate / 1000

    def secs(frame: float, rate: int) -> str:
        return f"{frame / rate:.3f} s"

    placed = []
    for t in device_clicks:
        c = round(t * out_rate)
        d = dma_frame(c, positions, spans, dma_rate / out_rate)
        if d is not None and (m := nearest(mixer, d, MIXER_MS * dma_rate / 1000)) is not None:
            placed.append(Placed(t, "mixer", f"aid.raw clicks at {secs(m, dma_rate)}"))
        elif (r := nearest(edges, c, near)) is not None:
            what = f"the ring cut {cuts[r]} frames" if r in cuts else "a pull the ring couldn't fill began or ended"
            placed.append(Placed(t, "ring", f"{what} at {secs(r, out_rate)}"))
        elif (f := nearest(late_frames, c, near)) is not None:
            placed.append(Placed(t, "device", f"a callback came {late[f]:.1f} ms after the last at "
                                              f"{secs(f, out_rate)}"))
        elif d is not None:
            placed.append(Placed(t, "unexplained", f"aid.raw has no click near {secs(d, dma_rate)}"))
        else:
            placed.append(Placed(t, "unexplained", "the ring had no sound there"))
    return placed


def counts(placed: list[Placed]) -> dict[str, int]:
    return {stage: sum(p.stage == stage for p in placed) for stage in STAGES}
