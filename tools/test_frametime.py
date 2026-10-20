import unittest

import frametime as ft


def ft_line(n: int, ms: float = 16.67, shape: str = "draws  462/ 167  verts  12419  idx  33993") -> str:
    return (f"[ft] f{n} guest  {ms:.2f}ms  fe   1.20ms (tex  0.10)  {shape}  states  120"
            f"  newtex   2 (16KB)  queue 0")


def rt_line(n: int, ms: float = 2.0) -> str:
    return f"[rt] f{n} render  {ms:.2f}ms (tex  0.20 vbo  0.30 copies  0.10)  applies  161  programs 31"


def compiled(ms: float) -> str:
    return f"[shaders] compiled program 31 in {ms:.1f} ms"


class ParseTest(unittest.TestCase):
    def test_shaders_belong_to_next_render_line_across_ft_lines(self):
        frames = ft.parse([ft_line(9), compiled(14.0), ft_line(10), compiled(3.5), rt_line(10, 20.0),
                           rt_line(11)])
        self.assertEqual(frames[10].compiles, [14.0, 3.5])
        self.assertEqual(frames[11].compiles, [])
        self.assertEqual(frames[10].guest_ms, 16.67)
        self.assertEqual(frames[10].render_ms, 20.0)

    def test_render_line_takes_the_batch_of_the_ft_line_before(self):
        shape_a = "draws  1/ 2  verts  3  idx  4"
        shape_b = "draws  5/ 6  verts  7  idx  8"
        frames = ft.parse([ft_line(9, shape=shape_a), ft_line(10, shape=shape_b),
                           compiled(5.0), rt_line(10, 40.0)])
        self.assertEqual(frames[10].shape, "draws 1/2 verts 3 idx 4")
        self.assertEqual((frames[10].render_ms, frames[10].compiles), (40.0, [5.0]))
        self.assertEqual(frames[11].shape, "draws 5/6 verts 7 idx 8")

    def test_cut_off_last_line_is_skipped(self):
        frames = ft.parse([ft_line(38), rt_line(39), "[rt] f40", "[ft] f39 guest  16.6"])
        self.assertEqual(sorted(frames), [39])

    def test_lines_cut_off_mid_number_are_skipped(self):
        cut_ft = "[ft] f5 guest  16.67ms  fe   1.20ms (tex  0.10)  draws  462/ 167  verts  12419  idx  339"
        self.assertEqual(ft.parse([cut_ft]), {})
        self.assertEqual(ft.parse(["[rt] f40 render  1"]), {})

    def test_shape_normalizes_spaces(self):
        frames = ft.parse([ft_line(0)])
        self.assertEqual(frames[1].shape, "draws 462/167 verts 12419 idx 33993")

    def test_background_build_is_not_a_stall(self):
        frames = ft.parse(["[shaders] built program 7 in the background", compiled(5.0), rt_line(2)])
        self.assertEqual(frames[2].compiles, [5.0])


class StatsTest(unittest.TestCase):
    def test_percentile_nearest_rank(self):
        self.assertEqual(ft.percentile(list(range(1, 101)), 99), 99)
        self.assertEqual(ft.percentile([5], 50), 5)

    def test_summary_leaves_out_frames_before_start(self):
        frames = ft.parse([ft_line(0, 100.0), rt_line(1, 90.0), ft_line(4, 10.0), rt_line(5, 2.0)])
        s = ft.summary(frames, 5)
        self.assertEqual(s["guest"]["n"], 1)
        self.assertEqual(s["guest"]["worst"], 10.0)
        self.assertEqual(s["render"]["worst"], 2.0)

    def test_summary_of_nothing(self):
        self.assertEqual(ft.summary({}, 0), {"guest": {"n": 0}, "render": {"n": 0}})

    def test_slow_returns_frames_over_threshold_in_order(self):
        frames = ft.parse([rt_line(9, 30.0), rt_line(3, 5.0), rt_line(7, 17.0), rt_line(2, 50.0)])
        self.assertEqual([n for n, _ in ft.slow(frames, 3, 16.7)], [7, 9])


if __name__ == "__main__":
    unittest.main()
