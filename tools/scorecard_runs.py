"""How the audio scorecard plays a route on a build: one --real-time probe.sh run that records
the DMA's blocks (GCN_AIDWAV), what went to the device (GCN_WAV) and the GCN_AXSTATS log."""
from __future__ import annotations

import math
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from frame_dumps import frame_files
from probe_dirs import trash
from routes import Route, route_file

MARGIN_S = 15  # seconds played past a route's last checkpoint
MIXER_FILE = "mixer.raw"
DEVICE_FILE = "device.wav"
LOG_FILE = "stdout.txt"


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
class Run:
    directory: Path

    @property
    def mixer(self) -> Path:
        return self.directory / MIXER_FILE

    @property
    def device(self) -> Path:
        return self.directory / DEVICE_FILE

    @property
    def log(self) -> Path:
        return self.directory / LOG_FILE


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


def run_for(build: Build, route: Route) -> Run:
    return Run(build.directory / "probe" / f"scorecard-{route.name}")


def probe_args(build: Build, route: Route, margin: int = MARGIN_S) -> list[str]:
    """Dumps one frame, the route's last checkpoint, so the run shows it got there."""
    run, last = run_for(build, route), max(route.required)
    return [str(build.probe), run.directory.name, str(seconds(route, margin)), str(route_file(route.name)),
            str(last), "--real-time", f"GCN_DUMP_RANGE={last}", f"GCN_WAV={run.device}",
            f"GCN_AIDWAV={run.mixer}", "GCN_AXSTATS=1", *route.extra]


def play(build: Build, route: Route, margin: int = MARGIN_S) -> Run:
    run = run_for(build, route)
    if run.directory.exists():
        trash(run.directory)  # a blank memory card; the last run stays after this one
    try:
        subprocess.run(probe_args(build, route, margin), check=True, cwd=build.clone, stdout=subprocess.DEVNULL,
                       env={**os.environ, "SDL_AUDIO_DRIVER": "dummy"})
    except subprocess.CalledProcessError as e:
        raise ValueError(f"{build.label} {route.name}: probe.sh exited {e.returncode}") from None
    return finished(build, route)


def finished(build: Build, route: Route) -> Run:
    """The route's last run on the build, refused if it didn't reach the last checkpoint."""
    run = run_for(build, route)
    last = max(route.required)
    if not run.directory.is_dir() or last not in frame_files(run.directory):
        raise ValueError(f"{build.label} {route.name}: no run in {run.directory} reached frame {last}")
    return run
