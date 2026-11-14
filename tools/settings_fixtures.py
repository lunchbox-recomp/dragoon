#!/usr/bin/env python3
"""What does the engine write over settings.txt, and what sizes does it give the picture?

Usage: settings_fixtures.py [--out DIR] [--check] [--cxx FILE]

It compiles settings_fixtures.cpp beside it with gcn-recomp's own runtime/settings.cpp,
runtime/platform.cpp and runtime/gx/aspect.h, from the submodule, then writes the launcher's
fixtures to DIR (launcher/Tests/DragoonCoreTests/SettingsFixtures by default):
  NAME.in, NAME.out  settings.txt before a save and what settings_save wrote over it with the
                     values cases.txt gives NAME. The missing case has no .in
  cases.txt          NAME ASPECT FULLSCREEN SCALE DISC for each case
  window-sizes.txt   ASPECT USABLE_W USABLE_H W H, the window main.cpp opens in a usable area,
                     0 by 0 for none, with its 40 point title bar
  fits.txt           ASPECT DISPLAY_W DISPLAY_H X Y W H, the fullscreen picture
  scales.txt         SCALE W H, the picture the renderer draws at scales 1 to 10
The cases and the areas are this file's CASES, USABLE and DISPLAYS. PictureSettingsTests and
PictureGeometryTests check the launcher against what it writes.

--check writes them to a scratch folder instead and prints each file of DIR that differs, is
missing or isn't one it writes. --cxx names the C++ compiler, c++ from PATH by default.

Exits 0 when it wrote them or they all match, 1 when --check found a difference, and 2 when
gcn-recomp isn't checked out, the harness doesn't compile or a save failed.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple, Optional

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "gcn-recomp" / "runtime"
HARNESS = Path(__file__).resolve().parent / "settings_fixtures.cpp"
FIXTURES = ROOT / "launcher" / "Tests" / "DragoonCoreTests" / "SettingsFixtures"


class Case(NamedTuple):
    name: str
    before: Optional[bytes]  # None for a file that isn't there
    aspect: str
    fullscreen: int
    scale: int
    disc: str


CASES = [
    Case("missing", None, "16:9", 1, 3, "fast"),
    Case("empty", b"", "4:3", 0, 2, "fast"),
    Case("plain-lf", b"aspect 4:3\nfullscreen 0\nscale 2\ndisc fast\n", "21:9", 1, 4, "fast"),
    Case("plain-crlf", b"aspect 4:3\r\nfullscreen 0\r\nscale 2\r\ndisc fast\r\n", "16:10", 0, 1, "fast"),
    Case("bom-comments-unknown",
         b"\xef\xbb\xbf# Picture\r\naspect 4:3\r\n\r\n# Mods\r\ndisc_overlay mods/manifest.txt\r\n"
         b"menu_motion off\r\nfuture_key some value\r\nscale 2\r\n", "window", 0, 2, "fast"),
    Case("open-lf", b"aspect 16:9\nscale 2", "4:3", 0, 5, "fast"),
    Case("open-crlf", b"aspect 16:9\r\nfullscreen 1\r\nscale 2", "16:9", 0, 2, "console"),
    Case("keys-missing-crlf", b"# just a comment\r\nram_patches patches.txt\r\n", "16:9", 1, 2, "fast"),
    Case("spacing-and-duplicates",
         b"  aspect\t16:9   \n\tscale 3\naspect 4:3\n#aspect 21:9\naspectx 1\nscale\nfullscreen  1  \n"
         b"   \ndisc console\n", "16:10", 1, 8, "console"),
    Case("bad-values", b"aspect 5\nfullscreen yes\nscale 0\ndisc slow\n", "4:3", 0, 2, "fast"),
    Case("not-utf8", b"# caf\xe9 \xff\xfe settings\naspect 4:3\nname \x80\x81\n", "21:9", 0, 3, "fast"),
    Case("mixed-endings", b"aspect 4:3\nscale 2\r\n# note\r\nfullscreen 0\n", "16:9", 1, 2, "fast"),
    # The first newline is CR LF and the last LF, so the keys added take CR LF from the first.
    Case("crlf-then-lf", b"aspect 4:3\r\naspect 16:9\n", "window", 0, 2, "fast"),
    Case("bom-only", b"\xef\xbb\xbf", "16:9", 0, 2, "fast"),
    Case("double-cr", b"aspect 4:3\r\r\nscale 2\r\n", "21:9", 0, 2, "fast"),
    Case("open-after-cr", b"aspect 4:3\nscale 2\r", "16:9", 0, 6, "fast"),
    Case("bom-open-crlf", b"\xef\xbb\xbffullscreen 0\r\naspect window", "4:3", 1, 2, "fast"),
    Case("unchanged", b"aspect 16:9\nfullscreen 1\nscale 3\ndisc fast\n", "16:9", 1, 3, "fast"),
    Case("big-scale", b"scale 2\n", "4:3", 0, 999999999, "fast"),
]

ASPECTS = ["4:3", "16:9", "16:10", "21:9", "window"]
# Usable areas in points, as SDL_GetDisplayUsableBounds gives them, 0 by 0 for none.
USABLE = [(0, 0), (1512, 944), (1440, 875), (1280, 760), (1920, 1050), (2560, 1415), (3008, 1667),
          (1024, 640), (800, 500), (2240, 1000)]
# Whole displays in points, which a fullscreen game covers.
DISPLAYS = [(1512, 982), (1440, 900), (1920, 1080), (2560, 1440), (3440, 1440), (1280, 800),
            (3024, 1964), (1024, 768)]
SCALES = range(1, 11)


class Failure(Exception):
    """The fixtures can't be made, with the one line that says why."""


def build(work: Path, cxx: str) -> Path:
    """The harness, compiled into WORK."""
    sources = [RUNTIME / "settings.cpp", RUNTIME / "platform.cpp", RUNTIME / "gx" / "aspect.h"]
    missing = [str(p.relative_to(ROOT)) for p in sources if not p.is_file()]
    if missing:
        raise Failure(f"{missing[0]}: not there, so check gcn-recomp out: git submodule update --init gcn-recomp")
    exe = work / "settings_fixtures"
    cmd = [cxx, "-std=c++20", "-I", str(RUNTIME), str(HARNESS), str(sources[0]), str(sources[1]), "-o", str(exe)]
    try:
        done = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except OSError as e:
        raise Failure(f"{cxx}: {e.strerror}") from None
    if done.returncode != 0:
        first = next((line for line in done.stdout.splitlines() if "error" in line), done.stdout.strip())
        raise Failure(f"{HARNESS.name}: doesn't compile: {first}")
    return exe


def ask(exe: Path, commands: list[str]) -> list[str]:
    """The harness's line for each command."""
    done = subprocess.run([str(exe)], input="".join(c + "\n" for c in commands), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, check=False)
    lines = done.stdout.splitlines()
    if done.returncode != 0 or len(lines) != len(commands):
        raise Failure(f"{exe.name}: exited {done.returncode} after {len(lines)} of {len(commands)} answers")
    return lines


def write(out: Path, exe: Path, work: Path) -> None:
    """Every fixture and table, written to OUT."""
    out.mkdir(parents=True, exist_ok=True)
    saves = work / "saves"
    saves.mkdir()
    commands = []
    for case in CASES:
        folder = saves / case.name
        folder.mkdir()
        if case.before is not None:
            (folder / "settings.txt").write_bytes(case.before)
            (out / f"{case.name}.in").write_bytes(case.before)
        commands.append(f"save {case.aspect} {case.fullscreen} {case.scale} {case.disc} {folder / 'settings.txt'}")
    for case, answer in zip(CASES, ask(exe, commands)):
        if answer != "saved":
            raise Failure(f"{case.name}: settings_save failed")
        (out / f"{case.name}.out").write_bytes((saves / case.name / "settings.txt").read_bytes())
    (out / "cases.txt").write_text(
        "".join(f"{c.name} {c.aspect} {c.fullscreen} {c.scale} {c.disc}\n" for c in CASES))

    windows = [(a, w, h) for a in ASPECTS for w, h in USABLE]
    answers = ask(exe, [f"window {a} {w} {h}" for a, w, h in windows])
    (out / "window-sizes.txt").write_text(
        "".join(f"{a} {w} {h} {size}\n" for (a, w, h), size in zip(windows, answers)))
    fits = [(a, w, h) for a in ASPECTS for w, h in DISPLAYS]
    answers = ask(exe, [f"fit {a} {w} {h}" for a, w, h in fits])
    (out / "fits.txt").write_text("".join(f"{a} {w} {h} {rect}\n" for (a, w, h), rect in zip(fits, answers)))
    answers = ask(exe, [f"scale {n}" for n in SCALES])
    (out / "scales.txt").write_text("".join(f"{n} {size}\n" for n, size in zip(SCALES, answers)))


def differences(made: Path, committed: Path) -> list[str]:
    """Each file of COMMITTED that isn't what MADE holds, with why."""
    found = []
    names = sorted({p.name for p in made.iterdir()} | {p.name for p in committed.iterdir()})
    for name in names:
        if not (committed / name).is_file():
            found.append(f"{name}: missing")
        elif not (made / name).is_file():
            found.append(f"{name}: not one the harness writes")
        elif (made / name).read_bytes() != (committed / name).read_bytes():
            found.append(f"{name}: differs")
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Write the launcher's settings.txt fixtures and geometry tables from the engine's own code.")
    parser.add_argument("--out", type=Path, default=FIXTURES, help="the fixtures' folder")
    parser.add_argument("--check", action="store_true", help="compare with --out instead of writing it")
    parser.add_argument("--cxx", default="c++", help="the C++ compiler (default c++)")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="settings fixtures ") as tmp:
        work = Path(tmp)
        try:
            exe = build(work, args.cxx)
            if not args.check:
                write(args.out, exe, work)
                return 0
            if not args.out.is_dir():
                raise Failure(f"{args.out}: not a folder")
            made = work / "made"
            write(made, exe, work)
        except Failure as e:
            print(e, file=sys.stderr)
            return 2
        found = differences(made, args.out)
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
