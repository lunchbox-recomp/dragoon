#!/usr/bin/env python3
"""Which of the pad's controls reached the game in a playtest, and on which port?

Usage: pad_report.py DIR

DIR is a playtest session from tools/playtest.sh, with its input log in DIR/inputs/, or an
input log's own directory, such as one in saves/inputs/. Reads the log's inputs.txt and, in
a session, the gamepad lines of stdout.txt.

For each port the game saw plugged in, it prints the gamepads gcn-recomp put on it and took
off it. Under each go gcn-recomp's own lines about the port, which give its type and labels
as it landed, and what it sent and how its rumble went as it left or the game quit. Then
each button in the order it was first pressed with how many times, how far each stick went
from the middle and which of its eight directions it reached, and each trigger's highest
value with how many levels it took. A trigger that only ever read 255 was on or off. Then
how often and how long the game ran the rumble motor, from a log of version 5 or later. Last
come the pad's controls nobody used on that port, where a stick counts once it reaches a
direction.

Times are the game's frames, with minutes and seconds at 60 frames a second. A gamepad line
is placed after the last frame stdout.txt timed before it. A run-N directory, made when the
game reset the console, reads its own part of the session's stdout.txt. Port 1 also takes
the keyboard, so its presses may be keys.

Exits 0 once it has read the log, 2 on a bad argument or a log it can't read, that's older
than version 2 or that holds no pad state.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import session_log
from frametime import FT

# The GameCube pad's buttons and their bits in the log (hw/pad.h in gcn-recomp).
BUTTONS = [("A", 0x0100), ("B", 0x0200), ("X", 0x0400), ("Y", 0x0800), ("Z", 0x0010),
           ("L", 0x0040), ("R", 0x0020), ("Start", 0x1000),
           ("Up", 0x0008), ("Down", 0x0004), ("Left", 0x0001), ("Right", 0x0002)]
# Clockwise from up, as direction() numbers them.
DIRECTIONS = ["up", "up-right", "right", "down-right", "down", "down-left", "left", "up-left"]
# How far from the middle a stick must go to reach a direction: half of the 100 that a
# gamepad's stick pushed all the way gives (gamepads.cpp).
REACH = 50
FRAMES_PER_SECOND = 60

VERSION = re.compile(r"^# gcn-recomp input log v(\d+)")
END = re.compile(r"^# end (\d+) (\d+)")
MOTOR = re.compile(r"^motor \d+ (\d+) (\d+) ([01])$")
GAMEPAD = re.compile(r'^gamepads: "(.*)" (on|pulled out of) port (\d)$')
LEFT_OUT = re.compile(r'^gamepads: "(.*)" left out: no port is free$')
SAID = re.compile(r"^gamepads: port (\d) (.+)$")


def direction(dx: int, dy: int) -> int | None:
    """The DIRECTIONS index of a stick `dx` right and `dy` up of the middle, or None short of REACH."""
    if math.hypot(dx, dy) < REACH:
        return None
    return round(math.atan2(dx, dy) / (math.pi / 4)) % 8


@dataclass
class Stick:
    low: list[int] = field(default_factory=lambda: [0, 0])  # x, y, from the middle
    high: list[int] = field(default_factory=lambda: [0, 0])
    reached: set[int] = field(default_factory=set)

    def add(self, x: int, y: int) -> None:
        for i, v in enumerate((x - 0x80, y - 0x80)):
            self.low[i] = min(self.low[i], v)
            self.high[i] = max(self.high[i], v)
        d = direction(x - 0x80, y - 0x80)
        if d is not None:
            self.reached.add(d)


@dataclass
class Port:
    plugged: list[tuple[int, bool]] = field(default_factory=list)  # frame and state, at each change
    presses: dict[str, list[int]] = field(default_factory=dict)  # frames, in the order first pressed
    stick: Stick = field(default_factory=Stick)
    cstick: Stick = field(default_factory=Stick)
    levels: dict[str, set[int]] = field(default_factory=lambda: {"L": set(), "R": set()})
    motor: list[tuple[int, bool]] = field(default_factory=list)  # frame and state, at each change


def parse(lines) -> tuple[dict[int, Port], int | None, int | None]:
    """The ports by channel (0 for port 1), the frame the run ended at and the log's version,
    each if the log says."""
    ports: dict[int, Port] = {}
    held: dict[int, int] = {}
    end = version = None
    for n, raw in enumerate(lines, 1):
        line = raw.strip()
        if m := VERSION.match(line):
            version = int(m[1])
            if version < 2:
                raise ValueError(f"version {version} log; this reads version 2 and later")
            continue
        if m := END.match(line):
            end = int(m[2])
            continue
        if m := MOTOR.match(line):
            ports.setdefault(int(m[2]), Port()).motor.append((int(m[1]), m[3] == "1"))
            continue
        if not line or line.startswith(("#", "jump ", "pose ")):
            continue
        f = line.split()
        try:
            if len(f) != 11:
                raise ValueError
            frame, chan, plugged = int(f[1]), int(f[2]), int(f[3]) != 0
            buttons, sx, sy, cx, cy, tl, tr = (int(v, 16) for v in f[4:])
        except ValueError:
            raise ValueError(f"line {n} is not a pad state: {line}") from None
        port = ports.setdefault(chan, Port())
        if not port.plugged or port.plugged[-1][1] != plugged:
            port.plugged.append((frame, plugged))
        pressed = buttons & ~held.get(chan, 0)
        held[chan] = buttons
        for name, bit in BUTTONS:
            if pressed & bit:
                port.presses.setdefault(name, []).append(frame)
        port.stick.add(sx, sy)
        port.cstick.add(cx, cy)
        for name, level in (("L", tl), ("R", tr)):
            if level:
                port.levels[name].add(level)
    return ports, end, version


def gamepad_lines(lines) -> tuple[dict[int, list[tuple[int | None, str, bool]]], list[str]]:
    """Each port's (0 for port 1) events, as (the frame timed last before, what was said,
    whether it's timed): its gamepads coming and going are, and what gcn-recomp said of the
    port between them isn't. Also the names of the gamepads no port was free for."""
    frame = None
    events: dict[int, list[tuple[int | None, str, bool]]] = {}
    left_out = []
    for raw in lines:
        line = raw.rstrip("\n")
        if m := FT.match(line):
            frame = int(m[1])
        elif m := GAMEPAD.match(line):
            what = "on" if m[2] == "on" else "pulled out"
            events.setdefault(int(m[3]) - 1, []).append((frame, f'gamepad "{m[1]}" {what}', True))
        elif m := SAID.match(line):
            events.setdefault(int(m[1]) - 1, []).append((frame, m[2], False))
        elif m := LEFT_OUT.match(line):
            left_out.append(m[1])
    return events, left_out


def when(frame: int) -> str:
    tenths = round(frame * 10 / FRAMES_PER_SECOND)
    return f"frame {frame} ({tenths // 600}:{tenths % 600 / 10:04.1f})"


def stick_line(name: str, s: Stick) -> str:
    if not s.reached:
        return f"  {name:8} x {s.low[0]:+d} to {s.high[0]:+d}, y {s.low[1]:+d} to {s.high[1]:+d}, no direction"
    which = ", ".join(DIRECTIONS[d] for d in sorted(s.reached))
    return (f"  {name:8} x {s.low[0]:+d} to {s.high[0]:+d}, y {s.low[1]:+d} to {s.high[1]:+d},"
            f" {len(s.reached)} of 8 directions: {which}")


def event_lines(events: list[tuple[int | None, str, bool]]) -> list[str]:
    """A timed event says when, and what was said of the port goes under it. The same thing
    said again straight after is counted rather than repeated."""
    shown: list[list] = []
    for frame, text, timed in events:
        if timed:
            line = f"  {text} {'before the first timed frame' if frame is None else f'after {when(frame)}'}"
        else:
            line = f"    {text}"
        if not timed and shown and shown[-1][0] == line:
            shown[-1][1] += 1
        else:
            shown.append([line, 1])
    return [line if n == 1 else f"{line} ({n} times)" for line, n in shown]


def rumble_line(port: Port, end: int | None, version: int | None) -> str:
    if version is None or version < 5:
        return "  rumble   not in the log, which is older than version 5"
    starts = [frame for frame, on in port.motor if on]
    if not starts:
        return "  rumble   never run by the game"
    frames, since = 0, None
    for frame, on in port.motor:
        if on:
            since = frame
        elif since is not None:
            frames += frame - since
            since = None
    still_on = since is not None and end is None
    if since is not None and end is not None:
        frames += end - since
    return (f"  rumble   run by the game {len(starts)} time{'s' if len(starts) > 1 else ''},"
            f" {'at least ' if still_on else ''}{frames / FRAMES_PER_SECOND:.1f} s in all,"
            f" first at {when(starts[0])}{', still on when the log ends' if still_on else ''}")


def report(ports: dict[int, Port], end: int | None, version: int | None, events,
           left_out: list[str]) -> list[str]:
    out = [f"the log ends at {when(end)}" if end is not None else "the log has no end line"]
    unplugged = []
    for chan in sorted(ports):
        port = ports[chan]
        if not any(on for _, on in port.plugged):
            unplugged.append(str(chan + 1))
            continue
        out.append(f"port {chan + 1}")
        out += event_lines(events.get(chan, []))
        out.append("  " + ", ".join(f"{'plugged in' if on else 'unplugged'} at {when(f)}" for f, on in port.plugged))
        out.append("  buttons, in the order first pressed:" if port.presses else "  no button pressed")
        for name, frames in port.presses.items():
            out.append(f"    {name:6} {len(frames):4} from {when(frames[0])}")
        out.append(stick_line("stick", port.stick))
        out.append(stick_line("c-stick", port.cstick))
        for name, levels in port.levels.items():
            if levels:
                kind = "on or off" if levels == {255} else f"{len(levels)} level{'s' if len(levels) > 1 else ''}"
                out.append(f"  {name:8} trigger up to {max(levels)}, {kind}")
            else:
                out.append(f"  {name:8} trigger never moved")
        out.append(rumble_line(port, end, version))
        unused = [name for name, _ in BUTTONS if name not in port.presses]
        unused += [name for name, s in (("stick", port.stick), ("c-stick", port.cstick)) if not s.reached]
        unused += [f"{name} trigger" for name, levels in port.levels.items() if not levels]
        out.append(f"  never used: {', '.join(unused)}" if unused else "  every control used")
    if unplugged:
        out.append(f"never plugged in: port{'s' if len(unplugged) > 1 else ''} {', '.join(unplugged)}")
    for name in left_out:
        out.append(f"gamepad \"{name}\" left out: no port was free")
    return out


def log_path(directory: Path) -> Path:
    for path in (directory / "inputs.txt", directory / "inputs" / "inputs.txt"):
        if path.is_file():
            return path
    raise ValueError(f"{directory}: no inputs.txt, nor inputs/inputs.txt")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", type=Path)
    args = ap.parse_args(argv)
    try:
        path = log_path(args.dir)
        with path.open(encoding="utf-8") as f:
            try:
                ports, end, version = parse(f)
            except ValueError as e:
                raise ValueError(f"{path}: {e}") from None
        if not ports:
            raise ValueError(f"{path}: no pad state")
        events, left_out = {}, []
        if found := session_log.run_lines(args.dir):
            events, left_out = gamepad_lines(found[0])
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    print("\n".join(report(ports, end, version, events, left_out)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
