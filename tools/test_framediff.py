import tempfile
import unittest
import zlib
from pathlib import Path

import framediff as fd


def paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def write_png(path, w, h, ch, pixels, filters):
    """Encode with the given filter type per row, independently of the decoder."""
    stride, raw, prev = w * ch, bytearray(), bytes(w * ch)
    for y in range(h):
        row, f = pixels[y * stride:(y + 1) * stride], filters[y % len(filters)]
        out = bytearray([f])
        for i in range(stride):
            a = row[i - ch] if i >= ch else 0
            b, c = prev[i], prev[i - ch] if i >= ch else 0
            pred = [0, a, b, (a + b) // 2, paeth(a, b, c)][f]
            out.append((row[i] - pred) & 255)
        raw += out
        prev = row

    def chunk(kind, body):
        return len(body).to_bytes(4, "big") + kind + body + zlib.crc32(kind + body).to_bytes(4, "big")

    ihdr = w.to_bytes(4, "big") + h.to_bytes(4, "big") + bytes([8, 6 if ch == 4 else 2, 0, 0, 0])
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                           + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))


class ReadPngTest(unittest.TestCase):
    def test_every_filter_round_trips(self):
        w, h, ch = 5, 5, 4
        pixels = bytes((x * 37 + y * 91 + k * 13) & 255
                       for y in range(h) for x in range(w) for k in range(ch))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "f.png")
            write_png(p, w, h, ch, pixels, [0, 1, 2, 3, 4])
            self.assertEqual(fd.read_png(p), (w, h, ch, pixels))


    def test_rejects_a_file_that_is_not_a_png(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "f.png")
            p.write_bytes(b"not a png at all")
            with self.assertRaisesRegex(ValueError, "not a PNG"):
                fd.read_png(p)


class DiffTest(unittest.TestCase):
    def test_counts_pixels_over_tolerance_and_ignores_alpha(self):
        a = (2, 1, 4, bytes([10, 10, 10, 0, 10, 10, 10, 0]))
        b = (2, 1, 4, bytes([13, 10, 10, 255, 10, 10, 14, 0]))
        self.assertEqual(fd.diff(a, b, 3), (2, 1, 4))

    def test_rgb_against_rgba(self):
        a = (1, 1, 3, bytes([1, 2, 3]))
        b = (1, 1, 4, bytes([1, 2, 3, 9]))
        self.assertEqual(fd.diff(a, b, 0), (1, 0, 0))


if __name__ == "__main__":
    unittest.main()
