#!/usr/bin/env python3
"""Which functions change a route when the interpreter runs them? Bisect the function starts.

Usage: interp_bisect.py ROUTE --slow=N [--frames|--audio]

Reads every function start from analysis/symbols.txt and checks ROUTE with
tools/frame_hashes.py, or with tools/audio_hashes.py under --audio, passing --slow=N on. Each
check sets GCN_INTERPRET to a list of starts, a file in build/bisect/ with one hex address a
line, named by its absolute path. ROUTE has to match with nothing interpreted and change with
every function listed. From there the list is halved and a half that changes the route is
followed, and the functions not yet cleared are checked once more in case others change it too.

It prints each function that changes ROUTE on its own with its name, and writes them to
build/bisect/ROUTE-KIND-found.txt, where KIND is frames or audio. Each check takes ROUTE's
seconds times N. One function takes about log2 of the function count in checks.

Exits 0 when interpreting every function leaves ROUTE matching, 1 when it names the functions
that change it, 2 on a bad argument, a hash tool that couldn't run, a ROUTE that changes with
nothing interpreted or a change that no single function reproduces.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from probe_dirs import slow_factor
from routes import MANIFEST, select_routes

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ROOT / "analysis" / "symbols.txt"
BISECT = ROOT / "build" / "bisect"
TOOLS = {"frames": ROOT / "tools" / "frame_hashes.py", "audio": ROOT / "tools" / "audio_hashes.py"}
SYMBOL = re.compile(r"(\S+) = \S+:0x([0-9A-Fa-f]{1,8}); // (.*)")


def read_starts(path: Path) -> list[tuple[int, str]]:
    """Where each function in the symbols file PATH starts, with its name, in address order. A
    line that isn't a symbol is a ValueError that names it, and so is a file with no functions."""
    names: dict[int, str] = {}
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        m = SYMBOL.fullmatch(line)
        if not m:
            raise ValueError(f"{path}: line {n}: not a symbol: {line!r}")
        if "type:function" in m[3].split():
            names.setdefault(int(m[2], 16), m[1])
    if not names:
        raise ValueError(f"{path}: no functions")
    return sorted(names.items())


def list_text(addrs: list[int]) -> str:
    """The text of a GCN_INTERPRET list: one hex address a line."""
    return "".join(f"{a:08X}\n" for a in addrs)


def narrow(funcs: list[int], fails: Callable[[list[int]], bool]) -> list[int]:
    """The functions of FUNCS that change the route on their own, in address order.

    FUNCS as a whole changes it, and so does any list holding one of those functions. FAILS runs
    a list and says whether it changes the route. Halving finds one function in about log2 of
    the length of FUNCS in runs. Each time it follows the left half, the right half is left
    unrun. After a function is found, all the halves left unrun are checked in one run, and the
    search goes on in them only if they change the route too.
    """
    found: list[int] = []
    while True:
        group, rest = funcs, []
        while len(group) > 1:
            half = len(group) // 2
            left, right = group[:half], group[half:]
            if fails(left):
                group, rest = left, right + rest
            else:
                group = right  # the left half is clear, so the change is in this one
        found += group
        if not rest or not fails(rest):
            return found
        funcs = rest


class Checks:
    """The hash tool's check of one route, run for each list of functions."""

    def __init__(self, tool: Path, route: str, slow: int, stem: str) -> None:
        self.tool, self.route, self.slow, self.stem = tool, route, slow, stem
        self.count = 0
        self.known: dict[tuple[int, ...], bool] = {}

    def check(self, addrs: list[int] | None) -> bool:
        """Run the hash tool once with GCN_INTERPRET naming a new list of ADDRS, or not set for
        None. True when the route changes. A run that isn't a pass or a fail is a ValueError."""
        self.count += 1
        env = {k: v for k, v in os.environ.items() if k != "GCN_INTERPRET"}
        if addrs is None:
            what = "nothing interpreted"
        else:
            listing = (BISECT / f"{self.stem}-{self.count:02d}.txt").absolute()
            listing.write_text(list_text(addrs))
            env["GCN_INTERPRET"] = str(listing)
            what = f"{len(addrs)} functions in {listing.name}"
        began = time.monotonic()
        code = subprocess.run([sys.executable, str(self.tool), "check", self.route, f"--slow={self.slow}"],
                              env=env, stdout=subprocess.DEVNULL).returncode
        if code not in (0, 1):
            raise ValueError(f"{self.tool.name} exited {code} on run {self.count}, with {what}")
        print(f"run {self.count}, {what}: {'changes' if code else 'matches'} {self.route} "
              f"({time.monotonic() - began:.0f} s)", flush=True)
        return code == 1

    def changes(self, addrs: list[int]) -> bool:
        """Whether interpreting ADDRS changes the route, run once however often it's asked."""
        key = tuple(addrs)
        if key not in self.known:
            self.known[key] = self.check(addrs)
        return self.known[key]


def bisect(route: str, slow: int, kind: str, starts: list[tuple[int, str]]) -> int:
    addrs = [a for a, _ in starts]
    names = dict(starts)
    stem = f"{route}-{kind}"
    BISECT.mkdir(parents=True, exist_ok=True)
    for old in list(BISECT.iterdir()):
        if re.fullmatch(re.escape(stem) + r"-(\d+|found)\.txt", old.name):
            old.unlink()  # an earlier bisect's lists
    checks = Checks(TOOLS[kind], route, slow, stem)
    if checks.check(None):
        raise ValueError(f"{route} changes with nothing interpreted, so there's nothing to bisect")
    if not checks.changes(addrs):
        print(f"Interpreting all {len(addrs)} functions leaves {route} matching, so none of them changes it.")
        return 0
    found = narrow(addrs, checks.changes)
    listing = (BISECT / f"{stem}-found.txt").absolute()
    listing.write_text(list_text(found))
    if not checks.changes(found):
        raise ValueError(f"Interpreting only the functions found leaves {route} matching, so the "
                         f"change takes a mix of them and others. They're listed in {listing}.")
    print(f"Functions that change {route} when interpreted alone ({len(found)}), listed in {listing}.")
    for a in found:
        print(f"  {a:08X}  {names[a]}")
    return 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("route")
    ap.add_argument("--slow", required=True, metavar="N",
                    help="give each check N times the route's seconds, a whole number from 1")
    kind = ap.add_mutually_exclusive_group()
    kind.add_argument("--frames", action="store_true", help="check frames with frame_hashes.py (the default)")
    kind.add_argument("--audio", action="store_true", help="check audio with audio_hashes.py")
    args = ap.parse_args(argv)
    try:
        slow = slow_factor(args.slow)
        select_routes([args.route], MANIFEST)
        starts = read_starts(SYMBOLS)
        return bisect(args.route, slow, "audio" if args.audio else "frames", starts)
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
