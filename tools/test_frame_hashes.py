import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import frame_hashes
from testutil import run_main, write_file

A, B, C = "a" * 40, "b" * 40, "c" * 40
MANIFEST = "title 20 60 120\n"


class ManifestTest(unittest.TestCase):
    def test_parses_routes_and_extra_args(self):
        routes = frame_hashes.parse_manifest("# comment\n\ncity-trial-4p 30 60 2700,3480 --pads=4\n")
        self.assertEqual(len(routes), 1)
        r = routes[0]
        self.assertEqual((r.name, r.seconds, r.dump_every, r.required, r.extra),
                         ("city-trial-4p", 30, 60, [2700, 3480], ["--pads=4"]))


class HashTest(unittest.TestCase):
    def test_hashes_a_frame_png(self):
        with tempfile.TemporaryDirectory() as d:
            write_file(Path(d), "frame_00060.png", b"a")
            self.assertEqual(frame_hashes.hash_frames(Path(d)),
                             {60: "86f7e437faa5a7fce15d1ddcb9eaeaea377667b8"})


class GoldenTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_round_trip_drops_frames_past_last(self):
        text = frame_hashes.format_golden({60: A, 120: B, 180: C}, 120)
        path = write_file(self.dir, "g.txt", text)
        self.assertEqual(frame_hashes.read_golden(path), {60: A, 120: B})

    def test_malformed_lines_are_refused_with_the_path_and_line(self):
        for bad in ("frame_00060 " + A[:39], "frame_00060 " + "A" * 40, "frame_60 " + A, "junk"):
            path = write_file(self.dir, "g.txt", f"frame_00030 {A}\n{bad}\n")
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, f"{path}: line 2"):
                frame_hashes.read_golden(path)

    def test_empty_golden_is_refused(self):
        path = write_file(self.dir, "g.txt", "\n")
        with self.assertRaisesRegex(ValueError, "no frames"):
            frame_hashes.read_golden(path)

    def test_compare_reports_changed_and_missing(self):
        golden = {60: A, 120: B}
        self.assertEqual(frame_hashes.compare(golden, dict(golden)), [])
        self.assertEqual(frame_hashes.compare(golden, {60: C}),
                         ["frame 60: cccccccc != golden aaaaaaaa", "frame 120: not reached"])


class ReachedTest(unittest.TestCase):
    def test_reports_largest_frame_and_what_the_route_needs(self):
        self.assertEqual(frame_hashes.reached({60: "a", 5400: "b", 120: "c"}, 3300),
                         "reached frame 5400 (needs 3300)")
        self.assertEqual(frame_hashes.reached({}, 60), "reached no frames (needs 60)")


class HashRouteTest(unittest.TestCase):
    route = frame_hashes.Route("title", 20, 60, [120], [])
    out = frame_hashes.ROOT / "build" / "probe" / "hashes-title"

    def run_route(self, exists: bool, run: mock.Mock) -> mock.Mock:
        trash = mock.Mock()
        with (mock.patch.object(frame_hashes, "trash", trash),
              mock.patch.object(frame_hashes.subprocess, "run", run),
              mock.patch.object(frame_hashes, "hash_frames", return_value={60: A}),
              mock.patch.object(Path, "exists", return_value=exists)):
            try:
                self.got = frame_hashes.hash_route(self.route)
            except ValueError:
                self.got = None
        return trash

    def test_runs_probe_with_the_route_and_hashes_the_frames(self):
        run = mock.Mock()
        self.run_route(False, run)
        self.assertEqual(run.call_args.args[0],
                         [str(frame_hashes.PROBE), "hashes-title", "20",
                          str(frame_hashes.ROOT / "tests" / "routes" / "title.txt"), "60"])
        self.assertEqual(self.got, {60: A})

    def test_trashes_a_directory_left_from_an_earlier_run_before_and_after(self):
        trash = self.run_route(True, mock.Mock())
        self.assertEqual(trash.call_args_list, [mock.call(self.out), mock.call(self.out)])

    def test_trashes_the_frames_when_the_probe_fails(self):
        run = mock.Mock(side_effect=subprocess.CalledProcessError(1, "probe"))
        trash = self.run_route(False, run)
        self.assertIsNone(self.got)
        trash.assert_not_called()
        trash = self.run_route(True, run)
        self.assertEqual(trash.call_count, 2)


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.hashes = Path(tmp.name)
        write_file(self.hashes, "manifest.txt", MANIFEST)
        (self.hashes / "gl").mkdir()
        patch = mock.patch.object(frame_hashes, "HASHES", self.hashes)
        patch.start()
        self.addCleanup(patch.stop)

    def golden(self, text: str) -> Path:
        return write_file(self.hashes / "gl", "title.txt", text)

    def main(self, got, *argv: str):
        with mock.patch.object(frame_hashes, "hash_route", return_value=got) as hash_route:
            result = run_main(frame_hashes.main, *argv)
        return (*result, hash_route)

    def test_matching_hashes_exit_0(self):
        self.golden(frame_hashes.format_golden({60: A, 120: B}, 120))
        code, out, _, _ = self.main({60: A, 120: B}, "check")
        self.assertEqual(code, 0)
        self.assertIn("OK, 2 frames match", out)

    def test_a_changed_hash_exits_1(self):
        self.golden(frame_hashes.format_golden({60: A, 120: B}, 120))
        code, out, _, _ = self.main({60: C, 120: B}, "check")
        self.assertEqual(code, 1)
        self.assertIn("frame 60:", out)

    def test_a_frame_not_reached_exits_1(self):
        self.golden(frame_hashes.format_golden({60: A, 120: B}, 120))
        code, out, _, _ = self.main({60: A}, "check")
        self.assertEqual(code, 1)
        self.assertIn("not reached", out)

    def test_record_writes_a_golden_that_check_passes(self):
        got = {60: A, 120: B, 180: C}
        self.assertEqual(self.main(got, "record")[0], 0)
        self.assertEqual(frame_hashes.read_golden(self.hashes / "gl" / "title.txt"), {60: A, 120: B})
        code, out, _, _ = self.main(got, "check")
        self.assertEqual(code, 0)
        self.assertIn("OK, 2 frames match", out)

    def test_record_with_a_gap_exits_1_and_writes_nothing(self):
        code, out, _, _ = self.main({120: B}, "record")
        self.assertEqual(code, 1)
        self.assertIn("didn't reach frames [60]", out)
        self.assertFalse((self.hashes / "gl" / "title.txt").exists())

    def test_bad_goldens_exit_2_naming_the_path_without_running_the_game(self):
        path = self.hashes / "gl" / "title.txt"
        for label, text in (("none", None), ("malformed", "junk\n"), ("empty", "")):
            if text is not None:
                self.golden(text)
            with self.subTest(label):
                code, _, err, hash_route = self.main({}, "check")
                self.assertEqual(code, 2)
                self.assertIn(str(path), err)
                hash_route.assert_not_called()

    def test_unknown_route_exits_2(self):
        code, _, err, hash_route = self.main({}, "check", "nope")
        self.assertEqual(code, 2)
        self.assertIn("nope", err)
        hash_route.assert_not_called()

    def test_help_exits_0(self):
        code, out, _ = run_main(frame_hashes.main, "--help")
        self.assertEqual(code, 0)
        self.assertIn("Usage:", out)


if __name__ == "__main__":
    unittest.main()
