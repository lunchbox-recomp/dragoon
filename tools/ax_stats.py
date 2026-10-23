#!/usr/bin/env python3
"""What did the AX mixer's voices ask for over a run? Sum a run's GCN_AXSTATS counts.

Usage: ax_stats.py STDOUT [STDOUT ...] [--until LIST]

Reads the "[ax] pb" and "[ax] bus" lines a run made with GCN_AXSTATS=1 prints every 400
command lists, from each stdout.txt given, and prints one row per count with a column per
file and a total. Counts are summed over the windows. The bus peaks (main_l to auxb_s) take
the largest window instead. src0_coef=a/b/c/d splits into src0_coef0 to src0_coef3, and the
mixer's top eight values are left out. --until stops at the window ending at that list
count, so unpaced runs that got different distances in the same time cover the same lists.
A file with no such lines exits 2.

A column is named by its run's directory (for a stdout.txt) or the file's name. Where two
files would get the same name, such as two clones' audio-title runs, each takes the shortest
trailing path that no other file shares. The same file given twice exits 2.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

LINE = re.compile(r"^\[ax\] (pb|bus) list=(\d+) (.*)$", re.MULTILINE)
FIELD = re.compile(r"(\w+)=([\d/]+)(?=\s|$)")
PEAKS = {"main_l", "main_r", "main_s", "auxa_l", "auxa_r", "auxa_s", "auxb_l", "auxb_r", "auxb_s"}


def totals(text: str, until: int | None = None) -> dict[str, int]:
    """The counts in one run's output up to list `until`, keyed in the order they first
    appear, with 'windows' first: the number of "[ax] pb" lines."""
    out: dict[str, int] = {"windows": 0}
    for kind, n, rest in LINE.findall(text):
        if until is not None and int(n) > until:
            continue
        out["windows"] += kind == "pb"
        for key, value in FIELD.findall(rest):
            parts = value.split("/")
            names = [f"{key}{i}" for i in range(len(parts))] if len(parts) > 1 else [key]
            for name, part in zip(names, parts):
                n = int(part)
                out[name] = max(out.get(name, 0), n) if name in PEAKS else out.get(name, 0) + n
    return out


def table(columns: dict[str, dict[str, int]]) -> str:
    keys: list[str] = []
    for counts in columns.values():
        keys += [k for k in counts if k not in keys]
    heads = list(columns) + ["total"]
    rows = []
    for k in keys:
        vals = [counts.get(k, 0) for counts in columns.values()]
        rows.append([k] + [str(v) for v in vals] + [str(max(vals) if k in PEAKS else sum(vals))])
    width = [max(len(r[i]) for r in [[""] + heads] + rows) for i in range(len(heads) + 1)]
    lines = [[""] + heads] + rows
    return "\n".join(" ".join(c.ljust(w) if i == 0 else c.rjust(w) for i, (c, w) in enumerate(zip(line, width)))
                     for line in lines)


def parts(path: Path) -> tuple[str, ...]:
    """A stdout.txt is named by its run's directory, any other file by itself, as the
    components of an absolute path."""
    full = Path(os.path.abspath(path))
    return (full.parent if full.name == "stdout.txt" else full).parts


def labels(paths: list[Path]) -> list[str]:
    """Each file's label is its run's directory name, or with more of the path in front of it
    where another file would get the same one: the shortest trailing path that no other file
    shares. The same file twice is an error, since it would have one label."""
    named: list[tuple[str, ...]] = []
    for path in paths:
        name = parts(path)
        if name in named:
            raise ValueError(f"{path}: given twice")
        named.append(name)
    out = []
    for i, name in enumerate(named):
        k = 1
        while k < len(name) and any(other[-k:] == name[-k:] for j, other in enumerate(named) if j != i):
            k += 1
        out.append(str(Path(*name[-k:])))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--until", type=int, default=None, help="the last list count to take")
    args = ap.parse_args(argv)
    if args.until is not None and args.until <= 0:
        ap.error("--until is a list count, over 0")
    try:
        names = labels(args.files)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    columns: dict[str, dict[str, int]] = {}
    for path, name in zip(args.files, names):
        try:
            counts = totals(path.read_text(errors="replace"), args.until)
        except OSError as e:
            print(e, file=sys.stderr)
            return 2
        if not counts["windows"]:
            print(f"{path}: no [ax] pb lines up to that list; was it run with GCN_AXSTATS=1?", file=sys.stderr)
            return 2
        columns[name] = counts
    print(table(columns))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
