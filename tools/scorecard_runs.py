"""How the audio scorecard plays a route on a build: two probe.sh runs. The unpaced one records
the DMA's blocks (GCN_AIDWAV) for the mixer stage, and two unpaced runs of one build should give
the same blocks. The --real-time one records what went to the device (GCN_WAV) for the device
stage, and the DMA's blocks again for tools that look at its catch-up. Both log GCN_AXSTATS."""
from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from frame_dumps import frame_files
from probe_dirs import remove_run, run_probe
from routes import Route, route_file

MARGIN_S = 15  # seconds played past a route's last checkpoint
MIXER_FILE = "mixer.raw"
DEVICE_FILE = "device.wav"
LOG_FILE = "stdout.txt"
COMMITS_FILE = "commits.json"


@dataclass
class Build:
    label: str
    directory: Path  # a clone's build/, which is the only one its probe.sh runs

    @property
    def clone(self) -> Path:
        return self.directory.parent

    @property
    def probe(self) -> Path:
        return self.clone / "tools" / "probe.sh"


@dataclass
class Commits:
    """What its clone had checked out when the tool started: describe()'s text for the clone and
    for its gcn-recomp, None outside git."""
    dragoon: str | None
    gcn_recomp: str | None


@dataclass
class Run:
    directory: Path

    @property
    def commits(self) -> Path:
        return self.directory / COMMITS_FILE

    @property
    def mixer(self) -> Path:
        return self.directory / MIXER_FILE

    @property
    def device(self) -> Path:
        return self.directory / DEVICE_FILE

    @property
    def log(self) -> Path:
        return self.directory / LOG_FILE


@dataclass
class Runs:
    """A route's two runs on a build."""
    paced: Run            # --real-time: the device stage and the ring
    unpaced: Run | None   # the mixer stage; None for --no-run on a build that has no unpaced run


def check_build(build: Build) -> None:
    """Refuse a build directory its clone's probe.sh wouldn't run the game from."""
    if build.directory.name != "build":
        raise ValueError(f"{build.directory}: probe.sh runs the game only from its clone's build/")
    if not os.access(build.probe, os.X_OK):
        raise ValueError(f"{build.probe}: no probe.sh to run")
    game = build.directory / "dragoon"
    if not os.access(game, os.X_OK):
        raise ValueError(f"{game}: not built")


def seconds(route: Route, margin: int = MARGIN_S) -> int:
    """The route's last checkpoint at the game's 60 frames a second, plus MARGIN seconds."""
    return math.ceil(max(route.required) / 60) + margin


def run_for(build: Build, route: Route, unpaced: bool = False) -> Run:
    name = f"scorecard-unpaced-{route.name}" if unpaced else f"scorecard-{route.name}"
    return Run(build.directory / "probe" / name)


def probe_args(build: Build, route: Route, margin: int = MARGIN_S, unpaced: bool = False) -> list[str]:
    """Dumps one frame, the route's last checkpoint, so the run shows it got there. An unpaced
    run plays as many wall-clock seconds as a real-time one, which gives it more of the game's
    time than the mixer stage scores, and records no device stage."""
    run, last = run_for(build, route, unpaced), max(route.required)
    paced = [] if unpaced else ["--real-time"]
    device = [] if unpaced else [f"GCN_WAV={run.device}"]
    return [str(build.probe), run.directory.name, str(seconds(route, margin)), str(route_file(route.name)),
            str(last), *paced, f"GCN_DUMP_RANGE={last}", *device, f"GCN_AIDWAV={run.mixer}", "GCN_AXSTATS=1",
            *route.extra]


def play_one(build: Build, route: Route, margin: int, unpaced: bool, commits: Commits) -> Run:
    run = run_for(build, route, unpaced)
    if run.directory.exists():
        remove_run(run.directory)  # a blank memory card; the last run stays after this one
    what = f"{build.label} {route.name}" + (" unpaced" if unpaced else "")
    run_probe(probe_args(build, route, margin, unpaced), build.clone, what,
              {**os.environ, "SDL_AUDIO_DRIVER": "dummy"})
    run = finished(build, route, unpaced)
    run.commits.write_text(json.dumps(asdict(commits)) + "\n")
    return run


def play(build: Build, route: Route, margin: int = MARGIN_S, *, commits: Commits) -> Runs:
    """Plays the route in real time, then unpaced, and leaves COMMITS in each run's directory,
    for a later --no-run."""
    return Runs(play_one(build, route, margin, False, commits), play_one(build, route, margin, True, commits))


def read_commits(run: Run) -> Commits | None:
    """What the run's clone had checked out when the tool started, or None for a run made before
    the tool recorded it."""
    if not run.commits.exists():
        return None
    try:
        return Commits(**json.loads(run.commits.read_text()))
    except (ValueError, TypeError):
        raise ValueError(f"{run.commits}: not a commits file") from None


def finished(build: Build, route: Route, unpaced: bool = False) -> Run:
    """The route's last run on the build, refused if it didn't reach the last checkpoint."""
    run = run_for(build, route, unpaced)
    last = max(route.required)
    if not run.directory.is_dir() or last not in frame_files(run.directory):
        raise ValueError(f"{build.label} {route.name}: no run in {run.directory} reached frame {last}")
    return run


def last_runs(build: Build, route: Route) -> Runs:
    """The route's runs already on the build, for --no-run. The unpaced one is None when its
    directory isn't there, as for runs made before the scorecard played one."""
    unpaced = run_for(build, route, unpaced=True).directory.is_dir()
    return Runs(finished(build, route), finished(build, route, unpaced=True) if unpaced else None)
