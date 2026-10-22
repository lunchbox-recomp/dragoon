import tempfile
import unittest
from pathlib import Path

import ax_stats
from testutil import run_main, write_file

PB = ("[ax] pb list={n} voice_ms={v} mixer=0011:828,0022:828 mixer_rest=3 src0={s0} src1=0 src2=5 "
      "src_other=0 src0_coef={s0}/0/1/0 delay=2 stream_loops=0 lpf=0 ramp=7 env_ramp=1")
BUS = ("[ax] bus list={n} main_l={pk} main_r=9 main_s=0 auxa_l=0 auxa_r=0 auxa_s=0 auxb_l=0 auxb_r=0 "
       "auxb_s=0 clipped=4 depop={d}")


def run_text(*windows: tuple[int, int, int, int]) -> str:
    lines = ["[ax] frames=400 voices(running, last frame)=3 peak=100 out=80571E00", "unrelated src0=999"]
    for n, (v, s0, pk, d) in enumerate(windows, 1):
        lines += [PB.format(n=400 * n, v=v, s0=s0), BUS.format(n=400 * n, pk=pk, d=d),
                  f"[ax] hash list={400 * n} fnv=0123456789ABCDEF"]
    return "\n".join(lines) + "\n"


class TotalsTest(unittest.TestCase):
    def test_counts_sum_and_peaks_take_the_largest_window(self):
        t = ax_stats.totals(run_text((10, 6, 500, 1), (20, 8, 300, 0)))
        self.assertEqual(t["windows"], 2)
        self.assertEqual((t["voice_ms"], t["src0"], t["src2"], t["ramp"]), (30, 14, 10, 14))
        self.assertEqual((t["clipped"], t["depop"]), (8, 1))
        self.assertEqual(t["main_l"], 500)

    def test_coefficient_sets_split_and_mixer_values_are_left_out(self):
        t = ax_stats.totals(run_text((10, 6, 0, 0), (10, 4, 0, 0)))
        self.assertEqual([t[f"src0_coef{i}"] for i in range(4)], [10, 0, 2, 0])
        self.assertNotIn("mixer", t)
        self.assertNotIn("src0_coef", t)
        self.assertEqual(t["mixer_rest"], 6)

    def test_until_stops_at_that_list(self):
        t = ax_stats.totals(run_text((10, 6, 500, 1), (20, 8, 300, 0), (40, 1, 900, 5)), until=800)
        self.assertEqual((t["windows"], t["voice_ms"], t["depop"], t["main_l"]), (2, 30, 1, 500))

    def test_only_ax_pb_and_bus_lines_count(self):
        t = ax_stats.totals(run_text((1, 1, 1, 1)))
        self.assertEqual(t["src0"], 1)
        self.assertNotIn("fnv", t)
        self.assertNotIn("frames", t)


class MainTest(unittest.TestCase):
    def test_a_column_per_run_and_a_total(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d, "audio-title")
            b = Path(d, "audio-menu")
            a.mkdir()
            b.mkdir()
            write_file(a, "stdout.txt", run_text((10, 6, 500, 1)))
            write_file(b, "stdout.txt", run_text((20, 8, 700, 2)))
            code, out, err = run_main(ax_stats.main, str(a / "stdout.txt"), str(b / "stdout.txt"))
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(lines[0].split(), ["audio-title", "audio-menu", "total"])
        rows = {line.split()[0]: line.split()[1:] for line in lines[1:]}
        self.assertEqual(rows["voice_ms"], ["10", "20", "30"])
        self.assertEqual(rows["main_l"], ["500", "700", "700"])
        self.assertEqual(rows["depop"], ["1", "2", "3"])

    def test_until_past_no_window_and_a_bad_until_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            path = write_file(Path(d), "stdout.txt", run_text((10, 6, 500, 1)))
            self.assertEqual(run_main(ax_stats.main, str(path), "--until", "399")[0], 2)
            self.assertEqual(run_main(ax_stats.main, str(path), "--until", "0")[0], 2)
            code, out, _ = run_main(ax_stats.main, str(path), "--until", "400")
        self.assertEqual(code, 0)
        self.assertIn("voice_ms", out)

    def test_a_run_without_stats_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            path = write_file(Path(d), "stdout.txt", "[ax] frames=400\n")
            code, out, err = run_main(ax_stats.main, str(path))
        self.assertEqual((code, out), (2, ""))
        self.assertIn("GCN_AXSTATS", err)


if __name__ == "__main__":
    unittest.main()
