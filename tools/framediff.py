#!/usr/bin/env python3
"""Do two runs draw the same pixels? Compare two directories of frame dumps.

Usage: framediff.py DIR_A DIR_B [--tolerance 3] [--budget 0.001]

For every frame_NNNNN.png in both, prints the share of pixels whose largest RGB difference
is over the tolerance (default 3) and the largest difference seen, then one summary line.
Frames only one directory has are counted on stderr and don't fail the diff. Alpha isn't
compared. A frame fails when its share is over the budget (default 0.001).

Exits 0 when every frame is within the budget, 1 when one is over it, 2 on a bad argument or
an unreadable directory or PNG.
"""
from __future__ import annotations

import argparse
import sys
import zlib
from pathlib import Path
from typing import NamedTuple

from frame_dumps import frame_files


class Image(NamedTuple):
    width: int
    height: int
    channels: int
    pixels: bytes


def read_png(path: Path) -> Image:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: not a PNG")
    pos, ihdr, idat = 8, b"", []
    while pos < len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        tag, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            ihdr = body
        elif tag == b"IDAT":
            idat.append(body)
        elif tag == b"IEND":
            break
    if len(ihdr) != 13:
        raise ValueError(f"{path}: no IHDR chunk")
    w, h = int.from_bytes(ihdr[0:4], "big"), int.from_bytes(ihdr[4:8], "big")
    depth, ctype, interlace = ihdr[8], ihdr[9], ihdr[12]
    if depth != 8 or ctype not in (2, 6) or interlace:
        raise ValueError(f"{path}: only 8-bit RGB or RGBA without interlacing")
    ch = 3 if ctype == 2 else 4
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error as e:
        raise ValueError(f"{path}: {e}") from None
    stride = w * ch
    if len(raw) != h * (stride + 1):
        raise ValueError(f"{path}: truncated image data")
    out = bytearray(h * stride)
    prev = bytearray(stride)
    for y in range(h):
        start = y * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        if kind:
            # a, b and c are the PNG spec's names: left, above and above-left.
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                if kind == 1:
                    pred = a
                elif kind == 2:
                    pred = b
                elif kind == 3:
                    pred = (a + b) // 2
                else:
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pred = a if pa <= pb and pa <= pc else b if pb <= pc else c
                line[i] = (line[i] + pred) & 255
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return Image(w, h, ch, bytes(out))


def diff(a: Image, b: Image, tolerance: int, where: str = "images") -> tuple[int, int, int]:
    if (a.width, a.height) != (b.width, b.height):
        raise ValueError(f"{where}: sizes differ: {a.width}x{a.height} and {b.width}x{b.height}")
    over = worst = 0
    for i in range(a.width * a.height):
        d = max(abs(a.pixels[i * a.channels + k] - b.pixels[i * b.channels + k]) for k in range(3))
        if d > worst:
            worst = d
        if d > tolerance:
            over += 1
    return a.width * a.height, over, worst


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--tolerance", type=int, default=3)
    ap.add_argument("--budget", type=float, default=0.001)
    args = ap.parse_args(argv)
    try:
        fa, fb = frame_files(args.a), frame_files(args.b)
        common = sorted(fa.keys() & fb.keys())
        if not common:
            raise ValueError(f"{args.a} and {args.b}: no frames in common")
        only_a, only_b = len(fa.keys() - fb.keys()), len(fb.keys() - fa.keys())
        if only_a or only_b:
            print(f"only in A: {only_a}, only in B: {only_b}", file=sys.stderr)
        failed = worst = 0
        for n in common:
            try:
                pixels, over, frame_worst = diff(read_png(fa[n]), read_png(fb[n]), args.tolerance,
                                                  f"{fa[n]} and {fb[n]}")
            except ValueError as e:
                raise ValueError(f"frame {n}: {e}") from None
            share = over / pixels
            bad = share > args.budget
            failed += bad
            worst = max(worst, frame_worst)
            print(f"frame {n}: {share:.4%} over {args.tolerance}, worst {frame_worst}"
                  f"{'  FAIL' if bad else ''}")
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    print(f"{len(common)} frames compared, {failed} over budget, worst {worst}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
