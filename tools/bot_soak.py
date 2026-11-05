#!/usr/bin/env python3
"""Play the game with bots until something breaks, and keep the replay that shows it.

Usage: bot_soak.py [--seed N] [--minutes M] [--modes LIST] [--ports N] [--round SECONDS]
                   [--stuck SECONDS] [--hang SECONDS] [-- SETTING ...]

Plays the game through bot_link.py for M minutes of wall time (10 by default) as a new run in
build/probe/soak-sSEED-TIME/, with GCN_AXVOICES=1 and every SETTING after `--`, and no frame
dumps. The bots walk the menus (bot_menus.py) and play the rounds LIST names, a comma-separated
list of air-ride, top-ride and city-trial (all three by default), with PORTS controllers (1 by
default). In a race or the city each bot holds the stick toward wherever a walk from SEED says
and taps A at random, and never presses START (bot_walk.py). The walker leaves an Air Ride or
Top Ride race, or a City Trial stadium, through the pause menu after SECONDS of game time
(--round, 120 by default). SEED is a whole number from 0, which is printed and defaults to one
made from the clock. --minutes is at most a week, and --round, --stuck and --hang are at most a
day.

It stops at the first of these:

  the game exits, shuts itself down, panics or is stopped by the engine
  the game sends no frame, or no answer to a read, for --hang seconds of wall time (30 by default)
  the picture's hash stays the same for 10 s of game time while the race bots' input changes
  a music stream ends early (stream_voices.py's rule, on the run's [axv] lines)
  a menu screen stays up for --stuck seconds of game time (120 by default, 30 at least), or a race or the
  city for 600 (a minute past --round when that's more), or the menus go on for five times
  --stuck with no race or city

The frozen-picture check needs a picture hash, which the link doesn't give, so it doesn't run, and
the soak says so. A stop keeps the run's input log, writes bot.json beside it with the seed, the
arguments, the Dragoon and engine commits and how the run stopped, and prints the probe.sh line
that plays the input log back. bot.json says when the stop came after a console reset, since a
replay plays only the process after the last reset, from the card as it stood then. A restart
rebuilds the shader cache before the bot connects again, and that counts against the hang limit.
The first reset's `[shaders] ... in Z ms` line is kept, a Z near the limit is warned about when
it comes, and --hang raises the limit for the next run.

Exits 0 when the run ended with no stop, at its time limit or at an --exit-after given after
`--`, 1 when it stopped, and 2 on a bad argument or when it couldn't run or be judged: the game
never connected, or a bot raised an error.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Callable, Optional

import bot_link
import bot_menus
import bot_record
from bot_player import Player, count
from bot_stop import HANG, SoakError, Stop, classify, near_hang
from bot_watch import Detected, Frozen, LogWatch, Picture, engine_picture

MINUTES = 10
HANG_SECONDS = 30
SEED_RANGE = 1_000_000
SOAK_SETTINGS = ["GCN_AXVOICES=1"]  # what the soak sets before the user's settings
# The menus are cut off at five times --stuck, and a first walk from the boot to a race takes up to
# about 72 s, so a --stuck much under this one could stop a healthy run.
STUCK_FLOOR = 30
# The most each time may be, which keeps round(seconds * FPS) and the like finite. Each is the
# number and the unit it's given in.
CEILINGS = {"minutes": (7 * 24 * 60, "minutes (a week)"), "round": (24 * 60 * 60, "seconds (a day)"),
            "stuck": (24 * 60 * 60, "seconds (a day)"), "hang": (24 * 60 * 60, "seconds (a day)")}


def modes_arg(text: str) -> list[str]:
    modes = text.split(",")
    for mode in modes:
        if mode not in bot_menus.MODE_CURSOR:
            raise argparse.ArgumentTypeError(f"{mode!r} isn't one of {', '.join(bot_menus.MODE_CURSOR)}")
    if len(set(modes)) != len(modes):
        raise argparse.ArgumentTypeError(f"{text!r} names a mode twice")
    return modes


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="bot_soak.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, metavar="N")
    ap.add_argument("--minutes", type=float, default=MINUTES, metavar="M")
    ap.add_argument("--modes", type=modes_arg, default=list(bot_menus.MODE_CURSOR), metavar="LIST")
    ap.add_argument("--ports", type=int, choices=range(1, 5), default=1, metavar="N")
    ap.add_argument("--round", type=float, default=bot_menus.ROUND_SECONDS, metavar="SECONDS")
    ap.add_argument("--stuck", type=float, default=bot_menus.STUCK_SECONDS, metavar="SECONDS")
    ap.add_argument("--hang", type=float, default=HANG_SECONDS, metavar="SECONDS")
    ap.add_argument("--probe", help=argparse.SUPPRESS)
    return ap


def checked(ap: argparse.ArgumentParser, args: argparse.Namespace, clock: Callable[[], float]) -> None:
    """Fills in the seed and refuses a number the run would refuse."""
    if args.seed is None:
        args.seed = int(clock()) % SEED_RANGE
    if args.seed < 0:
        ap.error("--seed is a whole number from 0")
    for name, (ceiling, unit) in CEILINGS.items():
        if not 0 < getattr(args, name) < math.inf:  # nan fails both
            ap.error(f"--{name} is a finite number above 0")
        if getattr(args, name) > ceiling:
            ap.error(f"--{name} is at most {ceiling} {unit}")
    if args.stuck < STUCK_FLOOR:
        ap.error(f"--stuck is at least {STUCK_FLOOR} seconds")


def say(text: str) -> None:
    print(text, flush=True)


def complain(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def soak(args: argparse.Namespace, settings: list[str], *, picture: Picture = engine_picture,
         out: Callable[[str], None] = say, err: Callable[[str], None] = complain,
         clock: Callable[[], float] = time.time, run=bot_link.run) -> int:
    """Plays the soak ARGS names and returns the exit code. PICTURE gives the frozen-picture check
    its hash, which the engine doesn't give, and OUT and ERR take the lines to print."""
    probe = Path(os.path.abspath(args.probe if args.probe is not None else bot_link.PROBE))
    name = bot_record.new_name(args.seed, clock(), lambda n: bot_link.run_directory(n, probe).exists())
    run_dir = bot_link.run_directory(name, probe)
    seconds = max(1, round(args.minutes * 60))

    def shaders(line: str, ms: int) -> None:
        out(f"the first reset: {line}")
        if near_hang(ms, args.hang):
            out(f"that is a good part of the {args.hang:g} s hang limit, and a hang after it may be only that "
                "rebuild; run again with a higher --hang")

    log = LogWatch(run_dir / "stdout.txt", shaders)
    frozen = Frozen(picture)
    player = Player(args.seed, args.ports, args.modes, round_seconds=args.round, stuck_seconds=args.stuck,
                    frozen=frozen, log=log, say=out)
    out(f"{name}: seed {args.seed}, {args.minutes:g} min, modes {','.join(args.modes)}, "
        f"{count(args.ports, 'port')}, round {args.round:g} s, stuck {args.stuck:g} s, hang {args.hang:g} s")
    began = time.monotonic()
    try:
        outcome = run(name, seconds, player, pads=args.ports, every=None, settings=[*SOAK_SETTINGS, *settings],
                      hang=args.hang, probe=probe)
    except (ValueError, bot_link.LinkSetupError) as e:
        err(f"bot_soak.py: {e}")
        return 2
    except KeyboardInterrupt:
        err(f"bot_soak.py: interrupted; the run is in {run_dir}")
        return 2
    wall = time.monotonic() - began
    late: Optional[Detected] = None
    try:
        log.finish(outcome.last_frame or 0)
    except Detected as e:
        late = e
    try:
        stop = classify(outcome, log.resets, args.hang, late=late)
    except SoakError as e:
        err(f"bot_soak.py: {e}")
        if outcome.error is not None:
            err("".join(traceback.format_exception(type(outcome.error), outcome.error, outcome.error.__traceback__)))
        return 2
    watched = {"picture_hashes": frozen.hashes > 0, "axv_lines": log.axv}
    if not watched["picture_hashes"]:
        out("the frozen-picture check saw no picture hash, so it did not run; the engine gives a bot none")
    if not watched["axv_lines"]:
        out("the music check saw no [axv] lines, so it did not run; was GCN_AXVOICES=1 turned off?")
    if stop is None:
        out(f"{name}: no stop in {wall / 60:.1f} min ({count(outcome.frames, 'frame')}, "
            f"{count(player.menus.rounds, 'round')}, {count(log.resets.count, 'console reset')}), "
            f"ended on {outcome.reason}")
        return 0
    report(stop, outcome, probe=probe, name=name, args=args, settings=settings, resets=log.resets,
           watched=watched, wall=wall, out=out)
    return 1


def report(stop: Stop, outcome: bot_link.Outcome, *, probe: Path, name: str, args: argparse.Namespace,
           settings: list[str], resets, watched: dict[str, bool], wall: float,
           out: Callable[[str], None]) -> None:
    """Writes bot.json beside the stop's input log and prints the stop and the replay line. The
    log is the last process's, unless a console reset came after the stop, and then it's the
    process the stop was in."""
    frame = stop.frame
    log = bot_link.session_inputs(outcome.run_dir, stop.session) if stop.before_reset else outcome.input_log
    replay = None
    if log is not None:
        # The last frame sent before a hang is not one a replay is known to reach, so it isn't a stopping point.
        # A stop with a reset after it has no frame of its own, so its replay runs to where its process ended.
        until = bot_link.ended_at(log) if stop.before_reset else frame
        replay = bot_record.replay_line(probe, name, log, until, [*SOAK_SETTINGS, *settings],
                                        exit_after=stop.kind != HANG, pads=args.ports)
    arguments = {"seed": args.seed, "minutes": args.minutes, "modes": args.modes, "ports": args.ports,
                 "round_seconds": args.round, "stuck_seconds": args.stuck, "hang": args.hang,
                 "settings": settings}
    commit_ids = {**bot_record.commits(probe.parent.parent),
                  "engine_built": bot_record.built_engine(log.parent) if log is not None else None}
    data = bot_record.record(name=name, seed=args.seed, arguments=arguments,
                             commit_ids=commit_ids, stop=stop, resets=resets,
                             input_log=log, replay=replay, frames=outcome.frames, wall_seconds=wall,
                             watched=watched)
    path = bot_record.write(log.parent if log is not None else outcome.run_dir, data)
    out(f"STOP {stop.kind}: {stop.detail}")
    out(f"  run {outcome.run_dir}")
    if frame is not None:
        out(f"  at frame {frame}, {frame / 60:.1f} s of game time, after {wall:.0f} s of wall time")
    else:
        out(f"  {wall:.0f} s of wall time")
    if stop.after_reset:
        out(f"  after {count(stop.resets_before, 'console reset')}; a replay starts from the card as it stood at "
            "the last reset")
    if stop.before_reset:
        out("  a console reset came after it, so the last process's replay can't show it; "
            + ("the input log and replay below are for the process it happened in" if log is not None
               else "the process it happened in kept no input log"))
    if log is not None:
        out(f"  input log {log}")
    out(f"  {path}")
    out(f"  replay: {replay}" if replay else "  no input log to replay")


def main(argv: list[str]) -> int:
    argv, settings = bot_link.split_settings(argv)
    ap = parser()
    args = ap.parse_args(argv)
    checked(ap, args, time.time)
    return soak(args, settings)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
