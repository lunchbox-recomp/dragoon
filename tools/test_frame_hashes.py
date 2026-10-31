import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import frame_hashes
import routes
from testutil import run_main, write_file

A, B, C = "a" * 40, "b" * 40, "c" * 40
MANIFEST = "title 20 60 120\n"


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

    def run_route(self, exists: bool, run: mock.Mock, fails: bool = False) -> mock.Mock:
        remove = mock.Mock()
        with (mock.patch.object(frame_hashes, "remove_run", remove),
              mock.patch.object(subprocess, "run", run),
              mock.patch.object(frame_hashes, "hash_frames", return_value={60: A}),
              mock.patch.object(Path, "exists", return_value=exists)):
            if fails:
                with self.assertRaisesRegex(ValueError, r"^title: probe\.sh exited 1$"):
                    frame_hashes.hash_route(self.route)
            else:
                self.got = frame_hashes.hash_route(self.route)
        return remove

    def test_runs_probe_with_the_route_and_hashes_the_frames(self):
        run = mock.Mock()
        self.run_route(False, run)
        self.assertEqual(run.call_args.args[0],
                         [str(frame_hashes.PROBE), "hashes-title", "20",
                          str(routes.route_file("title")), "60"])
        self.assertEqual(self.got, {60: A})

    def test_slow_multiplies_the_seconds_and_changes_nothing_else(self):
        route = frame_hashes.Route("title", 20, 60, [120], ["--pads=4"])
        run = mock.Mock()
        with (mock.patch.object(frame_hashes, "remove_run"),
              mock.patch.object(subprocess, "run", run),
              mock.patch.object(frame_hashes, "hash_frames", return_value={60: A}),
              mock.patch.object(Path, "exists", return_value=False)):
            frame_hashes.hash_route(route, 3)
        self.assertEqual(run.call_args.args[0],
                         [str(frame_hashes.PROBE), "hashes-title", "60",
                          str(routes.route_file("title")), "60", "--pads=4"])

    def test_removes_a_directory_left_from_an_earlier_run_before_and_after(self):
        remove = self.run_route(True, mock.Mock())
        self.assertEqual(remove.call_args_list, [mock.call(self.out), mock.call(self.out)])

    def test_removes_the_frames_when_the_probe_fails(self):
        run = mock.Mock(side_effect=subprocess.CalledProcessError(1, "probe"))
        remove = self.run_route(False, run, fails=True)
        remove.assert_not_called()
        remove = self.run_route(True, run, fails=True)
        self.assertEqual(remove.call_count, 2)


    def test_the_real_remove_run_deletes_the_run_before_and_after(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name) / "build" / "probe" / "hashes-title"
        out.mkdir(parents=True)
        (out / "old.png").write_bytes(b"old")

        def probe(*args, **kwargs):
            self.assertFalse(out.exists())
            out.mkdir()
            (out / "new.png").write_bytes(b"new")

        with (mock.patch.object(frame_hashes, "ROOT", Path(tmp.name)),
              mock.patch.object(subprocess, "run", probe),
              mock.patch.object(frame_hashes, "hash_frames", return_value={60: A})):
            self.assertEqual(frame_hashes.hash_route(self.route), {60: A})
        self.assertFalse(out.exists())
        self.assertTrue(out.parent.is_dir())


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.hashes = Path(tmp.name)
        write_file(self.hashes, "manifest.txt", MANIFEST)
        (self.hashes / "gl").mkdir()
        for patch in (mock.patch.object(frame_hashes, "HASHES", self.hashes),
                      mock.patch.object(frame_hashes, "MANIFEST", self.hashes / "manifest.txt")):
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

    def test_every_route_runs_once_at_the_given_slow(self):
        write_file(self.hashes, "manifest.txt", "title 20 60 120\nmenu 10 60 60\n")
        self.golden(frame_hashes.format_golden({60: A, 120: B}, 120))
        write_file(self.hashes / "gl", "menu.txt", frame_hashes.format_golden({60: A}, 60))
        for argv in (("--slow=3",), ("--slow", "3")):
            with self.subTest(argv=argv):
                code, _, _, hash_route = self.main({60: A, 120: B}, "check", *argv)
                self.assertEqual(code, 0)
                self.assertEqual([(c.args[0].name, c.args[1]) for c in hash_route.call_args_list],
                                 [("title", 3), ("menu", 3)])

    def test_a_run_is_not_slowed_unless_asked(self):
        self.golden(frame_hashes.format_golden({60: A, 120: B}, 120))
        _, _, _, hash_route = self.main({60: A, 120: B}, "check")
        self.assertEqual(hash_route.call_args.args[1], 1)

    def test_a_slow_that_is_not_a_whole_number_from_1_exits_2_without_running_the_game(self):
        self.golden(frame_hashes.format_golden({60: A, 120: B}, 120))
        for bad in ("0", "-1", "x", "1.5", ""):
            with self.subTest(bad=bad):
                code, _, err, hash_route = self.main({60: A, 120: B}, "check", f"--slow={bad}")
                self.assertEqual(code, 2)
                self.assertIn(f"--slow={bad} isn't a whole number from 1", err)
                hash_route.assert_not_called()

    def test_record_refuses_slow(self):
        code, _, err, hash_route = self.main({60: A, 120: B}, "record", "--slow=2")
        self.assertEqual(code, 2)
        self.assertIn("--slow is for check", err)
        hash_route.assert_not_called()
        self.assertFalse((self.hashes / "gl" / "title.txt").exists())

    def test_help_exits_0(self):
        code, out, _ = run_main(frame_hashes.main, "--help")
        self.assertEqual(code, 0)
        self.assertIn("Usage:", out)
        self.assertIn("--slow=N", out)


if __name__ == "__main__":
    unittest.main()
