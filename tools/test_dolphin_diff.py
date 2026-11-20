from __future__ import annotations

import contextlib
import hashlib
import io
import unittest
from pathlib import Path
from unittest import mock

import dolphin_diff
import dolphin_ref
from dolphin_diff import Bad, Watched
from framediff import Image
from frame_pair import write_png
from routes import Route
from testutil import run_main, temp_dir, write_file

SCENE = "805361AC"
RENEW = "805DE2CC"
RENEW_LAST = "80589C70"
NEXT = "8056E4C0"
HEAD = [SCENE, RENEW, RENEW_LAST, NEXT]
A, B = 0x806783C0, 0x8070E3C0  # the game's two XFBs


def ram(rows: list[tuple[int, int, int]]) -> list[str]:
    """A ram.txt watching the scene word, the renew counts and vi.next_buffer, a field a row,
    each row (scene, renew, next). The count a reset keeps is the renew count the row before,
    so a reset field adds only the frames shown after it."""
    out, kept = ["frame " + " ".join(HEAD)], 0
    for n, (scene, renew, nxt) in enumerate(rows, 1):
        out.append(f"{n} " + " ".join(f"{v:08X}" for v in (scene, renew, kept, nxt)))
        kept = renew
    return out


def boot_at(frame: int):
    return mock.patch.object(dolphin_diff, "BOOT", frame)


def flat(w: int, h: int, colour: tuple[int, int, int]) -> Image:
    return Image(w, h, 3, bytes(colour) * (w * h))


def png(folder: Path, name: str, image: Image) -> Path:
    return write_file(folder, name, write_png(image))


class TimelineTest(unittest.TestCase):
    """A fake run: nothing up for two fields, then a picture a field, with the renew count
    going back to 0 on field 5, where the game still put a picture up."""
    ROWS = [(0x12000026, 0, 0), (0x12000026, 0, 0), (0x12000026, 1, A), (0x02000000, 2, B),
            (0x02000000, 0, A), (0x02000000, 1, B), (0x03000002, 2, A), (0x03000002, 2, A)]

    def test_pictures_count_every_new_buffer_and_not_field_one(self):
        rows = [(0, 0, B)] + self.ROWS[1:]
        self.assertEqual(dolphin_diff.pictures(ram(self.ROWS)), [0, 0, 1, 2, 3, 4, 5, 5])
        self.assertEqual(dolphin_diff.pictures(ram(rows))[:3], [0, 1, 2])

    def test_a_game_frame_is_matched_at_the_first_field_showing_it(self):
        frames = [0, 0, 1, 2, 2, 3, 4, 4]
        self.assertEqual(dolphin_diff.first_field(frames, 2), 4)
        self.assertEqual(dolphin_diff.first_field(frames, 4), 7)
        self.assertIsNone(dolphin_diff.first_field(frames, 5))

    def test_checkpoints_are_the_goldens_and_each_scene_start_and_settle(self):
        route = Route("r", 30, 60, [7], [])
        with boot_at(0):
            got = dolphin_diff.checkpoints(route, ram(self.ROWS))
        self.assertEqual([c.frame for c in got], [0, 2, 4, 7, 10, 12, 14])
        self.assertEqual(got[0].why, "scene 18/38 starts")  # at BOOT, so not moved
        self.assertEqual(got[1].why, "scene 2/0 starts")
        self.assertEqual(got[4].why, "scene 18/38, 10 frames in")
        self.assertEqual(got[3].why, "golden 7")
        self.assertEqual([c.race for c in got], [""] * 7)
        self.assertEqual([c.since for c in got], [1, 4, 7, 7, 7, 7, 7])
        self.assertEqual([c.until for c in got], [4, 7, 0, 0, 0, 0, 0])

    def test_checkpoints_before_boot_are_one_at_boot(self):
        with boot_at(11):
            got = dolphin_diff.checkpoints(Route("r", 30, 60, [7], []), ram(self.ROWS))
        self.assertEqual([(c.frame, c.why) for c in got],
                         [(7, "golden 7"), (11, "the blank card's prompt"),
                          (12, "scene 2/0, 10 frames in"), (14, "scene 3/2, 10 frames in")])

    def test_a_scene_word_change_that_keeps_the_scene_is_no_checkpoint(self):
        rows = [(0x02000000, 0, A), (0x02000000, 1, B), (0x02010000, 2, A), (0x03000002, 3, B)]
        with boot_at(0):
            got = dolphin_diff.checkpoints(Route("r", 30, 60, [3], []), ram(rows))
        self.assertEqual([c.frame for c in got], [0, 3, 10, 13])

    def test_a_checkpoint_deep_in_a_race_is_matched_by_its_pass(self):
        # Top Ride's race starts at frame 1, field 2; its start and settled checkpoints are
        # matched by the game frame, the ones past them by the race's passes.
        rows = [(0x05000018, 0, A), (0x05000013, 1, B), (0x05000013, 2, A), (0x05000013, 3, B)]
        with boot_at(0):
            got = dolphin_diff.checkpoints(Route("r", 30, 60, [12, 13], []), ram(rows))
        self.assertEqual([(c.frame, c.race, c.since) for c in got],
                         [(0, "", 1), (1, "", 2), (10, "", 2), (11, "", 2),
                          (12, "Top Ride's race", 2), (13, "Top Ride's race", 2)])

    def test_city_trial_s_city_counts_as_a_race(self):
        rows = [(0x06000012, 0, A), (0x06000012, 1, B)]
        with boot_at(0):
            got = dolphin_diff.checkpoints(Route("r", 30, 60, [11], []), ram(rows))
        self.assertEqual([(c.frame, c.race) for c in got],
                         [(0, ""), (10, ""), (11, "City Trial's city")])

    def test_a_scene_s_passes_start_where_its_count_is_0_or_1(self):
        # The race's scene word changes at field 3, the count keeps the last scene's 40 and 41,
        # goes to 0 while it loads and is 1 on the race's first frame.
        counts = [39, 40, 41, 0, 0, 1, 2, 3]
        self.assertEqual(dolphin_diff.scene_passes(counts, 3), [None] * 3 + [0, 0, 1, 2, 3])
        self.assertEqual(dolphin_diff.scene_passes([5, 1, 2], 1), [None, 1, 2])
        self.assertEqual(dolphin_diff.scene_passes([5, 6], 1), [None, None])
        self.assertEqual(dolphin_diff.first_field(dolphin_diff.scene_passes(counts, 3), 2), 7)

    def test_a_scene_s_passes_end_where_the_next_scene_starts(self):
        # The next scene's word comes at field 6, its count holding this one's 4 and 5 until it
        # loads, so pass 4 and 5 belong to this scene only before field 6.
        counts = [0, 1, 2, 3, 4, 4, 5, 0, 1]
        self.assertEqual(dolphin_diff.scene_passes(counts, 1, 6),
                         [0, 1, 2, 3, 4, None, None, None, None])
        self.assertIsNone(dolphin_diff.first_field(dolphin_diff.scene_passes(counts, 1, 6), 5))
        self.assertEqual(dolphin_diff.scene_passes([5, 6, 0], 1, 3), [None, None, None])

    def test_passes_are_read_from_their_column(self):
        lines = ["frame 805361AC 805361C0", "1 05000013 00000272", "2 05000013 00000001"]
        self.assertEqual(dolphin_diff.passes(lines), [0x272, 1])


class PictureMatchTest(unittest.TestCase):
    def setUp(self):
        self.dir = temp_dir(self)
        # Dumps 1 to 6, each its own grey, but 4 and 5 the same picture.
        greys = [10, 20, 30, 40, 40, 60]
        self.dumps = []
        for k, g in enumerate(greys, 1):
            path = png(self.dir, f"framedump_{k}.png", flat(8, 8, (g, g, g)))
            self.dumps.append((hashlib.sha256(path.read_bytes()).hexdigest(), path))
        self.frames = [0, 1, 2, 3, 4, 5]
        self.shown = [1, 2, 3, 4, 5, 6]

    def match(self, n, grey, size=(8, 8), shown=None):
        ours = {n: png(self.dir, f"frame_{n:05d}.png", flat(*size, (grey, grey, grey)))}
        return dolphin_diff.compare_picture(n, dolphin_diff.first_field(self.frames, n),
                                            f"game frame {n}", shown or self.shown, self.dumps,
                                            ours)

    def test_a_race_s_frame_is_matched_at_the_field_its_pass_is_first_up(self):
        # Dragoon's frame 2 is the race's pass 4, which Dolphin's run reaches on field 5.
        ours = {2: png(self.dir, "frame_00002.png", flat(8, 8, (40, 40, 40)))}
        keys = dolphin_diff.scene_passes([7, 8, 0, 1, 4, 5], 2)
        found, refused = dolphin_diff.compare_picture(2, dolphin_diff.first_field(keys, 4),
                                                      "pass 4", self.shown, self.dumps, ours)
        self.assertIsNone(refused)
        self.assertEqual((found[0].field, found[0].counted, found[0].dump), (5, 5, 5))
        _, refused = dolphin_diff.compare_picture(2, dolphin_diff.first_field(keys, 9),
                                                  "pass 9 of Top Ride's race", self.shown,
                                                  self.dumps, ours)
        self.assertEqual(refused, "Dolphin's run never shows pass 9 of Top Ride's race")

    def test_the_counted_dump_is_taken_when_it_is_the_nearest(self):
        found, refused = self.match(2, 30)
        self.assertIsNone(refused)
        self.assertEqual((found[0].field, found[0].counted, found[0].dump, found[0].sure),
                         (3, 3, 3, "sure"))

    def test_a_drifted_count_finds_the_dump_that_shows_the_frame(self):
        found, _ = self.match(1, 60, shown=[1, 1, 2, 3, 4, 5])
        self.assertEqual((found[0].counted, found[0].dump), (1, 6))

    def test_a_tie_between_two_dumps_goes_to_the_counted_one(self):
        errors = {3: 5.0, 4: 5.0, 5: 5.0}
        self.assertEqual(dolphin_diff.pick(errors, {3: "x", 4: "y", 5: "z"}, 4),
                         (4, "unsure"))

    def test_how_sure_says_still_sure_or_unsure(self):
        same = {1: "a", 2: "a", 3: "b"}
        self.assertEqual(dolphin_diff.pick({1: 0.0, 2: 0.0}, same, 1), (1, "still"))
        self.assertEqual(dolphin_diff.pick({1: 1.0, 3: 1.3}, same, 1), (1, "sure"))
        self.assertEqual(dolphin_diff.pick({1: 1.0, 3: 1.2}, same, 1), (1, "unsure"))
        self.assertEqual(dolphin_diff.pick({1: 0.8, 3: 1.0}, same, 1), (1, "unsure"))  # at MARGIN
        self.assertEqual(dolphin_diff.pick({1: 1.0, 2: 0.0, 3: 0.5}, same, 3), (2, "sure"))

    def test_a_frame_dolphin_never_showed_is_refused(self):
        found, refused = self.match(9, 30)
        self.assertIsNone(found)
        self.assertIn("never shows game frame 9", refused)

    def test_dumps_that_stop_short_are_refused(self):
        _, refused = self.match(5, 60, shown=[1, 2, 3, 4, 5, 7])
        self.assertIn("dumps stop at 6, before picture 7", refused)

    def test_a_missing_dragoon_frame_is_refused(self):
        _, refused = dolphin_diff.compare_picture(2, 3, "game frame 2", self.shown, self.dumps, {})
        self.assertIn("Dragoon has no frame 2", refused)

    def test_pictures_of_two_sizes_are_refused_not_scaled(self):
        _, refused = self.match(2, 30, size=(16, 16))
        self.assertIn("16x16 and Dolphin's 8x8", refused)


class ScoreTest(unittest.TestCase):
    def test_share_max_and_mean_over_all_pixels(self):
        a = flat(4, 1, (100, 100, 100))
        b = Image(4, 1, 3, bytes([100, 100, 100, 100, 100, 104, 100, 105, 100, 0, 100, 100]))
        s, diff = dolphin_diff.score(a, b, tolerance=4)
        self.assertEqual(s.share, 0.5)  # 5 and 100 are over 4; 4 isn't
        self.assertEqual(s.max, 100)
        self.assertAlmostEqual(s.mean, (4 + 5 + 100) / 12)
        self.assertEqual(diff.pixels, bytes([0, 0, 0, 0, 0, 0, 255, 250, 250, 255, 155, 155]))

    def test_alpha_is_left_out(self):
        a = Image(1, 1, 4, bytes([1, 2, 3, 0]))
        b = Image(1, 1, 3, bytes([1, 2, 3]))
        self.assertEqual(dolphin_diff.score(a, b)[0].max, 0)

    def test_two_sizes_are_refused(self):
        with self.assertRaisesRegex(Bad, "sizes differ"):
            dolphin_diff.score(flat(2, 2, (0, 0, 0)), flat(2, 1, (0, 0, 0)))

    def test_the_coarse_error_samples_every_nth_pixel(self):
        a = flat(8, 8, (0, 0, 0))
        px = bytearray(a.pixels)
        px[3:6] = b"\xff\xff\xff"  # pixel (1, 0), which the 4-step sample skips
        self.assertEqual(dolphin_diff.coarse(a, Image(8, 8, 3, bytes(px))), 0.0)
        px[0:3] = b"\x0c\x0c\x0c"  # pixel (0, 0), which it reads
        self.assertEqual(dolphin_diff.coarse(a, Image(8, 8, 3, bytes(px))), 12 / 4)


class ThresholdTest(unittest.TestCase):
    def test_the_tolerance_is_the_repeat_error_and_a_rounding_step(self):
        self.assertEqual(dolphin_diff.threshold(0), 4)
        self.assertEqual(dolphin_diff.threshold(2), 6)
        self.assertEqual(dolphin_diff.threshold(0, step=0), 0)
        self.assertEqual(dolphin_diff.TOLERANCE, dolphin_diff.threshold(dolphin_diff.REPEAT_ERROR))

    def test_the_budget_is_a_share_of_pixels_over_the_tolerance(self):
        budget = dolphin_diff.BUDGET
        self.assertFalse(dolphin_diff.over_budget(dolphin_diff.Score(budget, 255, 9.0)))
        self.assertTrue(dolphin_diff.over_budget(dolphin_diff.Score(budget * 1.01, 1, 0.0)))

    def test_a_checkpoint_over_the_budget_or_with_its_state_off_goes_to_triage(self):
        e = {"frame": 5, "share": dolphin_diff.BUDGET, "max": 9, "mean": 0.5, "over": False,
             "state": "same, a frame off"}
        self.assertEqual(dolphin_diff.triage_line("r", e),
                         "r 5 share=0.100% max=9 mean=0.50 state=near within under the budget "
                         "and the state matching")
        e.update(share=0.002, over=True)
        self.assertEqual(dolphin_diff.triage_line("r", e),
                         "r 5 share=0.200% max=9 mean=0.50 state=near unclear not triaged yet")
        e.update(share=0.0, over=False, state="differs")
        self.assertIn(" state=differs unclear ", dolphin_diff.triage_line("r", e))

    def test_a_refused_checkpoint_has_no_score(self):
        e = {"frame": 5, "refused": "why not", "state": "not read"}
        self.assertEqual(dolphin_diff.triage_line("r", e),
                         "r 5 share=0% max=0 mean=0 state=none refused why not")

    def test_repeat_runs_of_dragoon_give_the_largest_error(self):
        a, b = temp_dir(self), temp_dir(self)
        png(a, "frame_00010.png", flat(2, 2, (5, 5, 5)))
        png(b, "frame_00010.png", flat(2, 2, (5, 5, 5)))
        self.assertEqual(run_main(dolphin_diff.main, "repeat", str(a), str(b))[0], 0)
        png(b, "frame_00010.png", flat(2, 2, (5, 6, 5)))
        code, out, _ = run_main(dolphin_diff.main, "repeat", str(a), str(b))
        self.assertEqual((code, out), (1, "Dragoon: 1 frames, the largest channel error 1\n"))

    def test_repeat_runs_of_dolphin_compare_dumps_in_order(self):
        a, b = temp_dir(self), temp_dir(self)
        write_file(a, "frames.txt", "aa  framedump_1.png\nbb  framedump_2.png\n")
        write_file(b, "frames.txt", "aa  framedump_1.png\nbb  framedump_2.png\ncc  framedump_3.png\n")
        self.assertEqual(run_main(dolphin_diff.main, "repeat", str(a), str(b))[0], 0)
        write_file(b, "frames.txt", "aa  framedump_1.png\ncc  framedump_2.png\n")
        self.assertEqual(run_main(dolphin_diff.main, "repeat", str(a), str(b))[0], 1)


class StateTest(unittest.TestCase):
    def test_the_watches_follow_each_path_pointer_by_pointer(self):
        got = dolphin_diff.state_watches(["scene.major", "scene.minor", "player1.x", "player1.y"])
        self.assertEqual(got, ["805361AC", "8055AA2C", "8055AA2C+2C", "8055AA2C+2C+300",
                               "8055AA2C+2C+304"])
        self.assertEqual(dolphin_diff.watches()[:4], HEAD)

    def test_values_are_read_from_the_watched_words_as_kar_ram_reads_them(self):
        row = {"805361AC": 0x05000013, "8055AA2C": 0x81000000, "8055AA2C+2C": 0x81200000,
               "8055AA2C+2C+300": 0x3F800000}
        self.assertEqual(dolphin_diff.state_of(row, ["scene.major", "scene.minor", "player1.x"]),
                         {"scene.major": "5", "scene.minor": "19", "player1.x": "1"})

    def test_a_null_pointer_reads_none(self):
        row = {"8055AA2C": 0, "8055AA2C+2C": 0, "8055AA2C+2C+300": 0}
        self.assertEqual(dolphin_diff.state_of(row, ["player1.x"]), {"player1.x": "none"})
        row = {"8055AA2C": 0x81000000, "8055AA2C+2C": 0, "8055AA2C+2C+300": 0}
        self.assertEqual(dolphin_diff.state_of(row, ["player1.x"]), {"player1.x": "none"})

    def test_a_word_nobody_watched_is_refused(self):
        with self.assertRaisesRegex(Bad, "805361AF: not watched"):
            Watched({}).read(0x805361AF, 1)

    def frames_rows(self, scenes):
        return [n for n, _ in scenes], [{"805361AC": s} for _, s in scenes]

    def test_same_at_the_frame_a_frame_off_or_differs(self):
        want = {"scene.major": "5"}
        frames, rows = self.frames_rows([(9, 0x04000000), (10, 0x05000000), (11, 0x05000000)])
        self.assertEqual(dolphin_diff.compare_state(want, 10, frames, rows), ("same", []))
        frames, rows = self.frames_rows([(9, 0x05000000), (10, 0x04000000), (11, 0x04000000)])
        self.assertEqual(dolphin_diff.compare_state(want, 10, frames, rows),
                         ("same, a frame off", []))
        frames, rows = self.frames_rows([(8, 0x05000000), (10, 0x04000000), (12, 0x05000000)])
        self.assertEqual(dolphin_diff.compare_state(want, 10, frames, rows),
                         ("differs", ["scene.major: Dragoon 5, Dolphin 4"]))

    def test_what_differs_is_listed_from_the_first_field_at_the_frame(self):
        frames, rows = self.frames_rows([(10, 0x04000000), (10, 0x03000000)])
        self.assertEqual(dolphin_diff.compare_state({"scene.major": "5"}, 10, frames, rows),
                         ("differs", ["scene.major: Dragoon 5, Dolphin 4"]))

    def test_a_frame_dolphin_never_reached_differs(self):
        frames, rows = self.frames_rows([(1, 0), (2, 0)])
        self.assertEqual(dolphin_diff.compare_state({"scene.major": "0"}, 9, frames, rows),
                         ("differs", ["Dolphin never reached game frame 9"]))

    def test_a_race_s_state_is_compared_at_its_pass_and_not_before_the_scene_s_passes(self):
        # The last scene's count, 4, is still up on the first field and doesn't count.
        _, rows = self.frames_rows([(0, 0x05000000), (0, 0x04000000), (0, 0x05000000)])
        keys = [None, 3, 4]
        self.assertEqual(dolphin_diff.compare_state({"scene.major": "5"}, 4, keys, rows, "pass"),
                         ("same", []))
        self.assertEqual(dolphin_diff.compare_state({"scene.major": "4"}, 4, keys, rows, "pass"),
                         ("same, a frame off", []))
        self.assertEqual(dolphin_diff.compare_state({"scene.major": "5"}, 9, keys, rows, "pass"),
                         ("differs", ["Dolphin never reached pass 9"]))

    def test_the_rng_seeds_are_compared_and_the_pass_is_not(self):
        self.assertIn("rand.seed", dolphin_diff.FIELDS)
        self.assertIn("top_ride.seed", dolphin_diff.FIELDS)
        self.assertNotIn(dolphin_diff.PASSES, dolphin_diff.FIELDS)
        self.assertEqual(dolphin_diff.watches()[4], "805361C0")


class RaceCompareTest(unittest.TestCase):
    """A run that's in Top Ride's race from field 1, a game frame a field. The count keeps the last
    scene's 50 on field 1 and is 0 on field 2, so pass k is up on field k + 2. Game frame n is up
    on field n, its picture the (n - 1)th."""

    def setUp(self):
        self.out = temp_dir(self)
        head = ["805361AC", "805DE2CC", "80589C70", "8056E4C0", "805361C0", "805DCD30"]
        lines = ["frame " + " ".join(head)]
        for n in range(1, 31):
            count = 50 if n == 1 else n - 2
            # rand.seed is the field number, so a state matches at one field only.
            lines.append(f"{n} 05000013 {n:08X} 00000000 {(A, B)[n % 2]:08X} {count:08X} "
                         f"{n:08X}")
        dolphin = self.out / "dolphin"
        (dolphin / "frames").mkdir(parents=True)
        write_file(dolphin, "ram.txt", "\n".join(lines) + "\n")
        listed = []
        for k in range(1, 31):
            path = png(dolphin / "frames", f"framedump_{k}.png", flat(4, 4, (k * 8, 0, 0)))
            listed.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
        write_file(dolphin, "frames.txt", "\n".join(listed) + "\n")
        (self.out / "dragoon").mkdir()
        # Dragoon's frame 20 is the race's pass 6, the picture Dolphin put up on field 8.
        for frame, grey in ((1, 0), (11, 80), (20, 64)):
            png(self.out / "dragoon", f"frame_{frame:05d}.png", flat(4, 4, (grey, 0, 0)))

    def compare(self, read_20_at=20):
        states = {"1": [1, {"scene.major": "5", "scene.passes": "50", "rand.seed": "1"}],
                  "11": [11, {"scene.major": "5", "scene.passes": "8", "rand.seed": "11"}],
                  "20": [read_20_at, {"scene.major": "5", "scene.passes": "6", "rand.seed": "8"}]}
        write_file(self.out / "dragoon", "state.json",
                   dolphin_diff.json.dumps({"end": "exit_after", "detail": "", "states": states}))
        with boot_at(0):
            report = dolphin_diff.compare(Route("r", 30, 60, [20], []), self.out)
        return {e["frame"]: e for e in report["checkpoints"]}

    def test_a_checkpoint_past_the_settled_one_is_matched_at_its_pass(self):
        got = self.compare()
        self.assertEqual((got[20]["pass"], got[20]["field"], got[20]["counted"]), (6, 8, 7))
        self.assertEqual((got[20]["dump"], got[20]["share"], got[20]["state"]), (8, 0.0, "same"))
        self.assertNotIn("pass", got[11])
        self.assertEqual(got[11]["field"], 11)  # by its game frame, as before
        self.assertEqual((got[1]["state"], got[11]["state"]), ("same", "same"))
        self.assertIn("frame 20 (golden 20, pass 6):", dolphin_diff.summary(
            {"route": "r", "disc": "console", "tolerance": 4, "budget": 0.001,
             "dragoon_end": "exit_after", "checkpoints": list(got.values())}))

    def test_a_pass_read_at_another_frame_is_refused(self):
        got = self.compare(read_20_at=21)
        self.assertEqual(got[20]["refused"],
                         "Dragoon read Top Ride's race's pass at frame 21, not at 20")
        self.assertEqual(got[20]["state"], "not read")


class DragoonRunTest(unittest.TestCase):
    def test_dragoon_plays_with_the_test_seed_and_reads_the_passes(self):
        out = temp_dir(self)
        (out / "dolphin").mkdir()
        write_file(out / "dolphin", "ram.txt", "\n".join(
            ["frame " + " ".join(HEAD), *(f"{n} 05000013 {n:08X} 00000000 {A:08X}"
                                          for n in range(1, 4))]) + "\n")
        calls = {}

        def play(route, name, every, bot, settings, probe):
            calls.update(settings=settings, fields=bot.fields, required=route.required)
            raise dolphin_diff.Bad("stop here")

        with mock.patch.object(dolphin_diff.state_goldens, "play", side_effect=play), \
                mock.patch.object(dolphin_diff.bot_link, "run_directory",
                                  return_value=out / "run"), \
                boot_at(0), self.assertRaises(dolphin_diff.Bad), \
                contextlib.redirect_stdout(io.StringIO()):
            dolphin_diff.cmd_dragoon(Route("r", 30, 60, [20], []), out)
        self.assertIn("DRAGOON_SEED_PIN=1", calls["settings"])
        self.assertEqual(calls["fields"][-1], dolphin_diff.PASSES)
        self.assertEqual(calls["required"], [1, 11, 20])

    def test_a_race_is_read_every_frame_to_where_dolphin_s_run_ends(self):
        # Dolphin's run is at the main menu for 5 fields, then in Top Ride's race to game frame 30.
        root = temp_dir(self)
        dolphin = root / "cache"
        dolphin.mkdir()
        rows = [f"{n} {0x03000002 if n <= 5 else 0x05000013:08X} {n:08X} 00000000 {A:08X}"
                for n in range(1, 31)]
        write_file(dolphin, "ram.txt", "\n".join(["frame " + " ".join(HEAD), *rows]) + "\n")
        probe = root / "tools" / "probe.sh"
        calls = {}

        def play(route, name, every, bot, settings, probe):
            calls.update(settings=settings, probe=probe, seconds=route.seconds, required=route.required)
            run_dir = dolphin_diff.bot_link.run_directory(name, probe)
            run_dir.mkdir(parents=True)
            link = type("Link", (), {"frame": 0, "read": lambda self, a, n: bytes(n)})()
            for frame in range(1, 32):
                write_file(run_dir, f"frame_{frame:05d}.png", b"")
                link.frame = frame
                bot(link)
            return dolphin_diff.bot_link.Outcome(31, 31, "exit_after", "", run_dir), bot.states

        with mock.patch.object(dolphin_diff.state_goldens, "play", side_effect=play), \
                contextlib.redirect_stdout(io.StringIO()):
            bad = dolphin_diff.play_dragoon(Route("r", 30, 60, [20], []), root / "out", dolphin,
                                            [10, 12], probe, ["--bin=/b/dragoon"])
        self.assertIsNone(bad)
        self.assertEqual((calls["probe"], calls["settings"][-1]), (probe, "--bin=/b/dragoon"))
        self.assertEqual(calls["required"], [10, 12, 30])  # on to Dolphin's last game frame
        self.assertEqual(calls["seconds"], 30 * dolphin_diff.SLOW * 30 // 12)  # 30 frames, not 12
        saved = dolphin_diff.json.loads((root / "out" / "dragoon" / "state.json").read_text())
        self.assertEqual(sorted(saved["states"]), ["10", "12"])
        self.assertEqual(sorted(map(int, saved["trace"])), list(range(4, 32)))  # from 2 early
        self.assertEqual(sorted(p.name for p in (root / "out" / "dragoon").glob("*.png")),
                         ["frame_00010.png", "frame_00012.png"])
        self.assertFalse(dolphin_diff.bot_link.run_directory("dolphin-diff-r", probe).exists())

    def test_the_triage_s_frames_are_the_checkpoints_and_keep_their_race(self):
        route = Route("r", 30, 60, [20], [])
        rows = [(0x05000013, 0, A), (0x05000013, 1, B)] + [(0x05000013, n % 60, (A, B)[n % 2])
                                                           for n in range(2, 40)]
        with boot_at(0):
            got = dolphin_diff.checkpoints(route, ram(rows), [3, 25])
        self.assertEqual([(c.frame, c.why) for c in got], [(3, "triaged"), (25, "triaged")])
        self.assertEqual([c.race for c in got], ["", "Top Ride's race"])


class TriageTest(unittest.TestCase):
    TEXT = ("# a comment\n\ntolerance=4 budget=0.1%\n"
            "top-ride-grass 304 share=1.250% max=255 mean=2.10 state=same bug no glow\n"
            "top-ride-grass 60 share=0% max=0 mean=0 state=none refused no picture yet\n")

    def test_lines_read_back(self):
        got = dolphin_diff.parse_triage(self.TEXT)
        self.assertEqual((got.tolerance, got.budget), (4, 0.001))
        t = got.lines[0]
        self.assertEqual((t.route, t.frame, t.max, t.state, t.cls, t.reason),
                         ("top-ride-grass", 304, 255, "same", "bug", "no glow"))
        self.assertAlmostEqual(t.share, 0.0125)
        self.assertAlmostEqual(t.mean, 2.1)
        self.assertEqual([t.cls for t in got.lines], ["bug", "refused"])

    def test_a_draft_parses(self):
        e = {"frame": 5, "share": 0.5, "max": 9, "mean": 0.5, "over": True, "state": "same"}
        text = dolphin_diff.triage_head() + "\n" + dolphin_diff.triage_line("r", e)
        got = dolphin_diff.parse_triage(text)
        self.assertEqual((got.tolerance, got.budget), (dolphin_diff.TOLERANCE, dolphin_diff.BUDGET))
        self.assertEqual(got.lines[0].share, 0.5)

    def test_bad_lines_are_refused(self):
        head = "tolerance=4 budget=0.1%\n"
        for text, why in ((head + "r 1 share=1% max=2 mean=0 state=same nope why\n",
                           "class 'nope' isn't one of"),
                          (head + "r 1 share=1% max=2 mean=0 state=odd bug why\n",
                           "state 'odd' isn't one of"),
                          (head + "r 1 share=1% max=2 mean=0 state=same bug\n", "not 'ROUTE"),
                          (head + "r 1 share=1% max=2 mean=0 bug why\n", "not 'ROUTE"),
                          (head + "r x share=1% max=2 mean=0 state=same bug why\n", "not 'ROUTE"),
                          (head + "r 1 share=1% max=2 mean=0 state=same bug a\n"
                                  "r 1 share=1% max=2 mean=0 state=same bug b\n", "triaged twice"),
                          (head + "r 1 share=1% max=2 mean=0 state=differs bug it moves\n",
                           "says 'FIELD first differs at frame N'"),
                          (head + "r 1 share=1% max=2 mean=0 state=same bug lap first differs at "
                                  "frame 9\n", "with FIELD one of FIELDS"),
                          (head + "r 1 share=1% max=2 mean=0 state=differs bug lap first differs "
                                  "at frame 9\n", "with FIELD one of FIELDS"),
                          ("r 1 share=1% max=2 mean=0 state=same bug why\n", "comes first"),
                          ("# nothing\n", "no 'tolerance=")):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, why):
                dolphin_diff.parse_triage(text)

    def test_the_command_checks_a_file(self):
        path = write_file(temp_dir(self), "t.txt", self.TEXT)
        self.assertEqual(run_main(dolphin_diff.main, "triage", str(path))[:2],
                         (0, f"{path}: 2 checkpoints triaged at tolerance=4 budget=0.1%\n"))
        write_file(path.parent, "t.txt", "junk\n")
        self.assertEqual(run_main(dolphin_diff.main, "triage", str(path))[0], 2)

    def test_the_committed_file_parses_at_the_tool_s_tolerance_and_budget(self):
        got = dolphin_diff.parse_triage(dolphin_diff.TRIAGE.read_text())
        self.assertEqual((got.tolerance, got.budget), (dolphin_diff.TOLERANCE, dolphin_diff.BUDGET))
        self.assertTrue(got.lines)

    def test_a_differing_bug_names_its_field_and_frame(self):
        text = ("tolerance=4 budget=0.1%\nr 1 share=1% max=2 mean=0 state=differs bug Dragoon "
                "drifts: player2.x first differs at frame 3336, by a few ulps\n"
                "r 2 share=1% max=2 mean=0 state=differs timing a load, no field\n")
        self.assertEqual([t.cls for t in dolphin_diff.parse_triage(text).lines], ["bug", "timing"])

    def test_the_committed_file_has_no_unpinned_seed_or_unmatched_race_left(self):
        # With the seeds pinned nothing is set up to differ, and a race's checkpoints have passes.
        got = dolphin_diff.parse_triage(dolphin_diff.TRIAGE.read_text())
        self.assertEqual([(t.route, t.frame) for t in got.lines if t.cls in ("setup", "refused")],
                         [])


class PadsTest(unittest.TestCase):
    def test_a_route_with_more_pads_is_refused(self):
        route = Route("two", 30, 60, [100], ["--pads=2"])
        with mock.patch.object(dolphin_diff, "select_routes", return_value=[route]):
            code, _, err = run_main(dolphin_diff.main, "compare", "two")
        self.assertEqual(code, 2)
        self.assertIn("two: plays 2 pads, and both sides here play port 1 only", err)


class KeeperTest(unittest.TestCase):
    def test_it_deletes_the_dumps_it_wont_need_some_frames_behind(self):
        folder = temp_dir(self)
        for n in range(1, 31):
            write_file(folder, f"frame_{n:05d}.png", b"")
        keeper = dolphin_diff.Keeper([5, 100], folder)
        for frame in (12, 25):
            link = type("Link", (), {"frame": frame, "read": lambda self, a, n: bytes(n)})()
            self.assertEqual(keeper(link), {1: dolphin_diff.state_goldens.Pad()})
        left = sorted(int(p.stem[6:]) for p in folder.iterdir())
        self.assertEqual(left, [5, *range(15, 31)])
        self.assertEqual(sorted(keeper.states), [5])


class ChainWatchTest(unittest.TestCase):
    def test_a_chain_goes_to_the_watcher_with_spaces_and_comes_back_with_plus(self):
        self.assertEqual(dolphin_ref.watch_address("8055aa2c+2c+300"), "8055AA2C+2C+300")
        self.assertEqual(dolphin_ref.parse_watch(b"8055AA2C 2C 300\n3f800000\n\0"),
                         {"8055AA2C+2C+300": 0x3F800000})
        user = temp_dir(self) / "user"
        dolphin_ref.fresh_console(user, ["805361AC", "8055AA2C+2C+300"])
        self.assertEqual((user / "MemoryWatcher" / "Locations.txt").read_text(),
                         "805361AC\n8055AA2C 2C 300\n")

    def test_a_bad_chain_is_refused(self):
        for text in ("8055AA2D+2C", "8055AA2C+", "8055AA2C+12345", "8055AA2C+zz"):
            with self.subTest(text=text), self.assertRaises(dolphin_ref.argparse.ArgumentTypeError):
                dolphin_ref.watch_address(text)

    def test_the_diff_run_watches_its_words_and_dumps(self):
        cmd = dolphin_diff.dtm.boot_command(Path("/d.iso"), Path("/m.dtm"), 300, Path("/out"),
                                            "console", ["805361AC", "8055AA2C+2C"], dump=True)
        self.assertEqual(cmd[11:], ["--watch", "805361AC", "--watch", "8055AA2C+2C", "--dump",
                                    "--out", "/out"])


if __name__ == "__main__":
    unittest.main()
