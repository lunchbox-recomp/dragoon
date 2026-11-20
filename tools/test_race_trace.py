from __future__ import annotations

import unittest

import race_trace

HEAD = ["805361AC", "805DE2CC", "80589C70", "8056E4C0", "805361C0", "805DCD30"]
MENU, RACE = 0x03000002, 0x05000013  # the main menu, then Top Ride's race (5/19)


def ram(menu: int = 0, fields: int = 20) -> list[str]:
    """A Dolphin run at the menu for MENU fields, then in Top Ride's race. The race's first field
    still shows the menu's count, 50, then 0, then pass k on the race's field k + 2. rand.seed is
    the pass times 10, the same at every field of a pass."""
    lines = ["frame " + " ".join(HEAD)]
    for n in range(1, fields + 1):
        k = n - menu
        scene, count = (MENU, 50) if k < 1 else (RACE, 50 if k == 1 else k - 2)
        lines.append(f"{n} {scene:08X} {n:08X} 00000000 8070E3C0 {count:08X} {count * 10:08X}")
    return lines


def trace(passes: range, seed=lambda p: p * 10, scene: tuple[str, str] = ("5", "19")) -> dict:
    """Dragoon at pass P on frame P, its rand.seed SEED(P)."""
    return {p: {"scene.major": scene[0], "scene.minor": scene[1], "scene.passes": str(p),
                "rand.seed": str(seed(p))} for p in passes}


def first(lines: list[str], frames: dict) -> race_trace.Race:
    (race,) = race_trace.races(lines, frames)
    return race


class RaceTraceTest(unittest.TestCase):
    def test_a_race_that_matches_matches_through_dolphin_s_last_pass(self):
        race = first(ram(), trace(range(1, 26)))
        self.assertEqual((race.name, race.frame, race.through, race.reach), ("Top Ride's race", None, 18, 18))
        self.assertEqual(race.text(), "Top Ride's race: every compared value matches through pass 18")

    def test_the_first_value_to_differ_names_its_frame_and_pass(self):
        race = first(ram(), trace(range(1, 26), lambda p: p * 10 + (p >= 7)))
        self.assertEqual((race.frame, race.at, race.through), (7, 7, 6))
        self.assertEqual(race.differs, ["rand.seed: Dragoon 71, Dolphin 70"])
        self.assertEqual(race.text(), "Top Ride's race first differs at frame 7, pass 7: "
                                      "rand.seed: Dragoon 71, Dolphin 70")

    def test_the_text_names_three_values_then_how_many_more(self):
        race = race_trace.Race("Air Ride's race", 9, 4, 50, 5, ["a", "b", "c", "d", "e"])
        self.assertEqual(race.text(), "Air Ride's race first differs at frame 50, pass 5: a; b; c; and 2 more")

    def test_dolphin_s_value_a_pass_either_side_still_matches(self):
        race = first(ram(), trace(range(1, 18), lambda p: (p + 1) * 10))
        self.assertEqual((race.frame, race.through), (None, 17))
        race = first(ram(), trace(range(1, 18), lambda p: (p + 2) * 10))
        self.assertEqual((race.frame, race.at), (1, 1))

    def test_frames_outside_the_race_are_left_out(self):
        frames = trace(range(1, 10))
        frames.update(trace(range(10, 12), lambda p: 999, scene=("3", "2")))
        frames.update({k + 2: v for k, v in trace(range(10, 16)).items()})
        race = first(ram(), frames)
        self.assertEqual((race.frame, race.through), (None, 15))

    def test_a_race_after_another_scene_counts_from_its_own_passes(self):
        race = first(ram(menu=5, fields=25), trace(range(1, 30)))
        self.assertEqual((race.frame, race.through), (None, 18))

    def test_a_run_with_no_race_has_none(self):
        lines = ["frame " + " ".join(HEAD), *(f"{n} {MENU:08X} {n:08X} 0 0 0 0" for n in range(1, 5))]
        self.assertEqual(race_trace.races(lines, {}), [])

    def test_no_pass_compared_says_so(self):
        race = first(ram(), {})
        self.assertEqual((race.through, race.text()), (None, "Top Ride's race: no pass compared"))


if __name__ == "__main__":
    unittest.main()
