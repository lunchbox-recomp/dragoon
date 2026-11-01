"""What does the soak keep when it stops, and how does a person replay it?

A stop keeps the run's input log and gets a `bot.json` beside it, with the seed, the arguments,
the Dragoon and engine commits and how the run stopped. `replay_line` is the probe.sh command
that plays the input log back with no bot. `new_name` gives each run a NAME no earlier run used,
since a run in an old `build/probe/NAME/` starts from the memory card that run left. It has no
command line.
"""
from __future__ import annotations

import json
import math
import shlex
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

import source_info
from bot_stop import Stop
from bot_watch import Resets

RECORD = "bot.json"


def new_name(seed: int, now: float, taken: Callable[[str], bool]) -> str:
    """A NAME for a run of SEED started at NOW (seconds since the epoch) that TAKEN, which says
    whether a run directory of that name exists, hasn't seen. Two runs in one second of one seed
    differ by a number."""
    name = f"soak-s{seed}-{time.strftime('%Y%m%d-%H%M%S', time.localtime(now))}"
    candidate, n = name, 1
    while taken(candidate):
        n += 1
        candidate = f"{name}-{n}"
    return candidate


def _head(directory: Path) -> Optional[str]:
    if not (directory / ".git").exists():
        return None
    try:
        done = subprocess.run(["git", "-C", str(directory), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return done.stdout.strip() or None


def commits(root: Path) -> dict[str, Optional[str]]:
    """The commits the run played: Dragoon's, at ROOT, and the engine's, at ROOT/gcn-recomp. A
    checkout asks git. A source snapshot has no history, so the commit its source-info.json names
    is used, and git wins in a tree that has both. A commit neither knows is None."""
    try:
        info: dict[str, str] = source_info.read(root / source_info.NAME)
    except (OSError, ValueError):
        info = {}
    return {"dragoon": _head(root) or info.get("dragoon"),
            "engine": _head(root / "gcn-recomp") or info.get("gcn-recomp")}


def replay_line(probe: Path, name: str, input_log: Path, last_frame: Optional[int],
                *, exit_after: bool = True) -> str:
    """The probe.sh command that plays INPUT_LOG back as a run called replay-NAME, which quits
    after LAST_FRAME frames when there is a frame to give and EXIT_AFTER is true. None and 0 are
    none, and probe.sh refuses an --exit-after of 0. The seconds are generous, a real-time
    game's worth of the frames and a minute, since the replay runs as fast as it can."""
    frame = last_frame or None
    seconds = 3600 if frame is None else math.ceil(frame / 60) + 60
    args = [str(probe), f"replay-{name}", str(seconds), "", "60", f"--replay={input_log}"]
    if frame is not None and exit_after:
        args.append(f"--exit-after={frame}")
    return " ".join(shlex.quote(a) for a in args)


def record(*, name: str, seed: int, arguments: dict, commit_ids: dict[str, Optional[str]], stop: Stop,
           resets: Resets, input_log: Optional[Path], replay: Optional[str], frames: int, wall_seconds: float,
           watched: dict[str, bool]) -> dict:
    """What bot.json holds. ARGUMENTS are the soak's, as the command took them, FRAMES the number
    the bots answered and WATCHED says for each detector that reads something the run may not
    have (the picture's hash, the `[axv]` lines) whether it got any."""
    return {
        "name": name,
        "seed": seed,
        "arguments": arguments,
        "commits": commit_ids,
        "stop": {"kind": stop.kind, "detail": stop.detail, "frame": stop.frame,
                 "game_seconds": None if stop.frame is None else round(stop.frame / 60, 1)},
        "after_reset": stop.after_reset,
        "before_reset": stop.before_reset,
        "resets": {"count": resets.count, "first_shaders_line": resets.shaders, "first_shaders_ms": resets.shaders_ms},
        "frames_answered": frames,
        "wall_seconds": round(wall_seconds, 1),
        "watched": watched,
        "input_log": None if input_log is None else str(input_log),
        "replay": replay,
    }


def write(directory: Path, data: dict) -> Path:
    """Writes DATA as RECORD in DIRECTORY and returns the path."""
    path = directory / RECORD
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path
