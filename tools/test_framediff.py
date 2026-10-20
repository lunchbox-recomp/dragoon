import tempfile
import unittest
import zlib
from pathlib import Path

import framediff
from testutil import run_main, write_file

JUNK = object()
SIGNATURE = b"\x89PNG\r\n\x1a\n"


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
    Path(path).write_bytes(SIGNATURE + chunk(b"IHDR", ihdr) + idat + chunk(b"IEND", b""))


class TempDirTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)


class ReadPngTest(TempDirTest):
    def test_every_filter_round_trips(self):
        w, h, ch = 5, 5, 4
        pixels = bytes((x * 37 + y * 91 + k * 13) & 255
                       for y in range(h) for x in range(w) for k in range(ch))
        p = self.dir / "f.png"
        write_png(p, w, h, ch, pixels, [0, 1, 2, 3, 4])
        self.assertEqual(framediff.read_png(p), (w, h, ch, pixels))

    def test_three_channel_round_trips(self):
        w, h, ch = 4, 3, 3
        pixels = bytes((x * 41 + y * 17 + k * 29) & 255
                       for y in range(h) for x in range(w) for k in range(ch))
        p = self.dir / "f.png"
        write_png(p, w, h, ch, pixels, [4, 3, 2, 1, 0])
        self.assertEqual(framediff.read_png(p), (w, h, ch, pixels))

    def test_paeth_ties_pick_the_left_then_the_above_neighbour(self):
        # Row 0 holds c then b, row 1 holds a then the pixel under test.
        for label, (a, b, c) in (("left wins", (8, 11, 10)), ("above wins", (11, 8, 10))):
            pixels = bytes([c] * 3 + [b] * 3 + [a] * 3 + [100] * 3)
            p = self.dir / f"{label}.png"
            write_png(p, 2, 2, 3, pixels, [0, 4])
            with self.subTest(label):
                self.assertEqual(framediff.read_png(p).pixels, pixels)

    def test_sub_filter_reads_the_first_pixel_of_a_two_wide_row(self):
        pixels = bytes([9, 9, 9, 40, 40, 40])
        p = self.dir / "f.png"
        write_png(p, 2, 1, 3, pixels, [1])
        self.assertEqual(framediff.read_png(p).pixels, pixels)

    def test_image_data_split_across_idat_chunks(self):
        pixels = bytes(range(12))
        p = self.dir / "f.png"
        write_png(p, 2, 2, 3, pixels, [0], split=True)
        self.assertEqual(framediff.read_png(p), (2, 2, 3, pixels))

    def test_rejects_16_bit(self):
        p = self.dir / "f.png"
        write_png(p, 1, 1, 3, bytes(3), [0], depth=16)
        with self.assertRaisesRegex(ValueError, "8-bit"):
            framediff.read_png(p)

    def test_rejects_truncated_data(self):
        p = self.dir / "f.png"
        write_png(p, 2, 2, 3, bytes(12), [0], rows=1)
        with self.assertRaisesRegex(ValueError, "truncated"):
            framediff.read_png(p)

    def test_rejects_a_file_that_is_not_a_png(self):
        p = write_file(self.dir, "f.png", b"not a png at all")
        with self.assertRaisesRegex(ValueError, "not a PNG"):
            framediff.read_png(p)

    def test_rejects_a_file_cut_off_in_the_middle(self):
        whole = self.dir / "whole.png"
        write_png(whole, 8, 8, 3, bytes(range(192)), [0])
        data = whole.read_bytes()
        p = write_file(self.dir, "cut.png", data[:len(data) * 3 // 4])
        with self.assertRaisesRegex(ValueError, "cut.png"):
            framediff.read_png(p)

    def test_rejects_a_signature_with_nothing_after_it(self):
        p = write_file(self.dir, "f.png", SIGNATURE)
        with self.assertRaisesRegex(ValueError, "IHDR"):
            framediff.read_png(p)


class DiffTest(unittest.TestCase):
    def test_counts_pixels_over_tolerance_and_ignores_alpha(self):
        a = framediff.Image(2, 1, 4, bytes([10, 10, 10, 0, 10, 10, 10, 0]))
        b = framediff.Image(2, 1, 4, bytes([13, 10, 10, 255, 10, 10, 14, 0]))
        self.assertEqual(framediff.diff(a, b, 3), (2, 1, 4))

    def test_rgb_against_rgba(self):
        a = framediff.Image(1, 1, 3, bytes([1, 2, 3]))
        b = framediff.Image(1, 1, 4, bytes([1, 2, 3, 9]))
        self.assertEqual(framediff.diff(a, b, 0), (1, 0, 0))

    def test_different_sizes_are_refused(self):
        with self.assertRaisesRegex(ValueError, "a.png and b.png: sizes differ"):
            framediff.diff(framediff.Image(1, 1, 3, bytes(3)), framediff.Image(2, 1, 3, bytes(6)), 0,
                           "a.png and b.png")


class MainTest(TempDirTest):
    def run_dirs(self, files_a, files_b, *extra):
        """files_* map a file name to its 2x1 RGB pixel bytes, or JUNK for a file that isn't a PNG."""
        dirs = []
        for name, files in (("a", files_a), ("b", files_b)):
            sub = self.dir / name
            sub.mkdir()
            for fname, pixels in files.items():
                if pixels is JUNK:
                    write_file(sub, fname, b"junk")
                else:
                    write_png(sub / fname, 2, 1, 3, pixels, [0])
            dirs.append(str(sub))
        return run_main(framediff.main, *dirs, *extra)

    def test_within_tolerance_exits_0(self):
        code, out, _ = self.run_dirs({"frame_00001.png": bytes([5] * 6)}, {"frame_00001.png": bytes([6] * 6)})
        self.assertEqual(code, 0)
        self.assertIn("frame 1: 0.0000%", out)

    def test_over_budget_exits_1(self):
        code, out, _ = self.run_dirs({"frame_00001.png": bytes([5] * 6)}, {"frame_00001.png": bytes([50] * 6)})
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out)

    def test_share_equal_to_the_budget_passes(self):
        half = bytes([5, 5, 5, 50, 50, 50])
        code, out, _ = self.run_dirs({"frame_00001.png": bytes([5] * 6)}, {"frame_00001.png": half},
                                     "--budget", "0.5")
        self.assertEqual(code, 0)
        self.assertNotIn("FAIL", out)

    def test_last_line_counts_frames_and_failures(self):
        a = {"frame_00001.png": bytes([5] * 6), "frame_00002.png": bytes([5] * 6)}
        b = {"frame_00001.png": bytes([5] * 6), "frame_00002.png": bytes([50] * 6)}
        _, out, _ = self.run_dirs(a, b)
        self.assertEqual(out.splitlines()[-1], "2 frames compared, 1 over budget, worst 45")

    def test_bad_png_exits_2_naming_the_frame(self):
        code, _, err = self.run_dirs({"frame_00007.png": bytes(6)}, {"frame_00007.png": JUNK})
        self.assertEqual(code, 2)
        self.assertIn("frame 7:", err)

    def test_unmatched_frames_warn_on_stderr_without_failing(self):
        code, _, err = self.run_dirs({"frame_00001.png": bytes(6), "frame_00002.png": bytes(6)},
                                     {"frame_00001.png": bytes(6)})
        self.assertEqual(code, 0)
        self.assertIn("only in A: 1, only in B: 0", err)

    def test_missing_directory_exits_2_with_one_line_naming_it(self):
        code, _, err = run_main(framediff.main, str(self.dir / "nope"), str(self.dir))
        self.assertEqual(code, 2)
        self.assertIn("nope", err)
        self.assertEqual(len(err.splitlines()), 1)

    def test_help_exits_0_and_prints_usage(self):
        code, out, _ = run_main(framediff.main, "--help")
        self.assertEqual(code, 0)
        self.assertIn("Usage:", out)


if __name__ == "__main__":
    unittest.main()
