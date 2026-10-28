from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import pad_report
from testutil import run_main, write_file

HEADER = ["# gcn-recomp input log v4", "# game TEST01  started 2026-01-02T03:04:05",
          "# poll frame chan connected buttons stick_x stick_y cstick_x cstick_y trig_l trig_r"]


def state(frame: int, chan: int = 0, buttons: int = 0, stick=(0x80, 0x80), cstick=(0x80, 0x80),
          triggers=(0, 0), plugged: int = 1, poll: int | None = None) -> str:
    return (f"{frame * 4 + chan if poll is None else poll} {frame} {chan} {plugged} {buttons:04X}"
            f" {stick[0]:02X} {stick[1]:02X} {cstick[0]:02X} {cstick[1]:02X} {triggers[0]:02X} {triggers[1]:02X}")


class DirectionTest(unittest.TestCase):
    def test_eight_directions_clockwise_from_up(self):
        pushes = [(0, 90), (70, 70), (90, 0), (70, -70), (0, -90), (-70, -70), (-90, 0), (-70, 70)]
        self.assertEqual([pad_report.direction(x, y) for x, y in pushes], list(range(8)))

    def test_a_push_short_of_reach_is_no_direction(self):
        self.assertIsNone(pad_report.direction(30, 39))
        self.assertEqual(pad_report.direction(30, 40), 1)


class ParseTest(unittest.TestCase):
    def test_a_press_counts_once_however_its_other_buttons_change(self):
        A, B = 0x0100, 0x0200
        ports, _ = pad_report.parse(HEADER + [state(10, buttons=A), state(11, buttons=A | B), state(12, buttons=B),
                                              state(13, buttons=A | B), state(14)])
        self.assertEqual(ports[0].presses, {"A": [10, 13], "B": [11]})

    def test_buttons_keep_the_order_they_were_first_pressed(self):
        ports, _ = pad_report.parse(HEADER + [state(5, buttons=0x0008), state(6), state(7, buttons=0x1000),
                                              state(8), state(9, buttons=0x0008)])
        self.assertEqual(list(ports[0].presses), ["Up", "Start"])

    def test_each_channel_counts_its_own_presses(self):
        ports, _ = pad_report.parse(HEADER + [state(3, chan=0, buttons=0x0010), state(3, chan=2, buttons=0x0010),
                                              state(4, chan=2), state(5, chan=2, buttons=0x0010)])
        self.assertEqual(ports[0].presses, {"Z": [3]})
        self.assertEqual(ports[2].presses, {"Z": [3, 5]})

    def test_sticks_keep_their_range_from_the_middle_and_directions(self):
        ports, _ = pad_report.parse(HEADER + [state(1, stick=(0xE4, 0x80)), state(2, stick=(0x80, 0x1C)),
                                              state(3, stick=(0x90, 0x90), cstick=(0x30, 0xD0)), state(4)])
        stick = ports[0].stick
        self.assertEqual((stick.low, stick.high), ([0, -100], [100, 16]))
        self.assertEqual(stick.reached, {2, 4})
        self.assertEqual(ports[0].cstick.reached, {7})

    def test_triggers_count_their_levels(self):
        ports, _ = pad_report.parse(HEADER + [state(1, triggers=(0x40, 0xFF)), state(2, triggers=(0x90, 0)),
                                              state(3, triggers=(0x40, 0xFF)), state(4)])
        self.assertEqual(ports[0].levels, {"L": {0x40, 0x90}, "R": {0xFF}})

    def test_plugged_in_changes_and_the_end_line(self):
        lines = HEADER + [state(0, plugged=0), state(30), state(31, buttons=0x0100), state(90, plugged=0),
                          "jump 1000 20", "pose head 3 0", "# end 400 100"]
        ports, end = pad_report.parse(lines)
        self.assertEqual(ports[0].plugged, [(0, False), (30, True), (90, False)])
        self.assertEqual(end, 100)

    def test_a_short_line_names_its_number(self):
        with self.assertRaisesRegex(ValueError, "line 5 is not a pad state"):
            pad_report.parse(HEADER + [state(1), "2 2 0 1 0000 80 80 80 80 00"])

    def test_a_version_1_log_is_refused(self):
        with self.assertRaisesRegex(ValueError, "version 1 log"):
            pad_report.parse(["# gcn-recomp input log v1", "5 0 1 0000 80 80 80 80 00 00"])


class GamepadLinesTest(unittest.TestCase):
    def test_a_gamepad_line_takes_the_frame_timed_before_it(self):
        lines = ['gamepads: "Test Pad" on port 1', "[ft] f40 guest  16.67ms  fe", "[ft] f41 guest  16.67ms  fe",
                 'gamepads: "Test Pad" pulled out of port 1', "[ft] f99 guest  16.67ms  fe",
                 'gamepads: "Test Pad" on port 2', 'gamepads: "Other Pad" left out: no port is free']
        events, left_out = pad_report.gamepad_lines(lines)
        self.assertEqual(events, {0: [(None, True, "Test Pad"), (41, False, "Test Pad")], 1: [(99, True, "Test Pad")]})
        self.assertEqual(left_out, ["Other Pad"])


class MainTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def session(self, lines: list[str], stdout: str | None = None) -> Path:
        (self.dir / "inputs").mkdir()
        write_file(self.dir / "inputs", "inputs.txt", "\n".join(HEADER + lines) + "\n")
        if stdout is not None:
            write_file(self.dir, "stdout.txt", stdout)
        return self.dir

    def test_a_session_reports_each_plugged_in_port(self):
        lines = [state(0), state(0, chan=1, plugged=0), state(0, chan=2, plugged=0),
                 state(120, buttons=0x0100), state(150), state(3600, stick=(0x80, 0xE4)), state(3610),
                 state(3700, triggers=(0xFF, 0)), state(3710), "# end 20000 5400"]
        code, out, err = run_main(pad_report.main, str(self.session(lines, 'gamepads: "Test Pad" on port 1\n')))
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.splitlines(), [
            "the log ends at frame 5400 (1:30.0)",
            "port 1",
            '  gamepad "Test Pad" on at the start',
            "  plugged in at frame 0 (0:00.0)",
            "  buttons, in the order first pressed:",
            "    A         1 from frame 120 (0:02.0)",
            "  stick    x +0 to +0, y +0 to +100, 1 of 8 directions: up",
            "  c-stick  x +0 to +0, y +0 to +0, no direction",
            "  L        trigger up to 255, on or off",
            "  R        trigger never moved",
            "  never used: B, X, Y, Z, L, R, Start, Up, Down, Left, Right, c-stick, R trigger",
            "never plugged in: ports 2, 3",
        ])

    def test_an_input_logs_own_directory_reads_without_stdout(self):
        write_file(self.dir, "inputs.txt", "\n".join(HEADER + [state(0, buttons=0x0200), state(1)]) + "\n")
        code, out, _ = run_main(pad_report.main, str(self.dir))
        self.assertEqual(code, 0)
        self.assertIn("the log has no end line", out)
        self.assertIn("    B         1 from frame 0 (0:00.0)", out)

    def test_a_port_using_every_control_says_so(self):
        every = sum(bit for _, bit in pad_report.BUTTONS)
        lines = [state(1, buttons=every, stick=(0xE4, 0x80), cstick=(0x1C, 0x80), triggers=(0x20, 0xFF))]
        _, out, _ = run_main(pad_report.main, str(self.session(lines + [state(2, triggers=(0x60, 0xFF))])))
        self.assertIn("  every control used", out)
        self.assertIn("  L        trigger up to 96, 2 levels", out)

    def test_no_log_or_no_pad_state_exits_2(self):
        code, _, err = run_main(pad_report.main, str(self.dir))
        self.assertEqual(code, 2)
        self.assertIn("no inputs.txt", err)
        self.session(["jump 10 2"])
        code, _, err = run_main(pad_report.main, str(self.dir))
        self.assertEqual(code, 2)
        self.assertIn("no pad state", err)

    def test_a_bad_line_exits_2_naming_the_file(self):
        code, _, err = run_main(pad_report.main, str(self.session(["1 1 0 1 zz 80 80 80 80 00 00"])))
        self.assertEqual(code, 2)
        self.assertIn("inputs.txt: line 4 is not a pad state", err)


if __name__ == "__main__":
    unittest.main()
