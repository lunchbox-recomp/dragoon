"""The draw log's lines as GCN_DRAWLOG prints them, read for tools/drawlog.py and
tools/hud_boxes.py. A [draw] line starts with the draw's index and projection, and
GCN_DRAWLOG_VERBOSE=1 adds a viewport line under it."""
from __future__ import annotations

import re

NUM = r"-?[\d.]+(?:e[-+]?\d+)?"
DRAW = re.compile(rf"^\[draw\] (\d+) .*?proj=([po]),({NUM}),({NUM}),({NUM}),({NUM}),{NUM},{NUM}\s")
# The renderer prints a draw in pieces from its own thread, so a [census] line from the guest
# thread can land at the end of one of its lines. The pattern doesn't need the line to itself.
VIEWPORT = re.compile(rf"^\s+viewport=({NUM}),({NUM}),{NUM} ({NUM}),({NUM}),{NUM} "
                      r"scissor=\w+ \w+ offset=([0-9A-F]{6})")


def projection(m: re.Match) -> tuple[str, tuple[float, ...]]:
    """A DRAW match's projection kind, "persp" or "ortho", and GX's x scale, x offset, y scale
    and y offset."""
    return "persp" if m[2] == "p" else "ortho", tuple(float(x) for x in m.groups()[2:])


def viewport(m: re.Match) -> tuple[float, float, float, float]:
    """A VIEWPORT match's x, y, width and height in EFB pixels, with the scissor offset taken
    off."""
    sx, sy, ox, oy = (float(x) for x in m.groups()[:4])
    offset = int(m[5], 16)
    xoff, yoff = (offset & 0x3FF) * 2, ((offset >> 10) & 0x3FF) * 2
    return ox - xoff - abs(sx), oy - yoff - abs(sy), 2 * abs(sx), 2 * abs(sy)
