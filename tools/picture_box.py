#!/usr/bin/env python3
"""Where does the picture sit in an output dump, and what shape is it?

Usage: picture_box.py PNG [PNG ...] [--dark N] [--color RRGGBB [--within N]]

For each PNG, an output_NNNNN.png from probe.sh --output or any 8-bit RGB or RGBA PNG, prints
the box holding every lit pixel, one whose largest RGB value is over --dark (default 16). The
columns left and right of it are the bars, and a picture centered at its own 4:3 shape in a
wider window has a box whose width over its height is 4:3 with bars of equal width.

--color RRGGBB boxes the pixels within --within (default 8) of that colour in each of R, G and B
instead, which measures one element, such as a button's outline, so its shape can be compared
with the same element in a 4:3 dump.

Each line gives the image's size, the box as left..right by top..bottom with the right and
bottom edges exclusive, its width and height, their ratio to four figures and the bars' widths,
or says no pixel matched. The tool only reports, so it exits 0 once it has read every PNG, and
2 on a bad argument or a file it can't read or doesn't understand.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple

from framediff import Image, read_png


class Box(NamedTuple):
    x0: int
    x1: int
    y0: int
    y1: int


def box_of(image: Image, keep) -> Box | None:
    """The smallest box holding every pixel KEEP(r, g, b) is true of, or None for none."""
    w, ch, px = image.width, image.channels, image.pixels
    x0, x1, y0, y1 = w, -1, image.height, -1
    for y in range(image.height):
        row = y * w * ch
        first = last = -1
        for x in range(w):
            i = row + x * ch
            if keep(px[i], px[i + 1], px[i + 2]):
                if first < 0:
                    first = x
                last = x
        if first >= 0:
            x0, x1 = min(x0, first), max(x1, last)
            y0 = min(y0, y)
            y1 = y
    return None if x1 < 0 else Box(x0, x1 + 1, y0, y1 + 1)


def lit(dark: int):
    return lambda r, g, b: max(r, g, b) > dark


def near(color: tuple[int, int, int], within: int):
    cr, cg, cb = color
    return lambda r, g, b: abs(r - cr) <= within and abs(g - cg) <= within and abs(b - cb) <= within


def describe(name: str, image: Image, box: Box | None) -> str:
    size = f"{name}: {image.width}x{image.height}"
    if box is None:
        return f"{size}, no pixel matched"
    bw, bh = box.x1 - box.x0, box.y1 - box.y0
    return (f"{size}, box {box.x0}..{box.x1} by {box.y0}..{box.y1}, {bw}x{bh}, ratio {bw / bh:.4f}, "
            f"bars {box.x0} and {image.width - box.x1}")


def color_arg(text: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", text):
        raise argparse.ArgumentTypeError(f"not RRGGBB: {text!r}")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def byte_arg(text: str) -> int:
    if not re.fullmatch(r"[0-9][0-9]?[0-9]?", text) or int(text) > 255:
        raise argparse.ArgumentTypeError(f"not a whole number from 0 to 255: {text!r}")
    return int(text)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pngs", type=Path, nargs="+")
    ap.add_argument("--dark", type=byte_arg, default=16)
    ap.add_argument("--color", type=color_arg)
    ap.add_argument("--within", type=byte_arg, default=8)
    args = ap.parse_args(argv)
    keep = near(args.color, args.within) if args.color else lit(args.dark)
    for path in args.pngs:
        try:
            image = read_png(path)
        except (OSError, ValueError) as e:
            print(e, file=sys.stderr)
            return 2
        print(describe(str(path), image, box_of(image, keep)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
