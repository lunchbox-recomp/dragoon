#!/usr/bin/env python3
"""Which runs in build/probe/ are old enough to clear?

Usage: prune_runs.py [--hours N] [--delete] CLONE ...

For each CLONE, looks at the direct children of CLONE/build/probe/ and nothing else. A child
is stale when its own mtime and those of everything under it are all more than N hours old (24
unless given), and a file's age is its own mtime. The names in build/probe/keep, one a line,
are never stale. Blank lines and lines starting with # are skipped. keep itself is never
touched. Names are compared ignoring case, since the default macOS volume does, so Keep is
never touched and a keep line "case" protects Case. That only ever keeps more.

Links are never followed. The walk for mtimes doesn't go through them, a link's age is its own
mtime, and a stale link is removed as a link while its target stays. A CLONE is refused, with
exit 2 before anything is removed from any CLONE, when it isn't a directory, when its
build/probe resolves anywhere but CLONE/build/probe (a link to elsewhere, say) or when
build/probe/keep is there but can't be read as a plain file. A CLONE without build/probe is
skipped with a note on stderr.

Without --delete it prints what would go, one line each with its size and age, then a total.
With --delete it removes those and prints the same lines and the space freed. A size is the
length of the regular files, not the blocks they take. A child that can't be read or removed is
named on stderr, and the rest still go. A child that failed to remove counts as nothing freed.

Exits 0 when nothing failed, 1 when a child couldn't be read or removed, 2 on a bad argument or
a refused CLONE.
"""
from __future__ import annotations

import argparse
import math
import os
import shutil
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path

KEEP = "keep"
DEFAULT_HOURS = 24.0
UNITS = ("B", "KiB", "MiB", "GiB", "TiB")


@dataclass
class Child:
    path: Path
    size: int  # bytes in the regular files under it
    newest: float  # newest mtime of it and of everything under it


def probe_dir(clone: Path) -> Path | None:
    """CLONE/build/probe, or None when there isn't one. A CLONE that isn't a directory, or whose
    build/probe resolves anywhere but CLONE/build/probe, is a ValueError."""
    if not clone.is_dir():
        raise ValueError(f"{clone}: not a directory")
    probe = clone / "build" / "probe"
    if not os.path.lexists(probe):
        return None
    expected = clone.resolve() / "build" / "probe"
    try:
        real = probe.resolve()  # 3.9 raises RuntimeError on a link loop
    except (OSError, RuntimeError) as e:
        raise ValueError(f"{probe}: can't resolve it: {e}") from None
    if real != expected:
        raise ValueError(f"{probe}: resolves to {real}, not {expected}")
    return probe if probe.is_dir() else None


def read_keep(probe: Path) -> set[str]:
    """The names in probe/keep, casefolded. A keep that exists but isn't a readable plain file is
    an error, since the names it protects can't be known."""
    path = probe / KEEP
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return set()
    if not stat.S_ISREG(mode):
        raise ValueError(f"{path}: not a plain file")
    lines = path.read_text(encoding="utf-8", errors="surrogateescape").split("\n")
    names = (line.strip() for line in lines)
    return {name.casefold() for name in names if name and not name.startswith("#")}


def measure(path: Path) -> tuple[int, float]:
    """The bytes in the regular files under PATH and the newest mtime of PATH and everything
    under it. A link is measured as itself and a directory link isn't entered."""
    st = path.lstat()
    size = st.st_size if stat.S_ISREG(st.st_mode) else 0
    newest = st.st_mtime
    todo = [path] if stat.S_ISDIR(st.st_mode) else []
    while todo:
        try:
            entries = list(os.scandir(todo.pop()))
        except FileNotFoundError:
            continue  # removed since its parent was listed
        for entry in entries:
            try:
                st = entry.stat(follow_symlinks=False)
            except FileNotFoundError:
                continue
            newest = max(newest, st.st_mtime)
            if stat.S_ISREG(st.st_mode):
                size += st.st_size
            elif stat.S_ISDIR(st.st_mode):
                todo.append(Path(entry.path))
    return size, newest


def find_stale(probe: Path, keep: set[str], cutoff: float) -> tuple[list[Child], list[str]]:
    """The children of PROBE whose newest mtime is before CUTOFF, by name, and a line for each
    child that couldn't be read. A child named keep in any case, or whose casefolded name is in
    the set `keep` (from read_keep), is left out."""
    stale: list[Child] = []
    unreadable: list[str] = []
    for name in sorted(os.listdir(probe)):
        folded = name.casefold()
        if folded == KEEP or folded in keep:
            continue
        path = probe / name
        try:
            size, newest = measure(path)
        except FileNotFoundError:
            continue
        except OSError as e:
            unreadable.append(f"{path}: cannot read: {e}")
            continue
        if newest < cutoff:
            stale.append(Child(path, size, newest))
    return stale, unreadable


def remove(path: Path) -> None:
    """Remove PATH. A link goes as a link, whatever it points at."""
    if stat.S_ISDIR(path.lstat().st_mode):
        shutil.rmtree(path)
    else:
        path.unlink()


def human_size(n: int) -> str:
    size = float(n)
    for unit in UNITS[:-1]:
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} {UNITS[-1]}"


def human_age(seconds: float) -> str:
    days, minutes = divmod(max(int(seconds // 60), 0), 24 * 60)
    hours, minutes = divmod(minutes, 60)
    if days:
        return f"{days}d {hours}h"
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def n_entries(n: int) -> str:
    return f"{n} entry" if n == 1 else f"{n} entries"


def hours(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} isn't a number of hours") from None
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError(f"{text!r} isn't 0 or more hours")
    return value


def collect(clones: list[Path]) -> list[tuple[Path, set[str]]] | None:
    """Each CLONE's build/probe with its keep names, once per directory, or None when any CLONE
    is refused. Every CLONE is checked before any is touched, so a refusal removes nothing."""
    probes: list[tuple[Path, set[str]]] = []
    seen: set[Path] = set()
    refused = False
    for clone in clones:
        try:
            probe = probe_dir(clone)
            keep = read_keep(probe) if probe else set()
        except (OSError, ValueError) as e:
            print(e, file=sys.stderr)
            refused = True
            continue
        if probe is None:
            print(f"{clone}: no build/probe, skipped", file=sys.stderr)
        elif probe.resolve() not in seen:
            seen.add(probe.resolve())
            probes.append((probe, keep))
    return None if refused else probes


def prune(probes: list[tuple[Path, set[str]]], cutoff: float, now: float,
          delete: bool) -> tuple[int, int, int]:
    """Print each stale child, removing it first when DELETE. Returns how many were listed, their
    bytes and how many children failed."""
    count = freed = failed = 0
    for probe, keep in probes:
        try:
            stale, unreadable = find_stale(probe, keep, cutoff)
        except OSError as e:
            stale, unreadable = [], [f"{probe}: cannot read: {e}"]
        for line in unreadable:
            print(line, file=sys.stderr)
        failed += len(unreadable)
        for child in stale:
            if delete:
                try:
                    remove(child.path)
                except OSError as e:
                    print(f"{child.path}: cannot remove: {e}", file=sys.stderr)
                    failed += 1
                    continue
            print(f"{human_size(child.size):>10}  {human_age(now - child.newest):>7}  {child.path}")
            count += 1
            freed += child.size
    return count, freed, failed


def main(argv: list[str], now: float | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=hours, default=DEFAULT_HOURS, metavar="N",
                    help=f"a child is stale when nothing in it is newer than N hours "
                         f"(default {DEFAULT_HOURS:g})")
    ap.add_argument("--delete", action="store_true", help="remove the stale children")
    ap.add_argument("clones", nargs="+", type=Path, metavar="CLONE")
    args = ap.parse_args(argv)
    now = time.time() if now is None else now
    probes = collect(args.clones)
    if probes is None:
        return 2
    count, freed, failed = prune(probes, now - args.hours * 3600, now, args.delete)
    verb = "freed" if args.delete else "would free"
    tail = f", {failed} failed" if failed else ""
    print(f"{verb} {human_size(freed)} from {n_entries(count)}{tail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
