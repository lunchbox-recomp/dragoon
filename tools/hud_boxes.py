"""Does each HUD draw keep its 4:3 box at a wider output? drawlog.py hud runs this.

Usage: drawlog.py hud OLD NEW [--aspect W:H]

OLD and NEW are the stdout.txt of two tools/probe.sh runs of one route to one frame, with
GCN_DRAWLOG=<frame> and GCN_DRAWLOG_VERBOSE=1. OLD is at 4:3 and NEW at --aspect, 16:9 when it
isn't given. Each [draw] line names the draw's anchor, its rect and its box on the EFB after the
anchor's remap.

A HUD draw is one with an anchor, or one through a projection both runs drew with, since the
world's projections widen and the HUD's don't. The HUD draws of the two runs pair by projection
kind, textures and order.

An anchored pair passes when its width, its height and its distance to the anchored edge of its
rect each come within 1 pixel of 4:3's, in display pixels at 480 high. A centered draw's distance
is from the rect's middle to its own. No side of the box may stick out of its view by more than 1
pixel more than at 4:3 either. Its view is the smallest world view its whole 4:3 box sits in, or
else the screen. The world views are the viewports of OLD's draws whose projection NEW doesn't
have, which are the ones that widened.

A pair with no anchor at either aspect is listed as stretched, and passes. A HUD draw that
pairs with none is left out unless it has an anchor, and then it fails.

Each line gives the two draws' indices, the projection kind, the anchor, the textures by content
hash (copy for an EFB copy) and both boxes in display pixels, then ok, stretched or FAIL with the
reasons. The last line counts them. Exits 0 when no anchored draw fails, 1 when one does and 2 on
a bad argument or a log it can't read or that lacks the lines it needs.
"""
from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from drawlines import DRAW, VIEWPORT, projection, viewport

FLOAT = r"-?\d+(?:\.\d+)?"
FIELDS = re.compile(rf" anchor=(?:S|([LCR])\(({FLOAT})\.\.({FLOAT})\)) "
                    rf"scr=(?:({FLOAT})\.\.({FLOAT}),({FLOAT})\.\.({FLOAT})|none)")
TEXTURE = re.compile(r" t\d=\d+(?:(\*)|\[([0-9a-f]{16})\])")

EFB_WIDTH = 640.0
SCREEN = (0.0, 0.0, EFB_WIDTH, 480.0)  # x, y, width and height in EFB pixels
TOLERANCE = 1.0                        # display pixels at 480 high
EDGES = {"L": "left edge", "R": "right edge", "C": "middle"}

Box = tuple[float, float, float, float]   # x0, x1, y0, y1
Rect = tuple[float, float, float, float]  # x, y, width, height


@dataclass
class HudDraw:
    index: int
    kind: str                         # "persp" or "ortho"
    proj: tuple[float, ...]
    anchor: str | None = None         # S, L, C or R, None until its fields are read
    rect: tuple[float, float] | None = None
    box: Box | None = None            # on the EFB after the remap, None for no box
    textures: tuple[str, ...] = ()
    viewport: Rect | None = None

    @property
    def anchored(self) -> bool:
        return self.anchor in EDGES

    @property
    def anchor_text(self) -> str:
        if self.rect is None:
            return self.anchor or "?"
        return f"{self.anchor}({self.rect[0]:g}..{self.rect[1]:g})"


def _textures(text: str) -> tuple[str, ...]:
    return tuple("copy" if star else digest for star, digest in TEXTURE.findall(text))


def _read_fields(d: HudDraw, line: str) -> bool:
    """Reads a draw's anchor, box and textures from its line. True when its textures may be on
    the next line."""
    m = FIELDS.search(line)
    if not m:
        return False
    d.anchor = m[1] or "S"
    d.rect = (float(m[2]), float(m[3])) if m[1] else None
    d.box = tuple(float(x) for x in m.groups()[3:]) if m[4] else None
    d.textures = _textures(line[m.end():])
    return not d.textures


def read_draws(lines) -> list[HudDraw]:
    draws: list[HudDraw] = []
    textures_next = False
    for line in lines:
        line = line.rstrip("\n")
        if m := DRAW.match(line):
            draws.append(HudDraw(int(m[1]), *projection(m)))
            textures_next = _read_fields(draws[-1], line)
            continue
        if not draws:
            continue
        d = draws[-1]
        if m := VIEWPORT.match(line):
            d.viewport = viewport(m)
        elif textures_next:
            # A draw with slivers ends its line with them, so its textures come on the next.
            d.textures = _textures(line)
        elif d.anchor is None:
            # A [census] line landed in the middle of the draw's line, so the rest came after it.
            textures_next = _read_fields(d, line)
            continue
        textures_next = False
    return draws


def world_views(old: list[HudDraw], new: list[HudDraw]) -> list[Rect]:
    """The viewports of OLD's draws whose projection NEW doesn't have, which are the world's."""
    kept = {(d.kind, d.proj) for d in new}
    views: list[Rect] = []
    for d in old:
        if d.viewport and (d.kind, d.proj) not in kept and d.viewport not in views:
            views.append(d.viewport)
    return views


def hud_draws(draws: list[HudDraw], other: list[HudDraw]) -> list[HudDraw]:
    """The draws with an anchor or a projection the other run drew with too."""
    shared = {(d.kind, d.proj) for d in other}
    return [d for d in draws if d.anchored or (d.kind, d.proj) in shared]


def pairs(old: list[HudDraw], new: list[HudDraw]) -> list[tuple[HudDraw | None, HudDraw | None]]:
    """Each of OLD with the next of NEW of its projection kind and textures, or None, then NEW's
    with none."""
    queues: dict[tuple, list[HudDraw]] = {}
    for d in new:
        queues.setdefault((d.kind, d.textures), []).append(d)
    found = [(d, queue.pop(0) if (queue := queues.get((d.kind, d.textures))) else None) for d in old]
    taken = {id(n) for _, n in found if n}
    return found + [(None, d) for d in new if id(d) not in taken]


def overhangs(box: Box, view: Rect) -> tuple[float, ...]:
    """How far the box sticks out of the view to the left, right, top and bottom, 0 for a side
    it doesn't."""
    x0, x1, y0, y1 = box
    vx, vy, vw, vh = view
    return tuple(max(0.0, d) for d in (vx - x0, x1 - (vx + vw), vy - y0, y1 - (vy + vh)))


def view_of(box: Box, views: list[Rect]) -> Rect:
    """The smallest view that holds the box, to within TOLERANCE, or else the screen."""
    holding = [v for v in views if max(overhangs(box, v)) <= TOLERANCE]
    return min(holding, key=lambda v: v[2] * v[3], default=SCREEN)


def edge_distance(anchor: str, rect: tuple[float, float], box: Box) -> float:
    if anchor == "L":
        return box[0] - rect[0]
    if anchor == "R":
        return rect[1] - box[1]
    return (box[0] + box[1]) / 2 - (rect[0] + rect[1]) / 2


def faults(old: HudDraw, new: HudDraw, scale: float, label: str, views: list[Rect]) -> list[str]:
    """What keeps NEW, at `scale` display pixels to an EFB pixel across, from holding OLD's box."""
    if (old.anchor, old.rect) != (new.anchor, new.rect):
        return [f"anchor {old.anchor_text} at 4:3, {new.anchor_text} at {label}"]
    if old.box is None or new.box is None:
        return [] if old.box == new.box else [f"no box at {'4:3' if old.box is None else label}"]
    a = old.box
    b = (new.box[0] * scale, new.box[1] * scale, new.box[2], new.box[3])
    out = []
    if abs((b[1] - b[0]) - (a[1] - a[0])) > TOLERANCE:
        out.append(f"width {a[1] - a[0]:.1f} to {b[1] - b[0]:.1f}")
    if abs((b[3] - b[2]) - (a[3] - a[2])) > TOLERANCE:
        out.append(f"height {a[3] - a[2]:.1f} to {b[3] - b[2]:.1f}")
    da = edge_distance(old.anchor, old.rect, a)
    db = edge_distance(new.anchor, (new.rect[0] * scale, new.rect[1] * scale), b)
    if abs(db - da) > TOLERANCE:
        out.append(f"{EDGES[old.anchor]} {da:.1f} to {db:.1f}")
    view = view_of(a, views)
    wide = (view[0] * scale, view[1], view[2] * scale, view[3])
    if (more := max(n - o for o, n in zip(overhangs(a, view), overhangs(b, wide)))) > TOLERANCE:
        out.append(f"leaves its view {view[0]:.0f},{view[1]:.0f} {view[2]:.0f}x{view[3]:.0f} by {more:.1f}")
    return out


def _box_text(label: str, box: Box | None, scale: float) -> str:
    if box is None:
        return f"{label} none"
    return f"{label} {box[0] * scale:.1f}..{box[1] * scale:.1f},{box[2]:.1f}..{box[3]:.1f}"


def pair_text(old: HudDraw | None, new: HudDraw | None, scale: float, label: str) -> str:
    shown = new or old
    head = (f"{old.index if old else ''}>{new.index if new else ''} {shown.kind} {shown.anchor_text} "
            f"{','.join(shown.textures) or 'untextured'}")
    boxes = [_box_text("4:3", old.box, 1.0)] if old else []
    return "  ".join([head, *boxes, *([_box_text(label, new.box, scale)] if new else [])])


def aspect_value(text: str) -> float | None:
    """W:H or a number as an aspect, None when it isn't one above 0."""
    w, colon, h = text.partition(":")
    try:
        value = float(w) / float(h) if colon else float(text)
    except (ValueError, ZeroDivisionError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def _missing(path: Path, draws: list[HudDraw]) -> str | None:
    if not draws:
        return f"{path}: no [draw] lines; was GCN_DRAWLOG=<frame> set?"
    if not any(d.anchor for d in draws):
        return f"{path}: no anchor= on its [draw] lines, which gcn-recomp prints from 5e49451 on"
    if not any(d.viewport for d in draws):
        return f"{path}: no viewport lines; was GCN_DRAWLOG_VERBOSE=1 set?"
    return None


def hud(args) -> int:
    output = aspect_value(args.aspect)
    if output is None:
        print(f"--aspect {args.aspect}: give W:H or a number above 0", file=sys.stderr)
        return 2
    logs = []
    for path in (args.old, args.new):
        try:
            with path.open(errors="replace") as lines:
                draws = read_draws(lines)
        except OSError as e:
            print(e, file=sys.stderr)
            return 2
        if problem := _missing(path, draws):
            print(problem, file=sys.stderr)
            return 2
        logs.append(draws)
    old, new = logs
    scale = output * SCREEN[3] / EFB_WIDTH
    views = world_views(old, new)
    anchored = failed = stretched = 0
    for o, n in pairs(hud_draws(old, new), hud_draws(new, old)):
        text = pair_text(o, n, scale, args.aspect)
        if not (o and o.anchored) and not (n and n.anchored):
            if o and n:
                stretched += 1
                print(f"{text}  stretched")
            continue
        anchored += 1
        if o and n:
            found = faults(o, n, scale, args.aspect, views)
        else:
            found = [f"no match at {args.aspect if o else '4:3'}"]
        failed += bool(found)
        print(f"{text}  FAIL {'; '.join(found)}" if found else f"{text}  ok")
    print(f"anchored {anchored}  failed {failed}  stretched {stretched}")
    return 1 if failed else 0
