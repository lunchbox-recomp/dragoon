#!/usr/bin/env python3
"""What does guest RAM hold at the frames I name, along a route?

Usage: ram_peek.py --at FRAMES [--script ROUTE] [--pads N] [--every N] [--hang SECONDS]
                   [--table PATH] NAME SECONDS ITEM ... [-- SETTING ...]

Plays the game through bot_link.py as NAME for up to SECONDS with a bot that presses nothing on
ports 1 to N, so ROUTE's presses are the only ones. At each frame in FRAMES it reads every ITEM
and prints one line, `frame N` and then ITEM=VALUE for each. The engine's frame numbers can
jump, so a frame is read at the first one the engine steps the bot at that's as late or later,
and the line names that frame.

NAME has to be new. A run in a build/probe/NAME/ an earlier run left starts from that run's
memory card, and every route starts from a blank one, so such a NAME is refused.

FRAMES is a comma-separated list of frames and of ranges, A-B for every frame from A to B and
A-B/S for every Sth. An ITEM is one of these:
  ENTRY       a name in kar_ram.json (or the --table one), its value and, when the table says
              what that value means, the meaning in brackets
  ADDR:LEN    LEN bytes at ADDR (hex address, decimal length up to 256), in hex
  ADDR:TYPE   a value of TYPE at ADDR, TYPE being u8, s8, u16, s16, u32, s32 or f32, and
              ADDR:TYPExN for N of them one after the other, comma-separated
ADDR may go on with /OFF for each pointer to follow, as kar_ram.json's paths do. 8055AA2C/2C/300
reads the pointer at 8055AA2C, then the pointer at 2C past it, and reads the value at 300 past
that. A value behind a null pointer prints as none.

ROUTE, --pads, --hang and the SETTINGs are bot_link.py's. The run dumps no frames unless
--every N asks for every Nth, as bot_link.py's --every does. The run's end is printed after the
lines, as bot_link.py prints it, with a line naming the frames the run never reached.

Exits 0 when the run ended as a bot run is meant to and every frame was read, 1 when it ended
any other way or a frame wasn't reached, and 2 on a bad argument, a NAME that isn't new, an
unknown name, a table that won't load or a game that never connected.
"""
from __future__ import annotations

import argparse
import re
import struct
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TextIO

import bot_link
import kar_ram
from bot_link import Link, Pad

RAW = re.compile(r"([0-9a-fA-F]{1,8})((?:/[0-9a-fA-F]{1,4})*):(?:(\d{1,3})|([a-z0-9]+?)(?:x(\d{1,3}))?)")
RANGE = re.compile(r"(\d+)(?:-(\d+)(?:/(\d+))?)?")
NONE = "none"


@dataclass(frozen=True)
class Item:
    label: str
    address: int
    path: tuple[int, ...]
    length: int
    show: Callable[[bytes], str]


def parse_frames(text: str) -> list[int]:
    """The frames TEXT lists, in order and once each. Raises ValueError for a bad one."""
    frames: set[int] = set()
    for part in text.split(","):
        m = RANGE.fullmatch(part)
        if not m:
            raise ValueError(f"{part!r} isn't a frame, A-B or A-B/S")
        first = int(m[1])
        last = int(m[2]) if m[2] is not None else first
        step = int(m[3]) if m[3] is not None else 1
        if last < first or step < 1:
            raise ValueError(f"{part!r} runs backwards or has a step under 1")
        frames.update(range(first, last + 1, step))
    return sorted(frames)


def _number(type_: str, value: int | float) -> str:
    return format(value, ".7g") if type_ == "f32" else str(value)


def _entry_item(entry: kar_ram.Entry) -> Item:
    def show(data: bytes) -> str:
        value = kar_ram.decode(entry, data)
        if isinstance(value, bytes):
            return value.hex()
        meaning = entry.meaning(value)
        text = _number(entry.type, value)
        return f"{text} ({meaning})" if meaning is not None else text
    return Item(entry.name, entry.address, entry.path, entry.length, show)


def _raw_item(text: str, address: int, path: tuple[int, ...], length: str | None, type_: str | None,
              count: str | None) -> Item:
    if length is not None:
        n = int(length)
        if not 1 <= n <= kar_ram.READ_MAX:
            raise ValueError(f"{text}: LEN is 1 to {kar_ram.READ_MAX}")
        return Item(text, address, path, n, lambda data: data.hex())
    if type_ not in kar_ram.FORMATS:
        raise ValueError(f"{text}: TYPE is one of {', '.join(kar_ram.FORMATS)}")
    each = kar_ram.size(type_)
    n = int(count) if count is not None else 1
    if not 1 <= n * each <= kar_ram.READ_MAX:
        raise ValueError(f"{text}: reads 1 to {kar_ram.READ_MAX} bytes")
    fmt = ">" + kar_ram.FORMATS[type_][1:] * n

    def show(data: bytes) -> str:
        return ",".join(_number(type_, v) for v in struct.unpack(fmt, data))
    return Item(text, address, path, n * each, show)


def parse_item(text: str, table: dict[str, kar_ram.Entry] | None) -> Item:
    """The Item TEXT names, an entry in TABLE or a raw ADDR[/OFF...]:LEN or ADDR[/OFF...]:TYPE[xN].
    Raises ValueError for one that's neither, or that starts outside main RAM."""
    m = RAW.fullmatch(text)
    if m:
        path = tuple(int(o, 16) for o in m[2].split("/")[1:])
        item = _raw_item(text, int(m[1], 16), path, m[3], m[4], m[5])
        if not kar_ram.in_ram(item.address, kar_ram.POINTER if path else item.length):
            raise ValueError(f"{text} isn't all in main RAM, {kar_ram.RAM_START:08X} to {kar_ram.RAM_END - 1:08X}")
        return item
    if table is None or text not in table:
        raise ValueError(f"{text}: not an ADDR:LEN, an ADDR:TYPE or a name in the table")
    return _entry_item(table[text])


def show(link: Link, item: Item) -> str:
    """ITEM's value now, as ram_peek.py prints it."""
    address = kar_ram.follow(link, item.address, item.path, item.length)
    return NONE if address is None else item.show(link.read(address, item.length))


class Sampler:
    """A bot that presses nothing on PORTS and, at each of FRAMES, reads ITEMS and prints a line
    to OUT."""

    def __init__(self, items: Sequence[Item], frames: Sequence[int], ports: int, out: TextIO) -> None:
        self.items = list(items)
        self.left = sorted(set(frames))
        self.ports = ports
        self.out = out

    def __call__(self, link: Link) -> dict[int, Pad]:
        if self.left and link.frame >= self.left[0]:
            values = [f"{item.label}={show(link, item)}" for item in self.items]
            print("  ".join([f"frame {link.frame}", *values]), file=self.out, flush=True)
            while self.left and self.left[0] <= link.frame:
                self.left.pop(0)
        return {port: Pad() for port in range(1, self.ports + 1)}


def main(argv: list[str]) -> int:
    argv, settings = bot_link.split_settings(argv)
    ap = argparse.ArgumentParser(prog="ram_peek.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--at", required=True, metavar="FRAMES")
    bot_link.add_play_arguments(ap)
    bot_link.add_run_arguments(ap, every=None)
    ap.add_argument("--table", metavar="PATH")
    ap.add_argument("name")
    ap.add_argument("seconds", type=int)
    ap.add_argument("items", nargs="+", metavar="ITEM")
    args = ap.parse_args(argv)
    options = bot_link.run_options(ap, args)
    try:
        frames = parse_frames(args.at)
    except ValueError as e:
        ap.error(f"--at: {e}")
    table = None
    if args.table is not None or not all(RAW.fullmatch(text) for text in args.items):
        try:
            table = kar_ram.load(args.table)
        except (OSError, ValueError) as e:
            print(f"ram_peek.py: {e}", file=sys.stderr)
            return 2
    try:
        items = [parse_item(text, table) for text in args.items]
    except ValueError as e:
        print(f"ram_peek.py: {e}", file=sys.stderr)
        return 2
    directory = bot_link.run_directory(args.name, args.probe)
    if directory.exists():
        print(f"ram_peek.py: {directory} is there already, and a run in it would start from its memory "
              "card, not the blank one the routes start from, so give the run a new NAME", file=sys.stderr)
        return 2
    sampler = Sampler(items, frames, args.pads, sys.stdout)
    try:
        outcome = bot_link.run(args.name, args.seconds, sampler, settings=settings, **options)
    except (ValueError, bot_link.LinkSetupError) as e:
        print(f"ram_peek.py: {e}", file=sys.stderr)
        return 2
    bot_link.print_outcome(outcome, "ram_peek.py")
    if outcome.reason == bot_link.NEVER_LINKED:
        return 2
    if sampler.left:
        print(f"  never reached {', '.join(map(str, sampler.left))}")
    return 0 if outcome.reason in bot_link.CLEAN and not sampler.left else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
