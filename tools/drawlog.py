#!/usr/bin/env python3
"""Which cameras does a frame draw through, and what aspect does each hold?

Usage: drawlog.py cameras LOG [--symbols FILE] [--frame N]
       drawlog.py aspects LOG [--from N] [--to N]

LOG is a run's stdout.txt from tools/probe.sh. The draws come from GCN_DRAWLOG=<frame> with
GCN_DRAWLOG_VERBOSE=1, which adds each draw's viewport. The cameras and their render
callbacks come from DRAGOON_CENSUS=1's [census] lines (src/census.cpp).

cameras prints one line per distinct projection and viewport among the [draw] lines, in the
order they're first drawn. A perspective line gives the projection's aspect and field of view,
an orthographic one its frame, then the viewport, the viewport's aspect over the projection's
and the draw count. The [census] cameras with the same field of view (or the same frame) and
viewport follow, with their stored aspect, the callbacks that set them and the callbacks that
drew through them, by name with --symbols (analysis/symbols.txt). --frame N reads only the
[census] lines of frame N. Cameras with nothing drawn come last, as "no draws".

aspects prints each perspective camera's stored aspects in the [census] lines from frame N to
frame M, with the frames it held each, a camera being one address in one viewport.

Exits 0 once it has read the log, 1 when aspects finds a camera whose stored aspect changed
within its viewport, 2 on a bad argument or a log it can't read or that lacks the lines asked
for.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

NUM = r"-?[\d.]+(?:e[-+]?\d+)?"
DRAW = re.compile(rf"^\[draw\] \d+ .*?proj=([po]),({NUM}),({NUM}),({NUM}),({NUM}),{NUM},{NUM}\s")
# The renderer prints a draw in pieces from its own thread, so a [census] line from the guest
# thread can land at the end of one of its lines. Neither pattern needs the line to itself.
VIEWPORT = re.compile(rf"^\s+viewport=({NUM}),({NUM}),{NUM} ({NUM}),({NUM}),{NUM} "
                      r"scissor=\w+ \w+ offset=([0-9A-F]{6})")
CENSUS = re.compile(r"\[census\] f=(\d+) cam=([0-9A-F]{8}) type=(\w+) p=(\S*) vp=(\S+) "
                    r"cb=([0-9A-F]{8}) cls=(\d+) via=(set|draw)$")
SYMBOL = re.compile(r"^(\S+) = \.text:0x([0-9A-Fa-f]{8});")
# The draw log prints the projection to four decimals, so an orthographic camera matches
# within this. A perspective camera's y scale matches within PERSP_TOLERANCE of the cotangent
# of half its field of view, since the game's own comes out about 0.02% over.
TOLERANCE = 1.5e-4
PERSP_TOLERANCE = 1e-3


@dataclass
class Draw:
    kind: str                  # "persp" or "ortho"
    proj: tuple[float, ...]    # GX's x scale, x offset, y scale, y offset
    viewport: tuple[float, float, float, float] | None = None  # x, y, width, height


@dataclass
class Camera:
    frame: int
    cam: int
    kind: str
    proj: tuple[float, ...]    # fov and aspect, or top, bottom, left and right
    viewport: tuple[float, float, float, float]
    cb: int
    via: str


@dataclass
class Group:
    kind: str
    proj: tuple[float, ...]
    viewport: tuple[float, float, float, float] | None
    count: int = 0

    @property
    def aspect(self) -> float:
        """A perspective projection's width over height, or an orthographic frame's."""
        if self.kind == "persp":
            return self.proj[2] / self.proj[0]
        return self.frame[0] / self.frame[1]

    @property
    def fov(self) -> float:
        return math.degrees(2 * math.atan(1 / self.proj[2]))

    @property
    def frame(self) -> tuple[float, float]:
        return 2 / abs(self.proj[0]), 2 / abs(self.proj[2])

    @property
    def ratio(self) -> float | None:
        if not self.viewport:
            return None
        return self.viewport[2] / self.viewport[3] / self.aspect


def parse(lines) -> tuple[list[Draw], list[Camera]]:
    draws: list[Draw] = []
    cams: list[Camera] = []
    for line in lines:
        line = line.rstrip("\n")
        if m := DRAW.match(line):
            draws.append(Draw("persp" if m[1] == "p" else "ortho", tuple(float(x) for x in m.groups()[1:])))
        elif (m := VIEWPORT.match(line)) and draws:
            sx, sy, ox, oy = (float(x) for x in m.groups()[:4])
            offset = int(m[5], 16)
            xoff, yoff = (offset & 0x3FF) * 2, ((offset >> 10) & 0x3FF) * 2
            draws[-1].viewport = (ox - xoff - abs(sx), oy - yoff - abs(sy), 2 * abs(sx), 2 * abs(sy))
        if m := CENSUS.search(line):
            left, right, top, bottom = (float(x) for x in m[5].split(","))
            cams.append(Camera(int(m[1]), int(m[2], 16), m[3], tuple(float(x) for x in m[4].split(",") if x),
                               (left, top, right - left, bottom - top), int(m[6], 16), m[8]))
    return draws, cams


def group(draws: list[Draw]) -> list[Group]:
    groups: dict[tuple, Group] = {}
    for d in draws:
        g = groups.setdefault((d.kind, d.proj, d.viewport), Group(d.kind, d.proj, d.viewport))
        g.count += 1
    return list(groups.values())


def _close(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return all(abs(x - y) <= TOLERANCE for x, y in zip(a, b, strict=True))


def _same_viewport(a, b) -> bool:
    return a is not None and all(abs(x - y) <= 1 for x, y in zip(a, b))


def matching(g: Group, cams: list[Camera]) -> list[Camera]:
    """The census lines for cameras that project like g, by field of view or frame, in its
    viewport. A perspective camera's aspect is left out, so a widened projection still finds
    the camera whose stored aspect it came from."""
    found = []
    for c in cams:
        if c.kind != g.kind or not _same_viewport(g.viewport, c.viewport):
            continue
        if c.kind == "persp" and len(c.proj) == 2:
            if math.isclose(1 / math.tan(math.radians(c.proj[0]) / 2), g.proj[2], rel_tol=PERSP_TOLERANCE):
                found.append(c)
        elif c.kind == "ortho" and len(c.proj) == 4:
            top, bottom, left, right = c.proj
            expect = (2 / (right - left), -(right + left) / (right - left), 2 / (top - bottom),
                      -(top + bottom) / (top - bottom))
            if _close(expect, g.proj):
                found.append(c)
    return found


def read_symbols(path: Path) -> dict[int, str]:
    names = {}
    with path.open() as lines:
        for line in lines:
            if m := SYMBOL.match(line):
                names[int(m[2], 16)] = m[1]
    return names


def _unique(values) -> list:
    return list(dict.fromkeys(values))


def _viewport_text(vp) -> str:
    return "?" if vp is None else f"{vp[0]:.0f},{vp[1]:.0f} {vp[2]:.0f}x{vp[3]:.0f}"


def _camera_text(cams: list[Camera], names: dict[int, str]) -> str:
    def callbacks(via: str) -> str:
        return ", ".join(names.get(cb, f"{cb:08X}" if cb else "no object")
                         for cb in _unique(c.cb for c in cams if c.via == via))
    parts = ["cams " + ",".join(f"{a:08X}" for a in _unique(c.cam for c in cams))]
    if cams[0].kind == "persp":
        parts.append("stored " + ",".join(_unique(f"{c.proj[1]:.6g}" for c in cams)))
    if set_by := callbacks("set"):
        parts.append("set by " + set_by)
    if drawn_by := callbacks("draw"):
        parts.append("drawn by " + drawn_by)
    return "  ".join(parts)


def _ortho_frame(proj: tuple[float, ...]) -> tuple[float, float]:
    top, bottom, left, right = proj
    return abs(right - left), abs(top - bottom)


def group_line(g: Group, cams: list[Camera], names: dict[int, str]) -> str:
    if g.kind == "persp":
        head = f"persp aspect {g.aspect:.4f} fov {g.fov:.1f}"
        aspect = g.aspect
    elif cams:
        w, h = _ortho_frame(cams[0].proj)
        head, aspect = f"ortho frame {w:.0f}x{h:.0f}", w / h
    else:
        head, aspect = f"ortho frame {g.frame[0]:.1f}x{g.frame[1]:.1f}", g.aspect
    ratio = "?" if g.viewport is None else f"{g.viewport[2] / g.viewport[3] / aspect:.3f}"
    line = f"{head}  vp {_viewport_text(g.viewport)}  ratio {ratio}  draws {g.count}"
    return line + ("  " + _camera_text(cams, names) if cams else "")


def unmatched_lines(cams: list[Camera], used: set[int], names: dict[int, str]) -> list[str]:
    left: dict[tuple, list[Camera]] = {}
    for i, c in enumerate(cams):
        if i not in used:
            left.setdefault((c.kind, c.proj if c.kind == "ortho" else c.proj[:1], c.viewport), []).append(c)
    out = []
    for (kind, proj, vp), group_cams in left.items():
        if kind == "persp" and proj:
            head = f"persp fov {proj[0]:.1f}"
        elif kind == "ortho" and len(proj) == 4:
            w, h = _ortho_frame(proj)
            head = f"ortho frame {w:.0f}x{h:.0f}"
        else:
            head = kind
        out.append(f"no draws: {head} vp {_viewport_text(vp)}  {_camera_text(group_cams, names)}")
    return out


def cameras(args) -> int:
    try:
        with args.log.open(errors="replace") as lines:
            draws, cams = parse(lines)
        names = read_symbols(args.symbols) if args.symbols else {}
    except OSError as e:
        print(e, file=sys.stderr)
        return 2
    if not draws:
        print(f"{args.log}: no [draw] lines; was GCN_DRAWLOG=<frame> set?", file=sys.stderr)
        return 2
    if args.frame is not None:
        cams = [c for c in cams if c.frame == args.frame]
    used: set[int] = set()
    for g in group(draws):
        found = matching(g, cams)
        used.update(id_ for id_, c in enumerate(cams) if any(c is f for f in found))
        print(group_line(g, found, names))
    for line in unmatched_lines(cams, used, names):
        print(line)
    return 0


def aspects(args) -> int:
    try:
        with args.log.open(errors="replace") as lines:
            _, cams = parse(lines)
    except OSError as e:
        print(e, file=sys.stderr)
        return 2
    if not cams:
        print(f"{args.log}: no [census] lines; was DRAGOON_CENSUS=1 set?", file=sys.stderr)
        return 2
    held: dict[tuple, dict[float, set[int]]] = {}
    fovs: dict[tuple, float] = {}
    for c in cams:
        if c.kind != "persp" or len(c.proj) != 2 or not args.start <= c.frame <= args.end:
            continue
        key = (c.cam, c.viewport)
        fovs[key] = c.proj[0]
        held.setdefault(key, {}).setdefault(c.proj[1], set()).add(c.frame)
    changed = 0
    for (cam, vp), by_aspect in held.items():
        name = f"{cam:08X} vp {_viewport_text(vp)} fov {fovs[(cam, vp)]:.1f}"
        for aspect, frames in by_aspect.items():
            print(f"{name}  aspect {aspect:.6g} in frames {min(frames)}..{max(frames)} ({len(frames)} frames)")
        if len(by_aspect) > 1:
            changed += 1
            print(f"{name}  changed its stored aspect {len(by_aspect) - 1} times")
    return 1 if changed else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    cam = sub.add_parser("cameras")
    cam.add_argument("log", type=Path)
    cam.add_argument("--symbols", type=Path)
    cam.add_argument("--frame", type=int)
    asp = sub.add_parser("aspects")
    asp.add_argument("log", type=Path)
    asp.add_argument("--from", dest="start", type=int, default=0)
    asp.add_argument("--to", dest="end", type=int, default=2**32)
    args = ap.parse_args(argv)
    return cameras(args) if args.command == "cameras" else aspects(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
