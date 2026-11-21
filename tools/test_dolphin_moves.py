from __future__ import annotations

import unittest
from typing import Optional

import dolphin_diff
import dolphin_moves
from nightly_report import FAIL, PASS, Check, improved
from race_trace import Race

BUDGET = 0.001
HEAD = "tolerance=4 budget=0.1%\n"
LINES = dolphin_diff.parse_triage(HEAD + "\n".join([
    "r 60 share=0.000% max=3 mean=0.01 state=same within under the budget and the state matching",
    "r 2004 share=1.342% max=230 mean=1.11 state=same timing the SAVE icon is up in Dragoon",
    "r 3300 share=24.476% max=255 mean=11.08 state=differs bug pass 568; player2.speed first "
    "differs at frame 3005, pass 273 (41B34B42 against 41B31EA5)",
    "r 4000 share=0% max=0 mean=0 state=none refused Dolphin's run never shows it",
]) + "\n").lines


def entry(frame: int, share: float, state: str = "same", **kw) -> dict:
    return {"frame": frame, "share": share, "max": 9, "mean": 0.1, "over": share > BUDGET,
            "state": state, "state_diff": [], "side": f"/work/sides/r-{frame:05d}.png", **kw}


def tonight(**changed: dict) -> dict:
    """The report the triage file was made from, with CHANGED's entries in place of its own."""
    entries = {"60": entry(60, 0.0), "2004": entry(2004, 0.01342), "3300": entry(3300, 0.24476, "differs"),
               "4000": {"frame": 4000, "refused": "Dolphin's run never shows it", "state": "not read",
                        "state_diff": []}}
    entries.update(changed)
    return {"checkpoints": list(entries.values())}


def race(at: Optional[int], through: Optional[int] = 272, frame: Optional[int] = 3005) -> Race:
    return Race("City Trial's city", 600, through, frame if at is not None else None, at,
                ["player2.speed: Dragoon 1, Dolphin 2"] if at is not None else [])


class MovesCase(unittest.TestCase):
    def checks(self, report: dict, found: Optional[list[Race]] = None, lines=LINES) -> dict[str, Check]:
        self.kept: list[int] = []

        def keep(e: dict) -> Optional[str]:
            self.kept.append(e["frame"])
            return f"dolphin/r-{e['frame']:05d}.png"
        got = dolphin_moves.checks("r", lines, BUDGET, report, [race(273)] if found is None else found, keep)
        return {c.id.split(" ", 2)[2]: c for c in got}


class CheckpointTest(MovesCase):
    def test_the_report_the_triage_came_from_passes_and_keeps_no_picture(self):
        got = self.checks(tonight())
        self.assertEqual({k: c.status for k, c in got.items()},
                         {"60": PASS, "2004": PASS, "3300": PASS, "4000": PASS, "race": PASS})
        self.assertEqual(self.kept, [])
        self.assertTrue(all(c.better is None and c.dump is None for c in got.values()))

    def test_a_within_checkpoint_over_the_budget_fails_with_both_scores_and_its_picture(self):
        c = self.checks(tonight(**{"60": entry(60, 0.02677)}))["60"]
        self.assertEqual((c.status, c.kind, c.dump), (FAIL, "moved", "dolphin/r-00060.png"))
        self.assertEqual(c.problems[0].where, "frame 60")
        self.assertEqual(c.problems[0].what, "left within: within at share 0.000% max 3, state same in "
                                             "the triage file, over at share 2.677% max 9, state same tonight")
        self.assertEqual(self.kept, [60])

    def test_a_class_change_fails(self):
        for frame, now in (("60", entry(60, 0.0, "differs")),
                           ("60", entry(60, 0.0, "not read")),
                           ("2004", {"frame": 2004, "refused": "Dragoon has no frame 2004", "state": "not read",
                                     "state_diff": []}),
                           ("2004", entry(2004, 0.01342, "differs"))):
            with self.subTest(frame=frame, now=now):
                self.assertEqual(self.checks(tonight(**{frame: now}))[frame].status, FAIL)

    def test_a_score_out_of_the_budget_fails_and_one_inside_it_passes(self):
        self.assertEqual(self.checks(tonight(**{"2004": entry(2004, 0.01342 + 0.0011)}))["2004"].status, FAIL)
        self.assertEqual(self.checks(tonight(**{"2004": entry(2004, 0.01342 + 0.0009)}))["2004"].status, PASS)
        self.assertEqual(self.checks(tonight(**{"60": entry(60, 0.0009)}))["60"].status, PASS)
        self.assertIn("its share rose more than the budget's 0.1%",
                      self.checks(tonight(**{"3300": entry(3300, 0.26, "differs")}))["3300"].problems[0].what)

    def test_a_bug_now_within_is_an_improvement_that_fails_nothing(self):
        c = self.checks(tonight(**{"3300": entry(3300, 0.0005)}))["3300"]
        self.assertEqual((c.status, c.dump), (PASS, "dolphin/r-03300.png"))
        self.assertEqual(c.better, "within where it was bug, update tests/hashes/dolphin-triage.txt")
        self.assertEqual(improved(c, None), c.better)

    def test_a_share_that_falls_past_the_budget_or_a_state_that_matches_improves(self):
        self.assertIn("its share fell", self.checks(tonight(**{"2004": entry(2004, 0.005)}))["2004"].better)
        self.assertIn("its state matches now", self.checks(tonight(**{"3300": entry(3300, 0.24476)}))["3300"].better)

    def test_a_refused_line_matched_now_improves(self):
        c = self.checks(tonight(**{"4000": entry(4000, 0.0)}))["4000"]
        self.assertEqual(c.status, PASS)
        self.assertIn("matched where it was refused", c.better)

    def test_a_checkpoint_missing_from_tonight_fails(self):
        report = tonight()
        report["checkpoints"] = [e for e in report["checkpoints"] if e["frame"] != 2004]
        self.assertEqual(self.checks(report)["2004"].kind, "not compared")


class RaceTest(MovesCase):
    def test_an_earlier_first_difference_fails_with_the_picture_after_it(self):
        c = self.checks(tonight(), [race(250, 249, 2980)])["race"]
        self.assertEqual((c.status, c.kind, c.problems[0].where), (FAIL, "differs earlier", "frame 2980 pass 250"))
        self.assertIn("the first difference comes before pass 273", c.problems[0].what)
        self.assertIn("player2.speed: Dragoon 1, Dolphin 2", c.problems[0].what)
        self.assertEqual((c.dump, self.kept), ("dolphin/r-03300.png", [3300]))

    def test_a_later_first_difference_or_none_is_an_improvement(self):
        for found in (race(300, 299), race(None, 600)):
            with self.subTest(at=found.at):
                c = self.checks(tonight(), [found])["race"]
                self.assertEqual(c.status, PASS)
                self.assertTrue(c.better.endswith("update tests/hashes/dolphin-triage.txt"))

    def test_no_difference_in_a_race_left_early_or_never_entered_fails(self):
        for found in (race(None, 400), Race("City Trial's city", 600)):
            with self.subTest(through=found.through):
                c = self.checks(tonight(), [found])["race"]
                self.assertEqual(c.status, FAIL)
                self.assertIn("compared short of pass 600, Dolphin's last, where the first difference "
                              "was at pass 273", c.problems[0].what)
        self.assertEqual(self.checks(tonight(), [Race("City Trial's city", None)])["race"].status, FAIL)

    def test_the_same_first_difference_passes(self):
        c = self.checks(tonight())["race"]
        self.assertEqual((c.status, c.better), (PASS, None))

    def test_the_earliest_of_two_first_passes_is_the_mark(self):
        lines = LINES + dolphin_diff.parse_triage(
            HEAD + "r 4200 share=81.192% max=255 mean=23.90 state=differs bug player4.speed first differs "
            "at frame 3100, pass 300\n").lines
        report = tonight(**{"4200": entry(4200, 0.81192, "differs")})
        self.assertEqual(dolphin_moves.marks(lines), (273, None))
        self.assertEqual(self.checks(report, [race(273)], lines)["race"].better, None)
        self.assertIn("comes after pass 273", self.checks(report, [race(290, 289)], lines)["race"].better or "")

    def test_matches_through_fails_on_a_difference_at_or_before_its_pass_or_a_shorter_compare(self):
        lines = dolphin_diff.parse_triage(HEAD + "r 3600 share=0.467% max=124 mean=0.61 state=same unclear "
                                          "lone pixels. Every compared value matches through pass 564\n").lines
        report = {"checkpoints": [entry(3600, 0.00467)]}
        self.assertEqual(self.checks(report, [race(None, 564)], lines)["race"].status, PASS)
        self.assertEqual(self.checks(report, [race(564, 563)], lines)["race"].status, FAIL)
        self.assertEqual(self.checks(report, [race(None, 500)], lines)["race"].status, FAIL)
        self.assertEqual(self.checks(report, [race(570, 569)], lines)["race"].status, PASS)

    def test_no_race_tonight_fails_and_a_route_whose_lines_name_none_has_no_race_check(self):
        self.assertEqual(self.checks(tonight(), [])["race"].kind, "not compared")
        self.assertNotIn("race", self.checks(tonight(), [], LINES[:2]))

    def test_the_committed_triage_names_each_race_s_first_difference(self):
        lines = dolphin_diff.parse_triage(dolphin_diff.TRIAGE.read_text()).lines
        got = {r: dolphin_moves.marks([t for t in lines if t.route == r])
               for r in ("city-trial", "air-ride-race", "top-ride-grass")}
        self.assertEqual(got, {"city-trial": (273, None), "air-ride-race": (763, None),
                               "top-ride-grass": (None, 564)})


if __name__ == "__main__":
    unittest.main()
