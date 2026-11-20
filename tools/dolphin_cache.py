"""Dolphin's side of the nightly's Dolphin diff: a route's converged movie and Dolphin's run of
it, kept in build/nightly/dolphin-cache/ROUTE/ and played again only when something it depends
on has changed.

Dolphin is deterministic for a fixed movie and pin (docs/dev/status.md, "Dolphin reference"), so
a run is reused while key.json still says what it was played with: the movie's sha256, the
Dolphin binary's, the build's record of its commit and patch (dolphin_ref.BUILT), the config and
game INI dolphin_ref.py writes, the words it watches, the disc speed and fields, the triage
file's head line and the macOS version, since Dolphin draws through the system's Metal. The
movie also has to still be its own fixed point for the route as it is now: dtm.make from the
run's timeline gives it back byte for byte. And every dump frames.txt lists has to be there.
Anything else is stale, and `ready` plays Dolphin again.

Playing again converges the movie as dtm.py converge does, starting from the saved run's
timeline when there is one, so a route that changed a little takes a run or two, not seven.
Every run plays through dolphin_ref.py boot, sandboxed with no network, with frame dumps and
dolphin_diff's watches on, and with the pad queue's words too so dtm's press check reads the
same run. Each run first calls BEFORE, as each game process does in the nightly. `log stream`
runs over the whole of it, filtered as dolphin_ref.py says, into the run's log, and every denial
but /dev/dtracehelper's is given back. The fixed point's run replaces the saved one and key.json
is written last, so a stopped rerun leaves nothing that looks current.

It never fetches or builds Dolphin: `missing` says when dolphin_ref.py's set-up isn't there.
It has no command line.
"""
from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Sequence

import dolphin_diff
import dolphin_ref
import dtm
from routes import parse_route

CACHE = "dolphin-cache"  # under build/nightly/
KEY = "key.json"
MOVIE = "movie.dtm"
SAVED = "dolphin"  # the saved run, a dolphin_ref.py boot --out folder
LOG_STREAM = ("/usr/bin/log", "stream", "--style", "compact", "--predicate",
              'eventMessage CONTAINS "dolphin-ref" AND eventMessage CONTAINS "deny("')
LOG_READY = "Filtering the log data"  # log stream's first line, once it's listening
HARMLESS = "/dev/dtracehelper"  # each process's DTrace probe offer, which the sandbox refuses
CONVERGE_MAX = dtm.CONVERGE_MAX


class Bad(ValueError):
    """A Dolphin side that couldn't be played."""


def dolphin_root() -> Path:
    return dolphin_ref.default_root()


def missing(root: Path) -> Optional[str]:
    """Why there's no Dolphin to play at ROOT, None when its source and binary are there."""
    for path in (root / "src", root / "build" / dolphin_ref.NOGUI):
        if not path.exists():
            return f"no {path}"
    return None


def checked(root: Path) -> None:
    """Refuse a Dolphin set-up dolphin_ref.py boot would refuse, before anything plays."""
    dolphin_ref.check_build(root / "build", dolphin_ref.check_tree(root / "src"))


def watched() -> list[str]:
    words = dolphin_diff.watches()
    pads = [f"{a:08X}" for a in (dtm.PAD_STATE, *dtm.BUTTON_WORDS)]
    return words + [w for w in pads if w not in words]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def key(root: Path, movie: bytes, fields: int, triage_head: str) -> dict:
    build = root / "build"
    config = json.dumps(dolphin_ref.CONFIG, sort_keys=True) + dolphin_ref.game_ini()
    return {"movie": sha256(movie), "dolphin": sha256((build / dolphin_ref.NOGUI).read_bytes()),
            "built": (build / dolphin_ref.BUILT).read_text(), "config": sha256(config.encode()),
            "watches": watched(), "disc": dolphin_diff.DISC, "fields": fields,
            "triage": triage_head, "macos": platform.mac_ver()[0]}


def stale(cache: Path, root: Path, script: str, fields: int, triage_head: str) -> Optional[str]:
    """Why CACHE's saved run can't be reused, None when it can."""
    saved, movie = cache / SAVED, cache / MOVIE
    if not (cache / KEY).is_file() or not movie.is_file() or not (saved / "ram.txt").is_file():
        return "no saved run"
    data = movie.read_bytes()
    want, had = key(root, data, fields, triage_head), json.loads((cache / KEY).read_text())
    changed = [k for k in want if had.get(k) != want[k]]
    if changed:
        return f"its {', '.join(changed)} changed"
    if dtm.make(script, fields, dtm.game_frames(dtm.read_lines(saved / "ram.txt"))) != data:
        return "the movie isn't the route's fixed point now"
    listed = (saved / "frames.txt").read_text().splitlines() if (saved / "frames.txt").is_file() else []
    if not listed or any(not (saved / "frames" / line.split()[1]).is_file() for line in listed):
        return "a dump it lists is gone"
    return None


def play(iso: Path, movie: Path, fields: int, out: Path) -> int:
    """Dolphin playing MOVIE for FIELDS fields into OUT, through dolphin_ref.py boot."""
    return subprocess.run(dtm.boot_command(iso, movie, fields, out, dolphin_diff.DISC, watched(),
                                           dump=True)).returncode


class SandboxLog:
    """`log stream` for Dolphin's sandbox denials while the block runs, into PATH."""

    def __init__(self, path: Path, command: Optional[Sequence[str]] = None) -> None:
        self.path = path
        self.command = list(command or LOG_STREAM)
        self.lines: list[str] = []

    def __enter__(self) -> "SandboxLog":
        self.proc = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True)
        assert self.proc.stdout is not None
        first = self.proc.stdout.readline()
        if not first.startswith(LOG_READY):
            self.proc.kill()
            self.proc.stdout.close()
            self.proc.wait()
            raise Bad(f"log stream didn't start: {first.strip() or 'no output'}")
        self.lines.append(first)
        self.drain = threading.Thread(target=self.read, daemon=True)
        self.drain.start()
        return self

    def read(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self.lines.append(line)

    def __exit__(self, *exc) -> None:
        self.proc.terminate()
        self.proc.wait()
        self.drain.join()
        self.proc.stdout.close()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("".join(self.lines))

    def denied(self) -> list[str]:
        return [line.strip() for line in self.lines if "deny(" in line and HARMLESS not in line]


@dataclass
class Side:
    folder: Path  # the saved run: ram.txt, frames.txt and frames/
    runs: int  # Dolphin's runs tonight, 0 when the saved one was reused
    why: str  # why it played again, "" when it didn't
    off: list[str] = field(default_factory=list)  # each press the game didn't read on its frame
    denied: list[str] = field(default_factory=list)  # the sandbox's denials, but HARMLESS's

    def text(self) -> str:
        if not self.runs:
            return "Dolphin's saved run reused"
        return f"Dolphin played again ({self.why}), {self.runs} runs to the movie's fixed point"


def presses_off(script: str, lines: Sequence[str]) -> list[str]:
    """Each of SCRIPT's presses Dolphin's run didn't read on its route frame, as dtm.py presses
    says it."""
    out = []
    for p, field_, frame in dtm.press_reads(parse_route(script), lines):
        names = "+".join(sorted(p.buttons))
        if field_ < 0:
            out.append(f"{p.at}:{names} never read")
        elif frame != p.at:
            out.append(f"{p.at}:{names} read at game frame {frame}")
    return out


def ready(cache: Path, script: str, fields: int, iso: Path, triage_head: str, log: Path,
          before: Callable[[], None], root: Optional[Path] = None) -> Side:
    """CACHE's saved run of SCRIPT's movie, played again first when it's stale."""
    root = root or dolphin_root()
    why = stale(cache, root, script, fields, triage_head)
    saved = cache / SAVED
    if why is None:
        return Side(saved, 0, "", presses_off(script, dtm.read_lines(saved / "ram.txt")))
    old = saved / "ram.txt"
    timeline = dtm.game_frames(dtm.read_lines(old)) if old.is_file() else []
    (cache / KEY).unlink(missing_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    run, movie_path = cache / "run", cache / "next.dtm"
    with SandboxLog(log) as sandbox:
        for n in range(1, CONVERGE_MAX + 1):
            movie = dtm.make(script, fields, timeline)
            movie_path.write_bytes(movie)
            if run.exists():
                shutil.rmtree(run)
            before()
            code = play(iso, movie_path, fields, run)
            if code:
                raise Bad(f"Dolphin's run {n} exited {code}, short of {fields} fields")
            lines = dtm.read_lines(run / "ram.txt")
            timeline = dtm.game_frames(lines)
            if dtm.make(script, fields, timeline) == movie:
                break
        else:
            raise Bad(f"no fixed point in {CONVERGE_MAX} runs")
    if saved.exists():
        shutil.rmtree(saved)
    run.rename(saved)
    movie_path.rename(cache / MOVIE)
    (cache / KEY).write_text(json.dumps(key(root, movie, fields, triage_head), indent=1) + "\n")
    return Side(saved, n, why, presses_off(script, lines), sandbox.denied())
