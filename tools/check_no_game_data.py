#!/usr/bin/env python3
"""Fail if git tracks anything that came from a disc.

    check_no_game_data.py    check every tracked file

Exits 1 and lists each path. The rules mirror .gitignore, so a file added with
`git add -f` still fails CI.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISC_SUFFIXES = (".iso", ".gcm", ".ciso", ".rvz", ".gcz", ".wbfs", ".dol", ".rel", ".gci", ".raw")


def violations(paths):
    bad = []
    for p in paths:
        top, sep, _ = p.partition("/")
        if p.lower().endswith(DISC_SUFFIXES):
            bad.append(p)
        elif sep and (top.startswith("build") or top == "saves"):
            bad.append(p)
        elif sep and top == "rom" and p != "rom/README.md":
            bad.append(p)
    return bad


def main():
    out = subprocess.run(["git", "-C", ROOT, "ls-files"], capture_output=True, text=True, check=True).stdout
    bad = violations(out.splitlines())
    for p in bad:
        print(f"game data tracked: {p}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
