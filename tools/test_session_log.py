import tempfile
import unittest
from pathlib import Path

import session_log
from session_log import Callbacks, Device
from testutil import write_file

LOG = """\
[session] build/playtest/20261022-160000
[audio] device driver=coreaudio rate=48000 channels=2 buffer=512
[audio] output frame 0 plays DMA frame 0
[audio] late callback at output frame 96000 gap_ms=17.1
[audio] callbacks n=400 period_ms=10.67 late=1 worst_ms=17.1 underruns=0
[ring] cut 640 frames at output frame 120000
[audio] output frame 120000 plays DMA frame 80640
[audio] underrun at output frame 150000 frames=300
[audio] underrun at output frame 150300 frames=512
[shaders] built program 7 in the background in 12.5 ms
[shaders] compiled program 8 in 30.0 ms
[audio] callbacks n=800 period_ms=10.66 late=1 worst_ms=10.9 underruns=2
"""


def parse(text: str) -> session_log.SessionLog:
    return session_log.parse(text.splitlines(keepends=True))


class ParseTest(unittest.TestCase):
    def test_reads_each_kind_of_line(self):
        log = parse(LOG)
        self.assertEqual(log.device, Device("coreaudio", 48000, 2, 512))
        self.assertEqual(log.late, [(96000, 17.1)])
        self.assertEqual(log.underruns, [(150000, 300), (150300, 512)])
        self.assertEqual(log.positions, [(0, 0), (120000, 80640)])
        self.assertEqual(log.background_ms, [12.5])
        self.assertEqual(log.fatal, [])
        self.assertFalse(log.reset)

    def test_a_cut_is_kept_as_output_frame_then_frames(self):
        self.assertEqual(parse(LOG).cuts, [(120000, 640)])

    def test_the_last_callbacks_line_is_kept(self):
        self.assertEqual(parse(LOG).callbacks, Callbacks(800, 10.66, 1, 10.9, 2))

    def test_lines_cut_off_mid_number_are_skipped(self):
        log = parse("[audio] late callback at output frame 96000 gap_ms=\n"
                    "[audio] underrun at output frame 150000\n"
                    "[audio] device driver=coreaudio rate=48000 channels=2\n")
        self.assertEqual((log.late, log.underruns, log.device), ([], [], None))

    def test_panics_fatal_and_fault_lines_are_crashes(self):
        lines = ["FATAL: guest panic: game.c:12: oops", "FAULT: host address 0x0 (code 1)",
                 "guest panic: game.c:12: oops"]
        log = parse("\n".join(["[audio] output frame 0 plays DMA frame 0", *lines, "[ft] FATAL is a word"]))
        self.assertEqual(log.fatal, lines)

    def test_a_reset_line_ends_the_run(self):
        self.assertTrue(parse("[reset] the game reset the console (hot reset, code 0)\n").reset)


class RunsTest(unittest.TestCase):
    def test_splits_at_each_session_line(self):
        lines = ["boot", "[session] a", "x", "[reset] the game reset the console", "[session] a/run-2", "y"]
        self.assertEqual(session_log.runs(lines),
                         [["boot", "[session] a", "x", "[reset] the game reset the console"], ["[session] a/run-2", "y"]])

    def test_a_log_without_session_lines_is_one_run(self):
        self.assertEqual(session_log.runs(["x", "y"]), [["x", "y"]])


class FindLogTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        write_file(self.dir, "stdout.txt", "[session] one\nfirst\n[session] one/run-2\nsecond\n")
        (self.dir / "run-2").mkdir()
        (self.dir / "run-5").mkdir()
        (self.dir / "other").mkdir()

    def test_a_session_reads_its_own_log_from_the_first_run(self):
        self.assertEqual(session_log.find_log(self.dir), (self.dir / "stdout.txt", 0))
        lines, path = session_log.run_lines(self.dir)
        self.assertEqual(lines, ["[session] one\n", "first\n"])

    def test_a_run_directory_reads_its_run_of_the_parents_log(self):
        self.assertEqual(session_log.find_log(self.dir / "run-2"), (self.dir / "stdout.txt", 1))
        lines, path = session_log.run_lines(self.dir / "run-2")
        self.assertEqual((lines, path), (["[session] one/run-2\n", "second\n"], self.dir / "stdout.txt"))

    def test_a_run_the_log_never_reached_has_no_lines(self):
        self.assertEqual(session_log.run_lines(self.dir / "run-5"), ([], self.dir / "stdout.txt"))

    def test_any_other_directory_has_no_log(self):
        self.assertIsNone(session_log.find_log(self.dir / "other"))
        self.assertIsNone(session_log.run_lines(self.dir / "other"))


if __name__ == "__main__":
    unittest.main()
