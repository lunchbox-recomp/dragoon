import unittest

import picture_box
from test_framediff import write_png
from testutil import run_main, temp_dir, write_file

BLACK, CREAM, ORANGE = (0, 0, 0), (250, 230, 160), (255, 128, 0)


def pixels(w: int, h: int, paint) -> bytes:
    """RGB pixels, PAINT(x, y) giving each one's colour."""
    return bytes(c for y in range(h) for x in range(w) for c in paint(x, y))


class PictureBoxTest(unittest.TestCase):
    def setUp(self):
        self.dir = temp_dir(self)

    def png(self, name: str, w: int, h: int, paint) -> str:
        path = self.dir / name
        write_png(path, w, h, 3, pixels(w, h, paint), [0, 1, 4])
        return str(path)

    def test_a_centered_4_3_picture_between_bars(self):
        # 16 by 9 with a 12 by 9 picture: bars of 2 at each side
        path = self.png("wide.png", 16, 9, lambda x, y: CREAM if 2 <= x < 14 else BLACK)
        code, out, _ = run_main(picture_box.main, path)
        self.assertEqual(code, 0)
        self.assertEqual(out, f"{path}: 16x9, box 2..14 by 0..9, 12x9, ratio 1.3333, bars 2 and 2\n")

    def test_a_stretched_picture_has_no_bars(self):
        path = self.png("stretched.png", 16, 9, lambda x, y: CREAM)
        _, out, _ = run_main(picture_box.main, path)
        self.assertIn("box 0..16 by 0..9, 16x9, ratio 1.7778, bars 0 and 0", out)

    def test_dark_sets_what_counts_as_lit(self):
        dim = (16, 16, 16)
        path = self.png("dim.png", 8, 4, lambda x, y: dim if x < 2 else CREAM if x < 6 else BLACK)
        _, out, _ = run_main(picture_box.main, path)
        self.assertIn("box 2..6 by 0..4", out)
        _, out, _ = run_main(picture_box.main, path, "--dark", "15")
        self.assertIn("box 0..6 by 0..4", out)

    def test_an_rgba_dump_reads_four_bytes_a_pixel(self):
        # The window's dumps are RGBA. The alpha isn't opaque and decides nothing: the bars are
        # black at full alpha and the picture is cream at a quarter.
        w, h = 8, 3
        data = bytes(c for y in range(h) for x in range(w)
                     for c in ((*CREAM, 64) if 2 <= x < 5 else (*BLACK, 255)))
        path = self.dir / "rgba.png"
        write_png(path, w, h, 4, data, [0, 1, 4])
        code, out, _ = run_main(picture_box.main, str(path))
        self.assertEqual(code, 0)
        self.assertEqual(out, f"{path}: 8x3, box 2..5 by 0..3, 3x3, ratio 1.0000, bars 2 and 3\n")

    def test_the_box_takes_every_rows_extent(self):
        # 15 wide, the rows lit over different spans with the widest in the middle, so the box
        # reaches past the first and last lit rows' ends, with bars of 2 and 1.
        spans = {1: (4, 10), 2: (2, 14), 3: (5, 8)}

        def paint(x, y):
            lo, hi = spans.get(y, (0, 0))
            return CREAM if lo <= x < hi else BLACK

        path = self.png("rows.png", 15, 6, paint)
        _, out, _ = run_main(picture_box.main, path)
        self.assertEqual(out, f"{path}: 15x6, box 2..14 by 1..4, 12x3, ratio 4.0000, bars 2 and 1\n")

    def test_color_boxes_one_element(self):
        def paint(x, y):
            return ORANGE if 3 <= x < 7 and 1 <= y < 4 else CREAM

        path = self.png("button.png", 10, 6, paint)
        _, out, _ = run_main(picture_box.main, path, "--color", "FF8000")
        self.assertIn("box 3..7 by 1..4, 4x3, ratio 1.3333", out)
        _, out, _ = run_main(picture_box.main, path, "--color", "F07808")
        self.assertIn("no pixel matched", out)
        _, out, _ = run_main(picture_box.main, path, "--color", "F07808", "--within", "15")
        self.assertIn("box 3..7 by 1..4", out)

    def test_color_checks_each_channel_to_within(self):
        # ORANGE is FF8000. Off by 9 in G alone or in B alone is past the default --within of 8,
        # and off by 8 in each is within it.
        path = self.png("button.png", 10, 6, lambda x, y: ORANGE if 3 <= x < 7 and 1 <= y < 4 else BLACK)
        for color in ("FF8900", "FF8009"):
            with self.subTest(color=color):
                _, out, _ = run_main(picture_box.main, path, "--color", color)
                self.assertEqual(out, f"{path}: 10x6, no pixel matched\n")
        _, out, _ = run_main(picture_box.main, path, "--color", "F78808")
        self.assertIn("box 3..7 by 1..4", out)

    def test_a_dark_image_matches_nothing(self):
        path = self.png("dark.png", 4, 3, lambda x, y: BLACK)
        code, out, _ = run_main(picture_box.main, path)
        self.assertEqual(code, 0)
        self.assertEqual(out, f"{path}: 4x3, no pixel matched\n")

    def test_one_line_per_png(self):
        a = self.png("a.png", 4, 3, lambda x, y: CREAM)
        b = self.png("b.png", 4, 3, lambda x, y: CREAM if x else BLACK)
        _, out, _ = run_main(picture_box.main, a, b)
        self.assertEqual([line.split(":")[0] for line in out.splitlines()], [a, b])

    def test_an_unreadable_png_exits_2_naming_it(self):
        bad = write_file(self.dir, "bad.png", b"not a png")
        code, _, err = run_main(picture_box.main, str(bad))
        self.assertEqual(code, 2)
        self.assertIn("bad.png", err)

    def test_a_missing_file_or_a_directory_exits_2_naming_it(self):
        for path in (self.dir / "missing.png", self.dir):
            with self.subTest(path=path):
                code, out, err = run_main(picture_box.main, str(path))
                self.assertEqual((code, out), (2, ""))
                self.assertIn(str(path), err)

    def test_bad_arguments_exit_2(self):
        path = self.png("a.png", 2, 2, lambda x, y: CREAM)
        for extra in (["--color", "FF80"], ["--color", "GG8000"], ["--dark", "256"], ["--within", "-1"]):
            with self.subTest(extra=extra):
                code, _, _ = run_main(picture_box.main, path, *extra)
                self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
