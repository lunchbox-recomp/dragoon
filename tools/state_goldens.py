#!/usr/bin/env python3
"""Does a route still play the same? Read the game's state at a route's checkpoints and compare it.

Usage: state_goldens.py check  [ROUTE ...] [--aspect=16:9]
       state_goldens.py record [ROUTE ...] [--aspect=16:9]

Plays each route in tests/hashes/manifest.txt through bot_link.py with a bot that presses
nothing, so the route's presses are the only ones, as ram_peek.py does. At each of the route's
required frames, its checkpoints, it reads FIELDS from guest RAM by their names in kar_ram.json.
The engine's frame numbers can jump, so a checkpoint is read at the first frame the engine steps
the bot at that's as late or later, and the golden keeps that frame too. Goldens are in
tests/hashes/state/<route>.txt, one line a checkpoint:

  frame 4200 read 4200 scene.major=4 scene.minor=18 players.count=4 ...

They hold numbers the game computed and nothing read from the disc. A value behind a null
pointer, such as a player who isn't in the race, is "none", and a float is written with nine
figures, enough to give back the f32. record rewrites the goldens, and writes none for a route
that didn't reach every checkpoint. --aspect=16:9 plays at 16:9 and keeps its goldens in
tests/hashes/state-16x9/, as frame_hashes.py does, since air-ride-courses-2 plays its third race
differently at 16:9.

Each run is build/probe/state-ROUTE/, deleted first so the game starts from a blank memory
card, and deleted after. A run gets twice its manifest seconds and quits one dump interval past
its last checkpoint, as frame_hashes.py check --slow=2 does.

Exits 0 when every route matches (or is recorded), 1 when a value changed, a checkpoint wasn't
reached or a run ended some other way than its --exit-after, 2 on a bad argument, a missing or
malformed golden, or a game that never connected.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Optional

import bot_link
import kar_ram
from bot_link import Link, Pad
from probe_dirs import remove_run
from routes import MANIFEST, Route, route_file, select_routes

ROOT = Path(__file__).resolve().parents[1]
HASHES = ROOT / "tests" / "hashes"
STATES = {"4:3": "state", "16:9": "state-16x9"}  # the directory under HASHES each aspect's goldens are in
PLAYERS = range(1, 5)
# What a checkpoint reads, all of it kar_ram.json's. The players' values read none or 0 for a
# port nobody plays, and Top Ride keeps its riders where these don't look (kar_ram.json).
FIELDS = ("scene.major", "scene.minor", "players.count", "players.humans",
          *(f"player{n}.kind" for n in PLAYERS), *(f"player{n}.speed" for n in PLAYERS),
          *(f"player{n}.{axis}" for n in PLAYERS for axis in "xyz"))
# What a race's state would hold that kar_ram.json doesn't map yet, so no golden checks it.
UNMAPPED = ("lap", "place", "race timer")
SLOW = 2  # a bot run's seconds, as a multiple of the manifest's
NONE = "none"
LINE = re.compile(r"frame (\d+) read (\d+)((?: [a-z0-9_.]+=\S+)+)")
HEADER = """\
# Game state at the {route} route's checkpoints, read from guest RAM by tools/state_goldens.py:
# the checkpoint, the frame it was read at, then each kar_ram.json value. Not mapped: {unmapped}.
"""

State = dict  # field name to its value as text


def value_text(value: Optional[kar_ram.Value]) -> str:
    if value is None:
        return NONE
    if isinstance(value, float):
        return format(value, ".9g")
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


class Checkpoints:
    """A bot that presses nothing on PORTS and reads FIELDS at each of FRAMES. `states` maps each
    frame it read to the frame it read it at and the values, as text."""

    def __init__(self, frames: Sequence[int], ports: int, fields: Sequence[str] = FIELDS,
                 table: Optional[dict] = None) -> None:
        self.left = sorted(set(frames))
        self.ports = ports
        self.fields = list(fields)
        self.table = table if table is not None else kar_ram.load()
        self.states: dict[int, tuple[int, State]] = {}

    def __call__(self, link: Link) -> dict[int, Pad]:
        if self.left and link.frame >= self.left[0]:
            state = {f: value_text(kar_ram.read(link, f, self.table)) for f in self.fields}
            while self.left and self.left[0] <= link.frame:
                self.states[self.left.pop(0)] = (link.frame, state)
        return {port: Pad() for port in range(1, self.ports + 1)}


def route_pads(route: Route) -> int:
    pads = [int(s[len("--pads="):]) for s in route.extra if s.startswith("--pads=")]
    return pads[-1] if pads else 1


def run_settings(route: Route, aspect: str) -> list[str]:
    """The probe.sh settings a state run of ROUTE takes, all but --pads, which bot_link.run sets."""
    wide = [] if aspect == "4:3" else [f"--aspect={aspect}"]
    return [f"--exit-after={max(route.required) + route.dump_every}", *wide,
            *(s for s in route.extra if not s.startswith("--pads="))]


def play(route: Route, name: str, *, aspect: str = "4:3", every: Optional[int] = None,
         probe: Optional[Path] = None, settings: Sequence[str] = ()):
    """Play ROUTE as NAME from a blank memory card and read its checkpoints. EVERY is the dump
    interval, None for no dumps, and the run's directory stays for the caller. Returns the
    bot_link Outcome and the Checkpoints' states."""
    out = bot_link.run_directory(name, probe)
    if out.exists():
        remove_run(out)
    bot = Checkpoints(route.required, route_pads(route))
    outcome = bot_link.run(name, route.seconds * SLOW, bot, pads=bot.ports,
                           script=str(route_file(route.name)), every=every,
                           settings=[*run_settings(route, aspect), *settings], probe=probe)
    return outcome, bot.states


def format_golden(route: str, states: dict[int, tuple[int, State]]) -> str:
    lines = [f"frame {f} read {at} " + " ".join(f"{k}={v}" for k, v in state.items())
             for f, (at, state) in sorted(states.items())]
    return HEADER.format(route=route, unmapped=", ".join(UNMAPPED)) + "\n".join(lines) + "\n"


def parse_golden(text: str, where: str = "golden") -> dict[int, tuple[int, State]]:
    golden: dict[int, tuple[int, State]] = {}
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        m = LINE.fullmatch(line)
        if not m:
            raise ValueError(f"{where}: line {n}: not 'frame N read N FIELD=VALUE ...': {line!r}")
        golden[int(m[1])] = (int(m[2]), dict(p.split("=", 1) for p in m[3].split()))
    if not golden:
        raise ValueError(f"{where}: no checkpoints")
    return golden


def read_golden(path: Path) -> dict[int, tuple[int, State]]:
    return parse_golden(path.read_text(), str(path))


def compare(golden: dict[int, tuple[int, State]], got: dict[int, tuple[int, State]]) -> list[tuple[int, str, str]]:
    """What differs, as (checkpoint, field, what): a checkpoint not reached, read at another frame,
    or a field with another value. The field is "frame" for the first two."""
    problems = []
    for f, (at, want) in sorted(golden.items()):
        if f not in got:
            problems.append((f, "frame", "not reached"))
            continue
        read_at, state = got[f]
        if read_at != at:
            problems.append((f, "frame", f"read at {read_at}, golden at {at}"))
        for field, value in want.items():
            now = state.get(field, NONE)
            if now != value:
                problems.append((f, field, f"{now} != golden {value}"))
    return problems


def ended_badly(outcome: bot_link.Outcome) -> Optional[str]:
    """Why a run didn't end at its --exit-after, or None when it did."""
    if outcome.reason == bot_link.EXIT_AFTER:
        return None
    return f"the run ended on {outcome.reason}: {outcome.detail}"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["check", "record"])
    ap.add_argument("routes", nargs="*")
    ap.add_argument("--aspect", choices=["4:3", "16:9"], default="4:3",
                    help="the picture's aspect, and so which goldens (default 4:3)")
    args = ap.parse_args(argv)
    try:
        routes = select_routes(args.routes, MANIFEST)
        paths = {r.name: HASHES / STATES[args.aspect] / f"{r.name}.txt" for r in routes}
        goldens = {r.name: read_golden(paths[r.name]) for r in routes} if args.mode == "check" else {}
        failed = 0
        for route in routes:
            outcome, states = play(route, f"state-{route.name}", aspect=args.aspect)
            remove_run(outcome.run_dir)
            if outcome.reason == bot_link.NEVER_LINKED:
                raise ValueError(f"{route.name}: the game never connected: {outcome.detail}")
            bad = ended_badly(outcome)
            if args.mode == "record":
                missing = [f for f in route.required if f not in states]
                if missing or bad:
                    print(f"{route.name}: not recorded, " + (bad or f"didn't reach {missing}"))
                    failed += 1
                    continue
                paths[route.name].parent.mkdir(parents=True, exist_ok=True)
                paths[route.name].write_text(format_golden(route.name, states))
                print(f"{route.name}: recorded {len(states)} checkpoints")
                continue
            problems = [f"frame {f}: {field}: {what}" for f, field, what in compare(goldens[route.name], states)]
            problems += [bad] if bad else []
            if problems:
                print(f"{route.name}: played differently, {len(problems)} problem(s)")
                for p in problems:
                    print(f"  {p}")
                failed += 1
            else:
                print(f"{route.name}: OK, {len(states)} checkpoints match")
    except (OSError, ValueError, bot_link.LinkSetupError) as e:
        print(e, file=sys.stderr)
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
