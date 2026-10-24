import json
import tempfile
import unittest
from pathlib import Path

import frametime
from testutil import run_main, write_file


def ft_line(n: int, ms: float = 16.67, shape: str = "draws  462/ 167  verts  12419  idx  33993") -> str:
    return (f"[ft] f{n} guest  {ms:.2f}ms  fe   1.20ms (tex  0.10)  {shape}  states  120"
            f"  newtex   2 (16KB)  queue 0")


def rt_line(n: int, ms: float = 2.0) -> str:
    return f"[rt] f{n} render  {ms:.2f}ms (tex  0.20 vbo  0.30 copies  0.10)  applies  161  programs 31"


def compiled(ms: float) -> str:
    return f"[shaders] compiled program 31 in {ms:.1f} ms"


class ParseTest(unittest.TestCase):
    def test_shaders_belong_to_next_render_line_across_ft_lines(self):
        frames = frametime.parse([ft_line(9), compiled(14.0), ft_line(10), compiled(3.5), rt_line(10, 20.0),
                                  rt_line(11)])
        self.assertEqual(frames[10].compiles, [14.0, 3.5])
        self.assertEqual(frames[11].compiles, [])
        self.assertEqual(frames[10].guest_ms, 16.67)
        self.assertEqual(frames[10].render_ms, 20.0)

    def test_render_line_takes_the_batch_of_the_ft_line_before(self):
        shape_a = "draws  1/ 2  verts  3  idx  4"
        shape_b = "draws  5/ 6  verts  7  idx  8"
        frames = frametime.parse([ft_line(9, shape=shape_a), ft_line(10, shape=shape_b),
                                  compiled(5.0), rt_line(10, 40.0)])
        self.assertEqual(frames[10].shape, "draws 1/2 verts 3 idx 4")
        self.assertEqual((frames[10].render_ms, frames[10].compiles), (40.0, [5.0]))
        self.assertEqual(frames[11].shape, "draws 5/6 verts 7 idx 8")

    def test_cut_off_last_line_is_skipped(self):
        frames = frametime.parse([ft_line(38), rt_line(39), "[rt] f40", "[ft] f39 guest  16.6"])
        self.assertEqual(sorted(frames), [39])

    def test_lines_cut_off_mid_number_are_skipped(self):
        cut_ft = "[ft] f5 guest  16.67ms  fe   1.20ms (tex  0.10)  draws  462/ 167  verts  12419  idx  339"
        self.assertEqual(frametime.parse([cut_ft]), {})
        self.assertEqual(frametime.parse(["[rt] f40 render  1"]), {})

    def test_shape_normalizes_spaces(self):
        frames = frametime.parse([ft_line(0)])
        self.assertEqual(frames[1].shape, "draws 462/167 verts 12419 idx 33993")

    def test_background_build_is_not_a_stall(self):
        frames = frametime.parse(["[shaders] built program 7 in the background", compiled(5.0), rt_line(2)])
        self.assertEqual(frames[2].compiles, [5.0])


class StatsTest(unittest.TestCase):
    def test_percentile_nearest_rank(self):
        self.assertEqual(frametime.percentile(list(range(1, 101)), 99), 99)
        self.assertEqual(frametime.percentile([5], 50), 5)

    def test_summary_leaves_out_frames_before_start(self):
        frames = frametime.parse([ft_line(0, 100.0), rt_line(1, 90.0), ft_line(4, 10.0), rt_line(5, 2.0)])
        s = frametime.summary(frames, 5)
        self.assertEqual(s["guest"]["n"], 1)
        self.assertEqual(s["guest"]["worst"], 10.0)
        self.assertEqual(s["render"]["worst"], 2.0)

    def test_sd_is_the_population_standard_deviation(self):
        frames = frametime.parse([ft_line(n, ms) for n, ms in enumerate([15.0, 17.0, 15.0, 17.0])])
        self.assertAlmostEqual(frametime.summary(frames, 0)["guest"]["sd"], 1.0)

    def test_render_and_guest_each_get_their_own_sd(self):
        frames = frametime.parse([ft_line(0, 15.0), ft_line(1, 17.0), rt_line(1, 2.0), rt_line(2, 6.0)])
        stats = frametime.summary(frames, 0)
        self.assertAlmostEqual(stats["guest"]["sd"], 1.0)
        self.assertAlmostEqual(stats["render"]["sd"], 2.0)

    def test_summary_of_nothing(self):
        self.assertEqual(frametime.summary({}, 0), {"guest": {"n": 0}, "render": {"n": 0}})

    def test_slow_returns_frames_over_threshold_in_order(self):
        frames = frametime.parse([rt_line(9, 30.0), rt_line(3, 5.0), rt_line(7, 17.0), rt_line(2, 50.0)])
        self.assertEqual([n for n, _ in frametime.slow(frames, 3, 16.7)], [7, 9])

    def test_a_frame_at_exactly_the_limit_is_not_slow(self):
        frames = frametime.parse([rt_line(5, 16.7), rt_line(6, 16.71)])
        self.assertEqual([n for n, _ in frametime.slow(frames, 0, 16.7)], [6])

    def test_late_returns_guest_intervals_over_the_limit_from_start_in_order(self):
        frames = frametime.parse([ft_line(1, 40.0), ft_line(2, 30.0), ft_line(8, 30.0), ft_line(3, 25.0), ft_line(5, 25.01),
                                  ft_line(6, 16.7)])
        self.assertEqual(frametime.late(frames, 3, 25.0), [(3, 30.0), (6, 25.01), (9, 30.0)])


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_prints_the_summary_and_slow_frames(self):
        log = write_file(self.dir, "stdout.txt", "\n".join([ft_line(9), rt_line(10, 40.0)]) + "\n")
        code, out, _ = run_main(frametime.main, str(log), "--from", "0")
        self.assertEqual(code, 0)
        self.assertIn("frames over 16.7 ms: 1", out)
        self.assertIn("f10  render 40.00 ms", out)

    def test_prints_the_sd_and_late_guest_intervals(self):
        log = write_file(self.dir, "stdout.txt", "\n".join([ft_line(9, 15.0), ft_line(10, 17.0),
                                                            ft_line(11, 30.0)]) + "\n")
        code, out, _ = run_main(frametime.main, str(log), "--from", "0", "--late", "20")
        self.assertEqual(code, 0)
        self.assertIn("mean 20.67  sd 6.650", out)
        self.assertIn("guest intervals over 20.0 ms: 1", out)
        self.assertIn("f12  guest 30.00 ms", out)

    def test_json_lists_guest_intervals_over_25_ms_by_default(self):
        log = write_file(self.dir, "stdout.txt", "\n".join([ft_line(9, 25.0), ft_line(10, 25.01)]) + "\n")
        code, out, _ = run_main(frametime.main, str(log), "--from", "0", "--json")
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["late"], [{"frame": 11, "guest_ms": 25.01}])
        self.assertAlmostEqual(result["summary"]["guest"]["sd"], 0.005)

    def test_a_log_with_no_guest_intervals_prints_no_late_count(self):
        log = write_file(self.dir, "stdout.txt", rt_line(10, 40.0) + "\n")
        code, out, _ = run_main(frametime.main, str(log), "--from", "0")
        self.assertEqual(code, 0)
        self.assertIn("frames over 16.7 ms: 1", out)
        self.assertNotIn("guest intervals", out)

    def test_missing_log_exits_2_with_one_line_naming_it(self):
        code, _, err = run_main(frametime.main, str(self.dir / "nope.txt"))
        self.assertEqual(code, 2)
        self.assertIn("nope.txt", err)
        self.assertEqual(len(err.splitlines()), 1)

    def test_log_without_frametime_lines_exits_2(self):
        log = write_file(self.dir, "stdout.txt", "nothing here\n")
        code, _, err = run_main(frametime.main, str(log))
        self.assertEqual(code, 2)
        self.assertIn("GCN_FRAMETIME=1", err)

    def test_from_past_the_end_exits_2(self):
        log = write_file(self.dir, "stdout.txt", rt_line(10) + "\n")
        code, _, err = run_main(frametime.main, str(log), "--from", "11")
        self.assertEqual(code, 2)
        self.assertIn("the log ends at frame 10", err)

    def test_help_exits_0_and_prints_usage(self):
        code, out, _ = run_main(frametime.main, "--help")
        self.assertEqual(code, 0)
        self.assertIn("Usage:", out)


if __name__ == "__main__":
    unittest.main()
