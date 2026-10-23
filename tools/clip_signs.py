#!/usr/bin/env python3
"""Which side of full scale do a build's clipped runs sit on?

Usage: clip_signs.py LABEL=BUILD_DIR [LABEL=BUILD_DIR ...] [--routes R,R] [--margin S]

audio_clicks.py counts a clipped run at +32,767 or at -32,768 as one number. A build whose
clamp stops at -32,767 holds its negative clipping at a value that number doesn't count, so
two builds' counts only compare once they're split by sign. This reads the two recordings
audio_scorecard.py scores, from the runs already in each BUILD_DIR/probe/, and plays no game.
The mixer is the unpaced run's mixer.raw cut to the route's last checkpoint plus --margin
seconds (15 by default), as the scorecard cuts it. The device is the real-time run's
device.wav in full. For each it prints its seconds, then:

  runs at +32767   clipped runs on the positive side, with their samples
  runs at -32768   clipped runs on the negative side, with their samples
  samples at -32767  samples one short of the negative limit, which no clipped run counts
  lowest, highest  the lowest and highest sample on any channel

The device also gets the highest main L peak the real-time run's log gives, from its
[ax] frames lines, which shows whether a run reached a loud stretch. A recording that isn't
there reads "not recorded", and a log value the build doesn't print reads "not logged".

Exits 0 once every route is read. It only reports, so it never exits 1. Exits 2 on a bad
argument, a run that didn't reach its last checkpoint, a recording it can't read or an
unpaced recording shorter than the cut.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from audio_clicks import Recording, clip_runs, read_wav
from audio_scorecard import NOT_LOGGED, NOT_RECORDED, parse_builds
from routes import MANIFEST, select_routes
from scorecard_measure import cut, peak
from scorecard_runs import MARGIN_S, Runs, last_runs, seconds

ONE_SHORT = -32767  # one short of the negative limit audio_clicks.py counts


@dataclass
class Signs:
    seconds: float
    high_runs: int
    high_samples: int
    low_runs: int
    low_samples: int
    at_minus_32767: int
    lowest: int
    highest: int


def signs(rec: Recording) -> Signs:
    s = Signs(rec.frames / rec.rate, 0, 0, 0, 0, 0,
              min(min(ch) for ch in rec.channels), max(max(ch) for ch in rec.channels))
    for ch in rec.channels:
        for start, n in clip_runs(ch):
            if ch[start] > 0:
                s.high_runs, s.high_samples = s.high_runs + 1, s.high_samples + n
            else:
                s.low_runs, s.low_samples = s.low_runs + 1, s.low_samples + n
        s.at_minus_32767 += ch.count(ONE_SHORT)
    return s


def lines(s: Signs | None) -> list[str]:
    if s is None:
        return [f"  {NOT_RECORDED}"]
    return [f"  {s.seconds:.2f} s",
            f"  runs at +32767 {s.high_runs} ({s.high_samples} samples)",
            f"  runs at -32768 {s.low_runs} ({s.low_samples} samples)",
            f"  samples at -32767 {s.at_minus_32767}",
            f"  lowest {s.lowest}, highest {s.highest}"]


def report(label: str, runs: Runs, mixer_seconds: float) -> str:
    unpaced = runs.unpaced
    mixer = signs(cut(unpaced.mixer, mixer_seconds)) if unpaced is not None and unpaced.mixer.exists() else None
    device = signs(read_wav(runs.paced.device)) if runs.paced.device.exists() else None
    top = peak(runs.paced.log.read_text(errors="replace"), sys.maxsize)
    return "\n".join([f"{label} mixer (unpaced run)", *lines(mixer),
                      f"{label} device (real-time run)", *lines(device),
                      f"  main L peak in the log {NOT_LOGGED if top is None else top}"])


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("builds", nargs="+", metavar="LABEL=BUILD_DIR")
    ap.add_argument("--routes", default="", help="comma-separated route names (default: every route)")
    ap.add_argument("--margin", type=int, default=MARGIN_S, help="seconds past the last checkpoint the mixer is cut at")
    args = ap.parse_args(argv)
    if args.margin < 0:
        ap.error("--margin can't be negative")
    try:
        builds = parse_builds(args.builds)
        routes = select_routes([n for n in args.routes.split(",") if n], MANIFEST)
        for route in routes:
            cut_at = seconds(route, args.margin)
            print(f"{route.name}: mixer cut at {cut_at} s")
            for b in builds:
                print(report(b.label, last_runs(b, route), cut_at), flush=True)
            print()
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
