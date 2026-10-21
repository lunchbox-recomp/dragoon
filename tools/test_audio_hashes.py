import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import audio_hashes
import routes
from testutil import run_main, write_file

A, B, C = "A" * 16, "B" * 16, "C" * 16
MANIFEST = "title 20 60 120\n"
BENCH_OUT = f"""whole run: 1 frames in 20.0 s
[ax] frames=400 voices(running, last frame)=0 peak=0 out=80571E00
[ax] hash list=400 fnv={A}
[ax] cmds list=800 skipped=0 unknown=0 00=400
[ax] hash list=800 fnv={B}
"""


class ParseTest(unittest.TestCase):
    def test_reads_the_hash_lines_and_nothing_else(self):
        self.assertEqual(audio_hashes.parse_hashes(BENCH_OUT), {400: A, 800: B})

    def test_a_run_with_no_hash_lines_has_no_rows(self):
        self.assertEqual(audio_hashes.parse_hashes("[ax] bus list=400 main_l=0\n"), {})

    def test_refuses_a_hash_that_is_not_16_upper_case_hex_digits(self):
        for bad in (A[:15], A + "A", "a" * 16, "G" * 16):
            with self.subTest(bad=bad):
                self.assertEqual(audio_hashes.parse_hashes(f"[ax] hash list=400 fnv={bad}\n"), {})

    def test_a_line_must_start_with_the_ax_tag(self):
        self.assertEqual(audio_hashes.parse_hashes(f"x [ax] hash list=400 fnv={A}\n"), {})


class GoldenTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_round_trip_keeps_the_chosen_lists_in_order(self):
        text = audio_hashes.format_golden("title", {400: A, 800: B, 1200: C}, [1200, 400])
        path = write_file(self.dir, "g.txt", text)
        self.assertEqual(audio_hashes.read_golden(path), {400: A, 1200: C})
        self.assertEqual(text.splitlines()[-2:], [f"400 {A}", f"1200 {C}"])

    def test_the_header_says_the_rows_hold_for_unpaced_runs_only(self):
        text = audio_hashes.format_golden("title", {400: A}, [400])
        self.assertIn("unpaced runs only", text)
        self.assertTrue(text.startswith("# "))

    def test_comments_and_blank_lines_are_skipped(self):
        path = write_file(self.dir, "g.txt", f"# note\n\n400 {A}\n   \n")
        self.assertEqual(audio_hashes.read_golden(path), {400: A})

    def test_malformed_lines_are_refused_with_the_path_and_line(self):
        for bad in (f"800 {A[:15]}", f"800 {'a' * 16}", f"frame_00800 {A}", f"800  {A}", f"800 {A} 1",
                    "800", "junk"):
            path = write_file(self.dir, "g.txt", f"400 {A}\n{bad}\n")
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, f"{path}: line 2"):
                audio_hashes.read_golden(path)

    def test_a_list_count_twice_is_refused(self):
        path = write_file(self.dir, "g.txt", f"400 {A}\n800 {B}\n400 {C}\n")
        with self.assertRaisesRegex(ValueError, f"{path}: line 3: list 400 is there twice"):
            audio_hashes.read_golden(path)

    def test_a_list_count_that_is_not_a_positive_multiple_of_400_is_refused(self):
        for bad in ("0", "7300", "399", "401"):
            path = write_file(self.dir, "g.txt", f"400 {A}\n{bad} {B}\n")
            with self.subTest(bad=bad), self.assertRaisesRegex(
                    ValueError, f"{path}: line 2: list {bad} is not a positive multiple of 400"):
                audio_hashes.read_golden(path)

    def test_a_golden_with_no_rows_is_refused(self):
        path = write_file(self.dir, "g.txt", "# only a header\n\n")
        with self.assertRaisesRegex(ValueError, "no rows"):
            audio_hashes.read_golden(path)

    def test_compare_reports_changed_and_missing(self):
        golden = {400: A, 800: B}
        self.assertEqual(audio_hashes.compare(golden, dict(golden)), [])
        self.assertEqual(audio_hashes.compare(golden, {400: C}),
                         [f"list 400: {C} != golden {A}", "list 800: not reached"])

    def test_compare_ignores_lists_the_golden_does_not_have(self):
        self.assertEqual(audio_hashes.compare({400: A}, {400: A, 800: C}), [])


class ReachedTest(unittest.TestCase):
    def test_reports_largest_list_and_what_the_golden_needs(self):
        self.assertEqual(audio_hashes.reached({400: "a", 5200: "b", 800: "c"}, 20400),
                         "reached list 5200 (needs 20400)")
        self.assertEqual(audio_hashes.reached({}, 800), "reached no lists (needs 800)")


class HashRouteTest(unittest.TestCase):
    route = audio_hashes.Route("title", 20, 60, [120], ["--pads=4"])

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.out = self.root / "build" / "probe" / "audio-title"
        self.out.mkdir(parents=True)
        write_file(self.out, "stdout.txt", BENCH_OUT)
        patch = mock.patch.object(audio_hashes, "ROOT", self.root)
        patch.start()
        self.addCleanup(patch.stop)

    def hash_route(self, run: mock.Mock) -> tuple[dict[int, str], mock.Mock]:
        self.calls = mock.Mock()
        trash = self.calls.trash
        self.calls.attach_mock(run, "run")
        with (mock.patch.object(audio_hashes, "trash", trash),
              mock.patch.object(audio_hashes.subprocess, "run", run)):
            return audio_hashes.hash_route(self.route), trash

    def test_trashes_a_directory_left_from_an_earlier_run_before_the_run_and_keeps_the_last(self):
        _, trash = self.hash_route(mock.Mock())
        trash.assert_called_once_with(self.out)

    def test_trashes_before_the_probe_runs_so_the_game_starts_on_a_blank_card(self):
        self.hash_route(mock.Mock())
        self.assertEqual([name for name, _, _ in self.calls.mock_calls], ["trash", "run"])

    def test_trashes_nothing_when_there_is_no_earlier_run(self):
        self.out.rename(self.root / "elsewhere")
        def play(*args, **kwargs):
            self.out.mkdir()
            write_file(self.out, "stdout.txt", BENCH_OUT)

        _, trash = self.hash_route(mock.Mock(side_effect=play))
        trash.assert_not_called()

    def test_runs_probe_as_a_bench_with_the_stats_on_and_reads_the_hashes(self):
        run = mock.Mock()
        got, _ = self.hash_route(run)
        self.assertEqual(run.call_args.args[0],
                         [str(audio_hashes.PROBE), "audio-title", "20",
                          str(routes.route_file("title")), "60", "GCN_AXSTATS=1", "--bench", "--pads=4"])
        self.assertEqual(got, {400: A, 800: B})

    def test_runs_it_with_sdls_dummy_audio_driver(self):
        run = mock.Mock()
        self.hash_route(run)
        self.assertEqual(run.call_args.kwargs["env"]["SDL_AUDIO_DRIVER"], "dummy")

    def test_a_failed_probe_is_an_error_naming_the_route(self):
        run = mock.Mock(side_effect=subprocess.CalledProcessError(1, "probe"))
        with self.assertRaisesRegex(ValueError, "title: probe.sh exited 1"):
            self.hash_route(run)


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.hashes = Path(tmp.name)
        write_file(self.hashes, "manifest.txt", MANIFEST)
        (self.hashes / "audio").mkdir()
        for patch in (mock.patch.object(audio_hashes, "HASHES", self.hashes),
                      mock.patch.object(audio_hashes, "MANIFEST", self.hashes / "manifest.txt")):
            patch.start()
            self.addCleanup(patch.stop)
        self.path = self.hashes / "audio" / "title.txt"

    def golden(self, text: str) -> Path:
        return write_file(self.hashes / "audio", "title.txt", text)

    def main(self, got, *argv: str):
        with mock.patch.object(audio_hashes, "hash_route", return_value=got) as hash_route:
            result = run_main(audio_hashes.main, *argv)
        return (*result, hash_route)

    def test_matching_hashes_exit_0(self):
        self.golden(f"400 {A}\n800 {B}\n")
        code, out, _, _ = self.main({400: A, 800: B, 1200: C}, "check")
        self.assertEqual(code, 0)
        self.assertIn("title: OK, 2 rows match, reached list 1200 (needs 800)", out)

    def test_a_changed_hash_exits_1_and_names_the_list(self):
        self.golden(f"400 {A}\n800 {B}\n")
        code, out, _, _ = self.main({400: C, 800: B}, "check")
        self.assertEqual(code, 1)
        self.assertIn(f"list 400: {C} != golden {A}", out)
        self.assertNotIn("list 800:", out)

    def test_a_list_not_reached_exits_1_and_says_how_far_the_run_got(self):
        self.golden(f"400 {A}\n800 {B}\n")
        code, out, _, _ = self.main({400: A}, "check")
        self.assertEqual(code, 1)
        self.assertIn("list 800: not reached", out)
        self.assertIn("reached list 400 (needs 800)", out)

    def test_a_run_with_no_hash_lines_fails_instead_of_passing(self):
        self.golden(f"400 {A}\n")
        code, out, _, _ = self.main({}, "check")
        self.assertEqual(code, 1)
        self.assertIn("reached no lists (needs 400)", out)

    def test_a_golden_row_the_run_matches_does_not_excuse_one_it_lacks(self):
        self.golden(f"400 {A}\n20400 {B}\n")
        code, out, _, _ = self.main({400: A}, "check")
        self.assertEqual(code, 1)
        self.assertIn("list 20400: not reached", out)

    def test_record_at_chosen_lists_writes_a_golden_that_check_passes(self):
        got = {400: A, 800: B, 1200: C}
        self.assertEqual(self.main(got, "record", "--lists", "400,1200")[0], 0)
        self.assertEqual(audio_hashes.read_golden(self.path), {400: A, 1200: C})
        code, out, _, _ = self.main(got, "check")
        self.assertEqual(code, 0)
        self.assertIn("OK, 2 rows match", out)

    def test_record_with_no_lists_rewrites_the_lists_the_golden_has(self):
        self.golden(f"400 {A}\n1200 {B}\n")
        self.assertEqual(self.main({400: C, 800: A, 1200: B}, "record")[0], 0)
        self.assertEqual(audio_hashes.read_golden(self.path), {400: C, 1200: B})

    def test_record_with_no_lists_and_no_golden_exits_2(self):
        code, _, err, hash_route = self.main({400: A}, "record")
        self.assertEqual(code, 2)
        self.assertIn(str(self.path), err)
        hash_route.assert_not_called()

    def test_record_with_a_list_not_reached_exits_1_and_writes_nothing(self):
        code, out, _, _ = self.main({400: A}, "record", "--lists", "400,800")
        self.assertEqual(code, 1)
        self.assertIn("didn't reach lists [800]", out)
        self.assertFalse(self.path.exists())

    def test_bad_goldens_exit_2_naming_the_path_without_running_the_game(self):
        for label, text in (("none", None), ("malformed", "junk\n"), ("empty", ""),
                            ("bad hash", f"400 {'a' * 16}\n")):
            if text is not None:
                self.golden(text)
            with self.subTest(label):
                code, _, err, hash_route = self.main({}, "check")
                self.assertEqual(code, 2)
                self.assertIn(str(self.path), err)
                hash_route.assert_not_called()

    def test_a_missing_golden_is_not_a_pass(self):
        code, out, err, _ = self.main({400: A}, "check")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn(str(self.path), err)

    def test_unknown_route_exits_2(self):
        code, _, err, hash_route = self.main({}, "check", "nope")
        self.assertEqual(code, 2)
        self.assertIn("nope", err)
        hash_route.assert_not_called()

    def test_a_list_count_that_is_not_a_number_exits_2(self):
        code, _, err, hash_route = self.main({}, "record", "--lists", "400,x")
        self.assertEqual(code, 2)
        self.assertIn("'x'", err)
        hash_route.assert_not_called()

    def test_a_repeated_list_count_exits_2_before_the_game_runs_and_writes_nothing(self):
        code, _, err, hash_route = self.main({400: A}, "record", "--lists", "400,800,400")
        self.assertEqual(code, 2)
        self.assertIn("names a list count twice", err)
        hash_route.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_a_list_count_that_is_not_a_positive_multiple_of_400_exits_2(self):
        for bad in ("0", "7300", "-400"):
            with self.subTest(bad=bad):
                code, _, err, hash_route = self.main({}, "record", "--lists", f"400,{bad}")
                self.assertEqual(code, 2)
                self.assertIn(f"{bad} is not a positive multiple of 400", err)
                hash_route.assert_not_called()

    def test_check_refuses_lists(self):
        self.golden(f"400 {A}\n")
        code, _, err, hash_route = self.main({400: A}, "check", "--lists", "400")
        self.assertEqual(code, 2)
        self.assertIn("--lists is for record", err)
        hash_route.assert_not_called()

    def test_help_exits_0(self):
        code, out, _ = run_main(audio_hashes.main, "--help")
        self.assertEqual(code, 0)
        self.assertIn("Usage:", out)


if __name__ == "__main__":
    unittest.main()
