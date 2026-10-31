#!/usr/bin/env python3
"""Which functions change a route when the interpreter runs them? Bisect the function starts.

Usage: interp_bisect.py ROUTE --slow=N [--frames|--audio]

Reads every function start from analysis/symbols.txt and checks ROUTE with
tools/frame_hashes.py, or with tools/audio_hashes.py under --audio. Each check sets
GCN_INTERPRET to a list of starts, a file in build/bisect/ with one hex address a line, named by
its absolute path, and passes --slow=N on. The first check sets nothing and runs at ROUTE's own
seconds, since ROUTE has to match with nothing interpreted.

The bisect starts from the list of every function and halves it, following a half that changes
the route. When the left half doesn't change it, the change is taken to be in the right half
without a run, and a function reached that way is checked alone before it's accepted. Once one
is found, the functions not yet cleared are checked together and searched again if they change
ROUTE too.

It prints each function that changes ROUTE on its own with its name, and writes them to
build/bisect/ROUTE-KIND-found.txt, where KIND is frames or audio. Each check but the first takes
ROUTE's seconds times N. One function among the 20,003 starts in symbols.txt takes at most 19
checks, and each further one takes at most 18 more.

When the search ends on a function that doesn't change ROUTE alone, the change needs several
functions together, or a list ran too slowly to reach ROUTE's checkpoints. The shortest list
known to change ROUTE goes to build/bisect/ROUTE-KIND-smallest.txt, and any functions found
alone before that go to the found file.

A run that goes as expected prints one progress line and none of the hash tool's output. The
output goes to stderr when the first check changes ROUTE, when a check exits 2 and when the
functions found leave ROUTE matching together.

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


class Irreducible(ValueError):
    """A change that a search can't pin on one function. FOUND are the functions it had found to
    change the route alone, and SMALLEST the shortest list of the rest known to change it."""

    def __init__(self, found: list[int], smallest: list[int]) -> None:
        super().__init__(f"no single function reproduces the change in {len(smallest)} functions")
        self.found, self.smallest = found, smallest


def narrow(funcs: list[int], fails: Callable[[list[int]], bool]) -> list[int]:
    """The functions of FUNCS that change the route on their own, in address order.

    FUNCS as a whole changes it. FAILS runs a list and says whether it changes the route. The
    search halves FUNCS and follows the left half if it fails, which finds one function in about
    log2 of the length of FUNCS in runs.

    A left half that passes means the change is in the right half, which is taken as failing
    without a run. A function reached that way is run alone, and if it passes the search stops
    with Irreducible, since the change then needs several functions together or a list that ran
    too slowly. After a function is found, the halves left unrun are checked in one run, and the
    search goes on in them only if they fail too.
    """
    found: list[int] = []
    while True:
        group, rest, smallest, ran = funcs, [], funcs, True
        while len(group) > 1:
            half = len(group) // 2
            left, right = group[:half], group[half:]
            if fails(left):
                group, rest, smallest, ran = left, right + rest, left, True
            else:
                group, ran = right, False  # the left half is clear, so the change should be in this one
        if not ran and not fails(group):
            raise Irreducible(found, smallest)
        found += group
        if not rest or not fails(rest):
            return found
        funcs = rest


def write_list(stem: str, name: str, addrs: list[int]) -> Path:
    """Write ADDRS to build/bisect/STEM-NAME.txt and return its absolute path."""
    path = (BISECT / f"{stem}-{name}.txt").absolute()
    path.write_text(list_text(addrs))
    return path


class Checks:
    """The hash tool's check of one route, run for each list of functions. OUTPUT is what the
    latest run printed, kept for show_output."""

    def __init__(self, tool: Path, route: str, slow: int, stem: str) -> None:
        self.tool, self.route, self.slow, self.stem = tool, route, slow, stem
        self.count = 0
        self.output = ""
        self.known: dict[tuple[int, ...], bool] = {}

    def show_output(self) -> None:
        """Print what the latest run's hash tool printed to stderr, to explain an error."""
        if self.output:
            print(f"{self.tool.name} printed this on run {self.count}:", file=sys.stderr)
            print(self.output, end="", file=sys.stderr)

    def check(self, addrs: list[int] | None) -> bool:
        """Run the hash tool once with GCN_INTERPRET naming a new list of ADDRS, or not set for
        None. True when the route changes. A run that isn't a pass or a fail shows what the tool
        printed and is a ValueError."""
        self.count += 1
        env = {k: v for k, v in os.environ.items() if k != "GCN_INTERPRET"}
        if addrs is None:
            what = "nothing interpreted"
        else:
            listing = write_list(self.stem, f"{self.count:02d}", addrs)
            env["GCN_INTERPRET"] = str(listing)
            what = f"{len(addrs)} functions in {listing.name}"
        began = time.monotonic()
        # Nothing interpreted runs as fast as the build the goldens came from, so it gets no --slow.
        slow = [] if addrs is None else [f"--slow={self.slow}"]
        done = subprocess.run([sys.executable, str(self.tool), "check", self.route, *slow],
                              env=env, stdout=subprocess.PIPE, text=True, errors="replace")
        code, self.output = done.returncode, done.stdout
        if code not in (0, 1):
            self.show_output()
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
        if re.fullmatch(re.escape(stem) + r"-(\d+|found|smallest)\.txt", old.name):
            old.unlink()  # an earlier bisect's lists
    checks = Checks(TOOLS[kind], route, slow, stem)
    if checks.check(None):
        checks.show_output()
        raise ValueError(f"{route} changes with nothing interpreted, so there's nothing to bisect")
    if not checks.changes(addrs):
        print(f"Interpreting all {len(addrs)} functions leaves {route} matching, so none of them changes it.")
        return 0
    try:
        found = narrow(addrs, checks.changes)
    except Irreducible as e:
        smallest = write_list(stem, "smallest", e.smallest)
        text = (f"Interpreting the {len(e.smallest)} functions in {smallest} changes {route}, but the search "
                f"ended on a function that doesn't change it alone. The change needs several functions "
                f"together, or a list ran too slowly to reach the route's checkpoints.")
        if e.found:
            text += f" The functions found alone before that are listed in {write_list(stem, 'found', e.found)}."
        raise ValueError(text) from None
    listing = write_list(stem, "found", found)
    if not checks.changes(found):
        checks.show_output()
        raise ValueError(f"Interpreting the {len(found)} functions found together leaves {route} matching, "
                         f"though each changes it alone. They're listed in {listing}.")
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
