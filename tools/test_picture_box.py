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

    def test_bad_arguments_exit_2(self):
        path = self.png("a.png", 2, 2, lambda x, y: CREAM)
        for extra in (["--color", "FF80"], ["--color", "GG8000"], ["--dark", "256"], ["--within", "-1"]):
            with self.subTest(extra=extra):
                code, _, _ = run_main(picture_box.main, path, *extra)
                self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
