"""What does a session's log say about its sound device, its ring and its crashes?

It reads the stdout.txt that tools/playtest.sh tees, or any log with gcn-recomp's [audio],
[ring], [shaders] and [session] lines (GCN_SESSION, GCN_AUDIOSTATS and GCN_AXSTATS in
gcn-recomp's docs/diagnostics.md), into a SessionLog for session_report.py. Output frames
are the device's 48 kHz frames, which are sample indices in the session's out.wav, and DMA
frames are indices in its aid.raw. It has no command line.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

DEVICE = re.compile(r"^\[audio\] device driver=(\S+) rate=(\d+) channels=(\d+) buffer=(\d+)$")
CALLBACKS = re.compile(r"^\[audio\] callbacks n=(\d+) period_ms=([\d.]+) late=(\d+) worst_ms=([\d.]+) "
                       r"underruns=(\d+)$")
LATE = re.compile(r"^\[audio\] late callback at output frame (\d+) gap_ms=([\d.]+)$")
UNDERRUN = re.compile(r"^\[audio\] underrun at output frame (\d+) frames=(\d+)$")
POSITION = re.compile(r"^\[audio\] output frame (\d+) plays DMA frame (\d+)$")
CUT = re.compile(r"^\[ring\] cut (\d+) frames at output frame (\d+)$")
BACKGROUND = re.compile(r"^\[shaders\] built program \d+ in the background in ([\d.]+) ms")
FATAL = re.compile(r"^(FATAL|FAULT):")
SESSION = re.compile(r"^\[session\] (?!can't write )(.+)$")  # a process's directory, not a write that failed
RESET = re.compile(r"^\[reset\] ")
RUN_DIR = re.compile(r"run-(\d+)")


@dataclass
class Device:
    driver: str
    rate: int
    channels: int
    buffer: int


@dataclass
class Callbacks:
    n: int
    period_ms: float
    late: int
    worst_ms: float
    underruns: int


@dataclass
class SessionLog:
    device: Device | None = None
    callbacks: Callbacks | None = None  # the last callbacks line
    late: list[tuple[int, float]] = field(default_factory=list)  # (output frame, gap in ms)
    underruns: list[tuple[int, int]] = field(default_factory=list)  # (output frame, frames short)
    positions: list[tuple[int, int]] = field(default_factory=list)  # (output frame, DMA frame)
    cuts: list[tuple[int, int]] = field(default_factory=list)  # (output frame, ring frames dropped)
    background_ms: list[float] = field(default_factory=list)  # shaders built off the render thread
    fatal: list[str] = field(default_factory=list)
    reset: bool = False  # the game reset the console, which ends this run


def runs(lines: list[str]) -> list[list[str]]:
    """The log cut where each process of a session began. A game that resets the console
    relaunches itself, and the new process prints its own [session] line, for <dir>/run-N.
    Lines before the first [session] line go with the first run."""
    parts: list[list[str]] = [[]]
    seen = False
    for line in lines:
        if SESSION.match(line):
            if seen:
                parts.append([])
            seen = True
        parts[-1].append(line)
    return parts


def parse(lines: list[str]) -> SessionLog:
    log = SessionLog()
    for line in lines:
        line = line.rstrip("\n")
        if m := DEVICE.match(line):
            log.device = Device(m[1], int(m[2]), int(m[3]), int(m[4]))
        elif m := CALLBACKS.match(line):
            log.callbacks = Callbacks(int(m[1]), float(m[2]), int(m[3]), float(m[4]), int(m[5]))
        elif m := LATE.match(line):
            log.late.append((int(m[1]), float(m[2])))
        elif m := UNDERRUN.match(line):
            log.underruns.append((int(m[1]), int(m[2])))
        elif m := POSITION.match(line):
            log.positions.append((int(m[1]), int(m[2])))
        elif m := CUT.match(line):
            log.cuts.append((int(m[2]), int(m[1])))
        elif m := BACKGROUND.match(line):
            log.background_ms.append(float(m[1]))
        elif FATAL.search(line):
            log.fatal.append(line)
        elif RESET.match(line):
            log.reset = True
    return log


def find_log(session: Path) -> tuple[Path, int] | None:
    """Where a session directory's log is, and which run of it is this directory's: its own
    stdout.txt, or for <dir>/run-N its parent's, from which run N is taken."""
    own = session / "stdout.txt"
    if own.is_file():
        return own, 0
    parent = session.parent / "stdout.txt"
    if (m := RUN_DIR.fullmatch(session.name)) and parent.is_file():
        return parent, int(m[1]) - 1
    return None


def run_lines(session: Path) -> tuple[list[str], Path] | None:
    """This directory's run of the session's log and the file it's in, or None when there's
    no log."""
    found = find_log(session)
    if not found:
        return None
    path, run = found
    with path.open(errors="replace") as f:
        parts = runs(f.readlines())
    return (parts[run] if run < len(parts) else []), path
