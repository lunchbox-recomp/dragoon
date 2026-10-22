#!/usr/bin/env python3
"""Does a playtest session replay faithfully, and where does its mixer click?

Usage: replay_session.py DIR [--list N]

DIR is a session directory that tools/playtest.sh made, or a run-N inside one. Its input log
(DIR/inputs) is played back in a hidden window with nobody at the controls and no sound,
through tools/probe.sh --replay with SDL's dummy audio driver, GCN_AIDWAV and GCN_AXSTATS=1,
as build/probe/replay-<name>/. The guest's clock is virtual, so a faithful replay gives the
mixer the same blocks the session gave it. This compares the SHA-1 of the session's aid.raw
with that of as much of the replay's, and says where they first differ when they do. Then
it lists the clicks audio_clicks.py finds in the replay's mixer audio over the session's
length, and any line where the game said the replay parted from its recording. --list N caps
the click times printed (default 10).

The replay runs to 60 frames a second of the session's mixer audio and 600 more, which no
game presenting at most 60 a second can fall short of, with twice the session's length and
two minutes for probe.sh's wall clock. The input log is copied into the replay's directory
first, since a replay keeps a scratch copy of the memory card beside the log it reads, so the
session stays as it was. A replay directory from before is moved to the Trash. A session
recorded on another engine commit than the one built is likely to part from its recording,
and the report says so.

Exits 0 when the replay's mixer audio matches the session's, 1 when it differs or stops
short, 2 on a bad argument, a session without inputs/ or aid.raw, or a probe.sh run that
failed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import audio_clicks
import probe_dirs

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe.sh"
PROBE_ROOT = ROOT / "build" / "probe"
ENGINE_HEADER = ROOT / "build" / "gcn_engine_sha" / "gcn_engine_sha.h"
DMA_RATE = 32000          # aid.raw's rate
FRAME_BYTES = 4           # a 16-bit stereo frame
FRAMES_A_SECOND = 60      # the most a game presents a second of guest time
EXTRA_FRAMES = 600
CHUNK = 1 << 20
PARTED = re.compile(r"^\[input\] the replay has parted from its recording", re.MULTILINE)
ENGINE = re.compile(r'#define GCN_ENGINE_SHA "([^"]*)"')


@dataclass
class Comparison:
    session_bytes: int
    replay_bytes: int
    session_sha1: str
    replay_sha1: str  # of the replay's first session_bytes, or all of it when it's shorter
    first_difference: int | None  # a byte offset, where both have bytes

    @property
    def short(self) -> bool:
        return self.replay_bytes < self.session_bytes

    @property
    def match(self) -> bool:
        return not self.short and self.session_sha1 == self.replay_sha1


@dataclass
class Replay:
    out: Path
    comparison: Comparison
    clicks: list[float] = field(default_factory=list)
    parted: list[str] = field(default_factory=list)
    engine: str | None = None  # why the engines may differ, when they do


def compare(session_aid: Path, replay_aid: Path) -> Comparison:
    """The two recordings over the session's length, read a chunk at a time."""
    n = session_aid.stat().st_size
    a_hash, b_hash = hashlib.sha1(), hashlib.sha1()
    first = None
    done = 0
    with session_aid.open("rb") as a, replay_aid.open("rb") as b:
        while done < n:
            x = a.read(CHUNK)
            y = b.read(len(x))
            a_hash.update(x)
            b_hash.update(y)
            if first is None and x[:len(y)] != y:
                first = done + next(i for i, (p, q) in enumerate(zip(x, y)) if p != q)
            done += len(x)
            if len(y) < len(x):
                break
    return Comparison(n, replay_aid.stat().st_size, a_hash.hexdigest(), b_hash.hexdigest(), first)


def replay_clicks(replay_aid: Path, length: int) -> list[float]:
    with replay_aid.open("rb") as f:
        raw = f.read(length)
    if len(raw) < FRAME_BYTES:
        return []
    rec = audio_clicks.split(replay_aid, raw, 2, DMA_RATE)
    return [c.at for c in audio_clicks.analyse_long(rec).clicks]


def engine_note(session: Path, header: Path) -> str | None:
    try:
        recorded = json.loads((session / "session.json").read_text()).get("engine_sha")
    except (OSError, ValueError):
        return None
    m = ENGINE.search(header.read_text()) if header.is_file() else None
    built = m[1] if m else None
    if recorded and built and recorded != built:
        return f"the session was recorded on engine {recorded} and the build is {built}"
    return None


def name_for(session: Path) -> str:
    if re.fullmatch(r"run-\d+", session.name):
        return f"replay-{session.parent.name}-{session.name}"
    return f"replay-{session.name}"


def probe_args(name: str, seconds: float, inputs: Path, aid: Path) -> list[str]:
    frames = math.ceil(seconds * FRAMES_A_SECOND) + EXTRA_FRAMES
    wall = math.ceil(2 * seconds) + 120
    return [str(PROBE), name, str(wall), "", "1000000", f"GCN_AIDWAV={aid}", "GCN_AXSTATS=1",
            f"--replay={inputs}", f"--exit-after={frames}"]


def replay(session: Path, probe_root: Path = PROBE_ROOT, run=subprocess.run, trash=probe_dirs.trash,
           header: Path = ENGINE_HEADER) -> Replay:
    session = session.resolve()
    inputs, aid = session / "inputs", session / "aid.raw"
    for path in (inputs, aid):
        if not path.exists():
            raise ValueError(f"{path}: missing; is {session} a session directory?")
    seconds = aid.stat().st_size / (FRAME_BYTES * DMA_RATE)
    name = name_for(session)
    out = probe_root / name
    if out.exists():
        trash(out)
    out.mkdir(parents=True)
    copy = out / "inputs"
    shutil.copytree(inputs, copy)
    replay_aid = out / "aid.raw"
    result = run(probe_args(name, seconds, copy, replay_aid), cwd=ROOT, stdout=subprocess.DEVNULL,
                 env={**os.environ, "SDL_AUDIO_DRIVER": "dummy"})
    if result.returncode != 0:
        raise ValueError(f"probe.sh exited {result.returncode}; its log is {out / 'stdout.txt'}")
    if not replay_aid.is_file():
        raise ValueError(f"{replay_aid}: the replay wrote no mixer audio; its log is {out / 'stdout.txt'}")
    log = out / "stdout.txt"
    text = log.read_text(errors="replace") if log.is_file() else ""
    c = compare(aid, replay_aid)
    return Replay(out, c, replay_clicks(replay_aid, c.session_bytes),
                  [line for line in text.splitlines() if PARTED.match(line)], engine_note(session, header))


def secs(byte: int) -> float:
    return byte / (FRAME_BYTES * DMA_RATE)


def render(session: Path, r: Replay, limit: int) -> list[str]:
    c = r.comparison
    lines = [f"session  {session}, {secs(c.session_bytes):.1f} s of mixer audio",
             f"replay   {r.out}"]
    if c.match:
        lines.append(f"match    yes: the first {c.session_bytes} bytes of both aid.raw files have SHA-1 {c.session_sha1}")
    elif c.first_difference is not None:
        lines.append(f"match    no: they first differ {secs(c.first_difference):.3f} s in, at byte "
                     f"{c.first_difference}; the session's SHA-1 is {c.session_sha1} and the replay's {c.replay_sha1}")
    if c.short:
        lines.append(f"match    no: the replay's aid.raw stops at {secs(c.replay_bytes):.1f} s of "
                     f"{secs(c.session_bytes):.1f}")
    per_minute = len(r.clicks) / (secs(c.session_bytes) / 60) if c.session_bytes else 0.0
    lines.append(f"mixer    {len(r.clicks)} clicks in the replay over the session's length ({per_minute:.1f} a minute)")
    lines += [f"    {t:.3f} s" for t in r.clicks[:limit]]
    if len(r.clicks) > limit:
        lines.append(f"    and {len(r.clicks) - limit} more")
    lines.append("parted   " + ("never" if not r.parted else f"{len(r.parted)} times"))
    lines += [f"    {line}" for line in r.parted[:limit]]
    if r.engine:
        lines.append(f"engine   {r.engine}, so the replay may part from it")
    return lines


def main(argv: list[str], run=subprocess.run, probe_root: Path = PROBE_ROOT) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", type=Path)
    ap.add_argument("--list", type=int, default=10)
    args = ap.parse_args(argv)
    if args.list < 0:
        ap.error("--list can't be negative")
    try:
        r = replay(args.dir, probe_root, run)
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    print("\n".join(render(args.dir, r, args.list)))
    return 0 if r.comparison.match else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
