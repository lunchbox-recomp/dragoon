#!/usr/bin/env python3
"""How does each build's sound measure, route by route? Clicks, gaps and clipping before and
after the audio ring, with nobody listening.

Usage: audio_scorecard.py LABEL=BUILD_DIR [LABEL=BUILD_DIR ...] [--routes R,R] [--margin S]
                          [--no-run] [--json]

BUILD_DIR is a Dragoon clone's build/ directory, and LABEL names it in the tables. Every route
in tests/hashes/manifest.txt (or the ones --routes names) plays on each build, a route at a
time across the builds, through that clone's own tools/probe.sh: a hidden window, SDL's dummy
audio driver, GCN_AXSTATS=1, and the route file and manifest settings from this clone. Each
route plays twice on a build, once --real-time and once unpaced. Each run lasts the route's
last checkpoint at 60 frames a second plus --margin seconds (15 by default) of wall-clock time,
and dumps that one frame to show it got there. They go to <clone>/build/probe/scorecard-ROUTE/
and scorecard-unpaced-ROUTE/, and an earlier run there is deleted first, so the game
starts from a blank memory card and an empty shader cache. --no-run measures the runs already
there instead.

The tool reads each clone's Dragoon and gcn-recomp commits (with -dirty when tracked files have
changed) before the first route plays, and leaves them in each run's commits.json. --no-run
prints the commits its runs recorded, or "not recorded" for a run made before the file existed.

The two stages are measured with audio_clicks.py's functions, each from the run that suits it.

  mixer   The unpaced run's GCN_AIDWAV, the DMA's blocks before the ring (raw, 32 kHz), cut
          to the route's last checkpoint plus --margin seconds. Unpaced, the game's time
          doesn't follow the host's, so two runs of one build should give the same blocks. A
          real-time run's clock catches up when the host falls behind, and then the DMA plays
          a block twice, presses land on other frames and sounds move, so its blocks differ
          from run to run. Clicks a minute, the clicks within 2 samples of a 160-sample block
          join beside the count chance gives, gaps and clipped runs. The run's log gives the
          highest main L peak before the output clamp and the samples the clamp changed, from
          the [ax] lines within the cut. A recording shorter than the cut exits 2.
  device  The real-time run's GCN_WAV, what went to the device, ring included (48 kHz).
          Clicks a minute, gaps and clipped runs, and the clicks within 2 samples of a ring cut
          when the build logs cuts. Its log gives the ring's cuts and underruns.

Each log value reads "not logged" where the build doesn't print it. A stage whose recording is
missing reads "not recorded", and so does the whole mixer stage, its log values included, when
--no-run finds no unpaced run. --no-run cuts the mixer stage at --margin as a run would. It
prints a table per route as the route finishes, then the totals: counts and seconds summed,
clicks a minute over the summed seconds, the highest peak. --json prints the whole result as
JSON at the end.

Exits 0 once every route is measured. It only reports, so it never exits 1. Exits 2 on a bad
argument, a build directory its probe.sh won't run, a run that fails or doesn't reach its last
checkpoint, a recording it can't read or a recording shorter than the cut.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from routes import MANIFEST, Route, select_routes
from scorecard_measure import Score, Stage, measure, total
from scorecard_runs import MARGIN_S, Build, Commits, Runs, check_build, last_runs, play, read_commits, seconds

NOT_LOGGED, NOT_RECORDED = "not logged", "not recorded"


def parse_build(text: str) -> Build:
    label, sep, path = text.partition("=")
    if not sep or not label or not path:
        raise ValueError(f"{text}: not LABEL=BUILD_DIR")
    return Build(label, Path(path).expanduser().resolve())


def parse_builds(texts: list[str]) -> list[Build]:
    builds = [parse_build(t) for t in texts]
    for what, values in (("label", [b.label for b in builds]), ("build directory", [b.directory for b in builds])):
        twice = sorted({str(v) for v in values if values.count(v) > 1})
        if twice:
            raise ValueError(f"the same {what} twice: {', '.join(twice)}")
    return builds


def describe(path: Path) -> str | None:
    """The checkout's commit, with -dirty when tracked files have changed. Tags are left out."""
    got = subprocess.run(["git", "-C", str(path), "describe", "--always", "--dirty", "--abbrev=7", "--exclude=*"],
                         capture_output=True, text=True)
    return (got.stdout.strip() or None) if got.returncode == 0 else None


def agree(values: list[str | None]) -> str | None:
    """The one value every run has, or all of them when the runs differ."""
    distinct = list(dict.fromkeys(values))
    return distinct[0] if len(distinct) == 1 else " and ".join(map(str, distinct))


def commits_of(build: Build, runs: list[Runs] | None) -> Commits:
    """What the build's RUNS recorded when they're already there (--no-run), which is what the
    clone had checked out when the tool started them, else what it has checked out now, which
    the tool reads before any route plays."""
    if runs is None:
        return Commits(describe(build.clone), describe(build.clone / "gcn-recomp"))
    each = [run for r in runs for run in (r.paced, r.unpaced) if run is not None]
    found = [read_commits(run) or Commits(NOT_RECORDED, NOT_RECORDED) for run in each]
    return Commits(agree([c.dragoon for c in found]), agree([c.gcn_recomp for c in found]))


def count(n: int | None) -> str:
    return NOT_LOGGED if n is None else str(n)


def near(n: int | None, chance: float | None) -> str:
    return NOT_LOGGED if n is None else f"{n} ({chance:.1f} by chance)"


def stage_rows(name: str, s: Stage | None) -> list[tuple[str, str]]:
    labels = [f"{name} seconds", f"{name} clicks", f"{name} clicks a minute", f"{name} gaps",
              f"{name} clipped runs (samples)"]
    if s is None:
        return [(label, NOT_RECORDED) for label in labels]
    return list(zip(labels, [f"{s.seconds:.2f}", str(s.clicks), f"{s.per_minute:.1f}", str(s.gaps),
                             f"{s.clipped_runs} ({s.clipped_samples})"]))


def rows(score: Score) -> list[tuple[str, str]]:
    m, d = score.mixer, score.device
    return [
        *stage_rows("mixer", m),
        ("mixer clicks on a block join", NOT_RECORDED if m is None else near(m.on_joins, m.joins_by_chance)),
        ("main L peak before the clamp", NOT_RECORDED if m is None else count(score.peak)),
        ("samples the clamp changed", NOT_RECORDED if m is None else count(score.clamped)),
        *stage_rows("device", d),
        ("device clicks on a ring cut", NOT_RECORDED if d is None else near(d.on_cuts, d.cuts_by_chance)),
        ("ring cuts", count(score.cuts)),
        ("ring underruns", count(score.underruns)),
    ]


def table(title: str, labels: list[str], scores: list[Score]) -> str:
    columns = [rows(s) for s in scores]
    names = [name for name, _ in columns[0]]
    cells = [["", *labels]] + [[name, *(col[i][1] for col in columns)] for i, name in enumerate(names)]
    widths = [max(len(row[c]) for row in cells) for c in range(len(cells[0]))]
    lines = [title] + ["  ".join(v.ljust(w) if c == 0 else v.rjust(w) for c, (v, w) in enumerate(zip(row, widths)))
                       .rstrip() for row in cells]
    return "\n".join(lines) + "\n"


def route_title(route: Route, margin: int | None) -> str:
    """With no margin, the runs were already there, and how long they played isn't known."""
    played = "" if margin is None else f"{seconds(route, margin)} s a run, "
    return f"{route.name}: {played}to frame {max(route.required)}"


def as_json(builds: list[Build], routes: list[Route], scores: dict[str, list[Score]],
            commits: dict[str, Commits]) -> str:
    return json.dumps({
        "routes": [r.name for r in routes],
        "builds": [{"label": b.label, "build": str(b.directory), "dragoon": commits[b.label].dragoon,
                    "gcn_recomp": commits[b.label].gcn_recomp,
                    "routes": {r.name: asdict(s) for r, s in zip(routes, scores[b.label])},
                    "total": asdict(total(scores[b.label]))} for b in builds],
    }, indent=1)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("builds", nargs="+", metavar="LABEL=BUILD_DIR")
    ap.add_argument("--routes", default="", help="comma-separated route names (default: every route)")
    ap.add_argument("--margin", type=int, default=MARGIN_S, help="seconds played past the last checkpoint")
    ap.add_argument("--no-run", action="store_true", help="measure the runs already in build/probe/")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.margin < 0:
        ap.error("--margin can't be negative")
    try:
        builds = parse_builds(args.builds)
        for b in builds:
            check_build(b)
        routes = select_routes([n for n in args.routes.split(",") if n], MANIFEST)
        labels = [b.label for b in builds]
        found = {b.label: [last_runs(b, r) for r in routes] for b in builds} if args.no_run else None
        commits = {b.label: commits_of(b, None if found is None else found[b.label]) for b in builds}
        if not args.json:
            for b in builds:
                print(f"{b.label}: {b.directory}, Dragoon {commits[b.label].dragoon}, "
                      f"gcn-recomp {commits[b.label].gcn_recomp}")
            print()
        scores: dict[str, list[Score]] = {b.label: [] for b in builds}
        for i, route in enumerate(routes):
            for b in builds:
                runs = found[b.label][i] if found is not None else play(b, route, args.margin, commits=commits[b.label])
                scores[b.label].append(measure(runs, seconds(route, args.margin)))
            if not args.json:
                print(table(route_title(route, None if args.no_run else args.margin), labels,
                            [scores[label][-1] for label in labels]), flush=True)
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    if args.json:
        print(as_json(builds, routes, scores, commits))
    else:
        print(table(f"total: {len(routes)} route{'s' * (len(routes) != 1)}", labels,
                    [total(scores[label]) for label in labels]), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
