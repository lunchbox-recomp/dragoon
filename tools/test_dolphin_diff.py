from __future__ import annotations

import hashlib
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
        self.assertEqual([c.refuse for c in got], [""] * 7)

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

    def test_a_checkpoint_deep_in_a_race_is_refused(self):
        # Top Ride's race starts at frame 1; its start and settled checkpoints are compared.
        rows = [(0x05000018, 0, A), (0x05000013, 1, B), (0x05000013, 2, A), (0x05000013, 3, B)]
        with boot_at(0):
            got = dolphin_diff.checkpoints(Route("r", 30, 60, [12, 13], []), ram(rows))
        self.assertEqual([(c.frame, bool(c.refuse)) for c in got],
                         [(0, False), (1, False), (10, False), (11, False), (12, True),
                          (13, True)])
        self.assertEqual(got[4].refuse, "11 frames into Top Ride's race, where a game frame "
                                        "isn't matched until the race timer is")

    def test_city_trial_s_city_counts_as_a_race(self):
        rows = [(0x06000012, 0, A), (0x06000012, 1, B)]
        with boot_at(0):
            got = dolphin_diff.checkpoints(Route("r", 30, 60, [11], []), ram(rows))
        self.assertEqual([(c.frame, c.refuse[:30]) for c in got],
                         [(0, ""), (10, ""), (11, "11 frames into City Trial's ci")])


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
        return dolphin_diff.compare_picture(n, self.frames, shown or self.shown, self.dumps, ours)

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
        _, refused = dolphin_diff.compare_picture(2, self.frames, self.shown, self.dumps, {})
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
