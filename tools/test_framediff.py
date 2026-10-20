import contextlib
import io
import tempfile
import unittest
import zlib
from pathlib import Path

import framediff as fd


def paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def write_png(path, w, h, ch, pixels, filters, split=False, depth=8, rows=None):
    """Encode with the given filter type per row, independently of the decoder.

    split puts the image data in two IDAT chunks, depth sets the header's bit depth and rows
    stops after that many rows.
    """
    stride, raw, prev = w * ch, bytearray(), bytes(w * ch)
    for y in range(h if rows is None else rows):
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

    ihdr = w.to_bytes(4, "big") + h.to_bytes(4, "big") + bytes([depth, 6 if ch == 4 else 2, 0, 0, 0])
    packed = zlib.compress(bytes(raw))
    cut = len(packed) // 2 if split else len(packed)
    idat = chunk(b"IDAT", packed[:cut]) + (chunk(b"IDAT", packed[cut:]) if split else b"")
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + idat + chunk(b"IEND", b""))


class ReadPngTest(unittest.TestCase):
    def test_every_filter_round_trips(self):
        w, h, ch = 5, 5, 4
        pixels = bytes((x * 37 + y * 91 + k * 13) & 255
                       for y in range(h) for x in range(w) for k in range(ch))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "f.png")
            write_png(p, w, h, ch, pixels, [0, 1, 2, 3, 4])
            self.assertEqual(fd.read_png(p), (w, h, ch, pixels))

    def test_three_channel_round_trips(self):
        w, h, ch = 4, 3, 3
        pixels = bytes((x * 41 + y * 17 + k * 29) & 255
                       for y in range(h) for x in range(w) for k in range(ch))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "f.png")
            write_png(p, w, h, ch, pixels, [4, 3, 2, 1, 0])
            self.assertEqual(fd.read_png(p), (w, h, ch, pixels))

    def test_image_data_split_across_idat_chunks(self):
        pixels = bytes(range(12))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "f.png")
            write_png(p, 2, 2, 3, pixels, [0], split=True)
            self.assertEqual(fd.read_png(p), (2, 2, 3, pixels))

    def test_rejects_16_bit(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "f.png")
            write_png(p, 1, 1, 3, bytes(3), [0], depth=16)
            with self.assertRaisesRegex(ValueError, "8-bit"):
                fd.read_png(p)

    def test_rejects_truncated_data(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "f.png")
            write_png(p, 2, 2, 3, bytes(12), [0], rows=1)
            with self.assertRaisesRegex(ValueError, "truncated"):
                fd.read_png(p)

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


class MainTest(unittest.TestCase):
    def run_main(self, files_a, files_b, *extra):
        """files_* map a file name to its first pixel byte; returns (exit code, stdout, stderr)."""
        with tempfile.TemporaryDirectory() as d:
            dirs = []
            for name, files in (("a", files_a), ("b", files_b)):
                sub = Path(d, name)
                sub.mkdir()
                for fname, value in files.items():
                    if value is None:
                        sub.joinpath(fname).write_bytes(b"junk")
                    else:
                        write_png(sub / fname, 2, 1, 3, bytes([value] * 6), [0])
                dirs.append(str(sub))
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = fd.main([*dirs, *extra])
            return code, out.getvalue(), err.getvalue()

    def test_matching_dirs_exit_0(self):
        code, out, _ = self.run_main({"frame_00001.png": 5}, {"frame_00001.png": 6})
        self.assertEqual(code, 0)
        self.assertIn("frame 1: 0.0000%", out)

    def test_over_budget_exits_1(self):
        code, out, _ = self.run_main({"frame_00001.png": 5}, {"frame_00001.png": 50})
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out)

    def test_bad_png_exits_2_naming_the_frame(self):
        code, _, err = self.run_main({"frame_00007.png": 5}, {"frame_00007.png": None})
        self.assertEqual(code, 2)
        self.assertIn("frame 7:", err)

    def test_frames_in_one_dir_are_reported(self):
        code, _, err = self.run_main({"frame_00001.png": 5, "frame_00002.png": 5},
                                     {"frame_00001.png": 5})
        self.assertEqual(code, 0)
        self.assertIn("only in A: 1, only in B: 0", err)


if __name__ == "__main__":
    unittest.main()
