#!/usr/bin/env python3
"""Compare two directories of frame dumps pixel by pixel.

Usage: framediff.py DIR_A DIR_B [--tolerance 3] [--budget 0.001]

For every frame_NNNNN.png in both, prints the share of pixels whose largest RGB difference
is over the tolerance, and the largest difference seen. Exits 1 if any frame's share is
over the budget. Alpha isn't compared.
"""
from __future__ import annotations

import argparse
import re
import sys
import zlib
from pathlib import Path

FRAME = re.compile(r"frame_(\d+)\.png$")


def read_png(path: Path) -> tuple[int, int, int, bytes]:
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: not a PNG")
    pos, ihdr, idat = 8, b"", []
    while pos < len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        kind, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            ihdr = body
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    w, h = int.from_bytes(ihdr[0:4], "big"), int.from_bytes(ihdr[4:8], "big")
    depth, ctype, interlace = ihdr[8], ihdr[9], ihdr[12]
    if depth != 8 or ctype not in (2, 6) or interlace:
        raise ValueError(f"{path}: only 8-bit RGB or RGBA without interlacing")
    ch = 3 if ctype == 2 else 4
    raw = zlib.decompress(b"".join(idat))
    stride = w * ch
    if len(raw) != h * (stride + 1):
        raise ValueError(f"{path}: truncated image data")
    out =bytearray(h * stride)
    prev = bytearray(stride)
    for y in range(h):
        start = y * (stride + 1)
        f, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        if f:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                if f == 1:
                    pred = a
                elif f == 2:
                    pred = b
                elif f == 3:
                    pred = (a + b) // 2
                else:
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pred = a if pa <= pb and pa <= pc else b if pb <= pc else c
                line[i] = (line[i] + pred) & 255
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, ch, bytes(out)


def diff(a: tuple[int, int, int, bytes], b: tuple[int, int, int, bytes],
         tolerance: int) -> tuple[int, int, int]:
    wa, ha, ca, pa = a
    wb, hb, cb, pb = b
    if (wa, ha) != (wb, hb):
        raise ValueError(f"sizes differ: {wa}x{ha} and {wb}x{hb}")
    over = worst = 0
    for i in range(wa * ha):
        d = max(abs(pa[i * ca + k] - pb[i * cb + k]) for k in range(3))
        if d > worst:
            worst = d
        if d > tolerance:
            over += 1
    return wa * ha, over, worst


def frames(directory: Path) -> dict[int, Path]:
    return {int(m.group(1)): p for p in directory.iterdir() if (m := FRAME.search(p.name))}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Compare two directories of frame dumps.")
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--tolerance", type=int, default=3)
    ap.add_argument("--budget", type=float, default=0.001)
    args = ap.parse_args(argv)
    fa, fb = frames(args.a), frames(args.b)
    common = sorted(fa.keys() & fb.keys())
    if not common:
        print("no frames in common", file=sys.stderr)
        return 2
    only_a, only_b = len(fa.keys() - fb.keys()), len(fb.keys() - fa.keys())
    if only_a or only_b:
        print(f"only in A: {only_a}, only in B: {only_b}", file=sys.stderr)
    failed = 0
    for f in common:
        try:
            pixels, over, worst = diff(read_png(fa[f]), read_png(fb[f]), args.tolerance)
        except ValueError as e:
            print(f"frame {f}: {e}", file=sys.stderr)
            return 2
        share = over / pixels
        bad = share > args.budget
        failed += bad
        print(f"frame {f}: {share:.4%} over {args.tolerance}, worst {worst}{'  FAIL' if bad else ''}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
