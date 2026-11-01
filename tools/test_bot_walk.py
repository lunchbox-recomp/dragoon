from __future__ import annotations

import unittest

import bot_walk
from bot_link import BUTTONS, Pad
from bot_walk import Walk


def play(seed: int, ports: int, frames: int) -> list[dict[int, Pad]]:
    walk = Walk(seed, ports)
    return [walk.pads() for _ in range(frames)]


class WalkTest(unittest.TestCase):
    def test_one_seed_gives_one_walk(self) -> None:
        self.assertEqual(play(7, 4, 3000), play(7, 4, 3000))

    def test_another_seed_gives_another_walk(self) -> None:
        self.assertNotEqual(play(7, 2, 600), play(8, 2, 600))

    def test_the_seed_gives_these_first_pads_on_any_python(self) -> None:
        # Pinned so a change to the walk, or to the numbers a seed gives, is seen. random() is the
        # one method Python promises to keep the same for a seed.
        first = play(0, 1, 1)[0][1]
        self.assertEqual((first.buttons, first.sx, first.sy), (0, 192, 36))

    def test_every_port_gets_a_pad_every_frame(self) -> None:
        for ports in (1, 2, 3, 4):
            with self.subTest(ports=ports):
                for pads in play(3, ports, 50):
                    self.assertEqual(sorted(pads), list(range(1, ports + 1)))

    def test_a_ports_walk_does_not_depend_on_how_many_ports_there_are(self) -> None:
        one = [pads[1] for pads in play(5, 1, 800)]
        four = [pads[1] for pads in play(5, 4, 800)]
        self.assertEqual(one, four)

    def test_the_ports_walk_apart(self) -> None:
        pads = play(5, 4, 400)
        for a in range(1, 4):
            self.assertNotEqual([p[a] for p in pads], [p[a + 1] for p in pads])

    def test_the_stick_stays_in_range_and_the_other_controls_stay_at_rest(self) -> None:
        for pads in play(11, 4, 5000):
            for pad in pads.values():
                self.assertTrue(1 <= pad.sx <= 255 and 1 <= pad.sy <= 255, pad)
                self.assertEqual((pad.cx, pad.cy, pad.l, pad.r), (128, 128, 0, 0))

    def test_no_pad_ever_presses_anything_but_a(self) -> None:
        pressed = {pad.buttons for pads in play(2, 4, 20000) for pad in pads.values()}
        self.assertEqual(pressed, {0, BUTTONS["A"]})

    def test_start_is_never_pressed(self) -> None:
        for pads in play(9, 4, 20000):
            for pad in pads.values():
                self.assertFalse(pad.buttons & BUTTONS["START"])

    def test_a_heading_is_held_for_half_a_second_to_two(self) -> None:
        stick = [(pads[1].sx, pads[1].sy) for pads in play(4, 1, 6000)]
        runs, length = [], 1
        for before, after in zip(stick, stick[1:]):
            if before == after:
                length += 1
            else:
                runs.append(length)
                length = 1
        low, high = bot_walk.HEADING_FRAMES
        # A new heading can land on the old one's stick position, which joins two runs.
        self.assertGreaterEqual(min(runs), low)
        self.assertGreater(len(runs), 40)
        self.assertLessEqual(max(runs), 2 * high)

    def test_a_taps_hold_and_rest_are_what_they_say(self) -> None:
        a = [bool(pads[1].buttons) for pads in play(6, 1, 20000)]
        holds, gaps, length, last = [], [], 0, a[0]
        for pressed in a:
            if pressed == last:
                length += 1
                continue
            (holds if last else gaps).append(length)
            length, last = 1, pressed
        self.assertGreater(len(holds), 100)
        self.assertEqual(set(holds), {bot_walk.TAP_FRAMES})
        self.assertGreaterEqual(min(gaps[1:]), bot_walk.REST_FRAMES)

    def test_taps_come_about_every_second_or_so(self) -> None:
        a = [bool(pads[1].buttons) for pads in play(1, 1, 36000)]  # ten minutes at 60 frames a second
        taps = sum(1 for before, after in zip(a, a[1:]) if after and not before)
        self.assertTrue(400 < taps < 800, taps)

    def test_a_bad_seed_or_port_count_is_a_value_error(self) -> None:
        for seed, ports in ((-1, 1), (0, 0), (0, 5)):
            with self.subTest(seed=seed, ports=ports), self.assertRaises(ValueError):
                Walk(seed, ports)


if __name__ == "__main__":
    unittest.main()
