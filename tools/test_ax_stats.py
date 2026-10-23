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


class LabelsTest(unittest.TestCase):
    def labels(self, *paths: str) -> list[str]:
        return ax_stats.labels([Path(p) for p in paths])

    def test_a_stdout_is_named_by_its_directory_and_another_file_by_its_name(self):
        self.assertEqual(self.labels("/a/audio-title/stdout.txt", "/a/notes.txt"), ["audio-title", "notes.txt"])

    def test_runs_of_one_name_each_take_the_shortest_trailing_path_no_other_shares(self):
        got = self.labels("/x/clone-a/build/probe/audio-title/stdout.txt",
                          "/x/clone-b/build/probe/audio-title/stdout.txt",
                          "/x/clone-a/build/probe/audio-menu/stdout.txt")
        self.assertEqual(got, ["clone-a/build/probe/audio-title", "clone-b/build/probe/audio-title", "audio-menu"])

    def test_paths_that_differ_sooner_get_shorter_labels(self):
        got = self.labels("/p/a/run/stdout.txt", "/q/a/run/stdout.txt", "/p/b/run/stdout.txt")
        self.assertEqual(got, ["p/a/run", "q/a/run", "b/run"])

    def test_a_label_never_runs_past_the_root(self):
        self.assertEqual(self.labels("/run/stdout.txt", "/x/run/stdout.txt"), ["/run", "x/run"])

    def test_a_relative_path_is_named_from_where_it_points(self):
        self.assertEqual(self.labels("stdout.txt"), [Path.cwd().name])
        self.assertEqual(self.labels("one/../other/stdout.txt"), ["other"])

    def test_the_same_file_twice_is_an_error_however_it_is_spelled(self):
        with self.assertRaisesRegex(ValueError, "/a/run/stdout.txt: given twice"):
            self.labels("/a/run/stdout.txt", "/a/run/stdout.txt")
        with self.assertRaisesRegex(ValueError, "given twice"):
            self.labels("/a/run/stdout.txt", "/a/other/../run/stdout.txt")


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

    def test_runs_in_directories_of_one_name_each_get_a_column(self):
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for clone, name, window in (("clone-a", "audio-title", (10, 6, 500, 1)),
                                        ("clone-b", "audio-title", (20, 8, 700, 2)),
                                        ("clone-a", "audio-menu", (30, 1, 900, 4))):
                run = Path(d, clone, name)
                run.mkdir(parents=True)
                paths.append(str(write_file(run, "stdout.txt", run_text(window))))
            code, out, err = run_main(ax_stats.main, *paths)
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(lines[0].split(), ["clone-a/audio-title", "clone-b/audio-title", "audio-menu", "total"])
        rows = {line.split()[0]: line.split()[1:] for line in lines[1:]}
        self.assertEqual(rows["voice_ms"], ["10", "20", "30", "60"])
        self.assertEqual(rows["depop"], ["1", "2", "4", "7"])

    def test_the_same_file_twice_exits_2_before_anything_prints(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d, "audio-title")
            run.mkdir()
            path = write_file(run, "stdout.txt", run_text((10, 6, 500, 1)))
            again = Path(d, "elsewhere", "..", "audio-title", "stdout.txt")
            code, out, err = run_main(ax_stats.main, str(path), str(again))
        self.assertEqual((code, out), (2, ""))
        self.assertIn("elsewhere/../audio-title/stdout.txt: given twice", err)

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
