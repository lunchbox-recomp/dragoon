"""What does a changed frame look like beside its golden? It puts two frame dumps side by side in
one PNG, the golden on the left and the new frame on the right, with a gap between them.

`side_by_side(left, right)` takes framediff.py's Image records, RGB or RGBA, and returns an RGB
Image as wide as both and the gap, as tall as the taller, the rest of it black. `write_png`
encodes an Image as an 8-bit PNG without filters. It has no command line.
"""
from __future__ import annotations

import struct
import zlib

from framediff import Image

GAP = 8  # black pixels between the two frames


def rgb(image: Image) -> bytes:
    """IMAGE's pixels as RGB, alpha dropped."""
    if image.channels == 3:
        return image.pixels
    px = image.pixels
    return b"".join(px[i:i + 3] for i in range(0, len(px), 4))


def side_by_side(left: Image, right: Image, gap: int = GAP) -> Image:
    width = left.width + gap + right.width
    height = max(left.height, right.height)
    a, b = rgb(left), rgb(right)
    rows = []
    for y in range(height):
        row = a[y * left.width * 3:(y + 1) * left.width * 3] if y < left.height else bytes(left.width * 3)
        rows.append(row + bytes(gap * 3)
                    + (b[y * right.width * 3:(y + 1) * right.width * 3] if y < right.height
                       else bytes(right.width * 3)))
    return Image(width, height, 3, b"".join(rows))


def _chunk(tag: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))


def write_png(image: Image) -> bytes:
    """IMAGE as a PNG: RGB or RGBA by its channels, 8 bits, every row unfiltered."""
    kind = {3: 2, 4: 6}[image.channels]
    stride = image.width * image.channels
    raw = b"".join(b"\0" + image.pixels[y * stride:(y + 1) * stride] for y in range(image.height))
    header = struct.pack(">IIBBBBB", image.width, image.height, 8, kind, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(raw, 6))
            + _chunk(b"IEND", b""))
