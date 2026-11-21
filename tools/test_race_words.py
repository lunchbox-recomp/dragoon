from __future__ import annotations

import argparse
import struct
import unittest
from pathlib import Path
from unittest import mock

import race_words
from race_words import Bad
from routes import Route
from testutil import FakeLink, run_main, temp_dir

TIMELINE = ["805361AC", "805DE2CC", "80589C70", "8056E4C0", "805361C0"]
MENU, RACE = 0x03000002, 0x05000013  # the main menu, then Top Ride's race (5/19)
SPEED, X = "80536280", "8055B338+2C+300"
ONE = 0x3F800000  # 1.0
RAND = "805DCD30"  # rand.seed
DRAWS = [0x00B90000]  # HSD_Rand's seeds from the pinned one, a draw apart
while len(DRAWS) < 400:
    DRAWS.append((DRAWS[-1] * 214013 + 2531011) % 2 ** 32)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def dolphin_ram(words: dict, menu: int = 2, fields: int = 22, again: tuple = None) -> str:
    """A Dolphin run at the menu for MENU fields, then in Top Ride's race. The race's first
    field still shows the menu's count, 50, then 0, then pass k on the race's field k + 2. Each
    of WORDS, a watch to a function of the pass, holds that function's value at every field of
    the pass (of pass 0 before the race). AGAIN, (P, {watch: value}), shows pass P on a second
    field after its first, those words changed there. vi.renew_count is the field's number."""
    rows = []
    for n in range(1, fields + 1):
        k = n - menu
        scene, count = (MENU, 50) if k < 1 else (RACE, 50 if k == 1 else k - 2)
        at = count if scene == RACE and k > 1 else 0
        values = {w: f(at) for w, f in words.items()}
        rows.append((scene, count, values))
        if again and scene == RACE and k > 1 and count == again[0]:
            rows.append((scene, count, {**values, **again[1]}))
    lines = ["frame " + " ".join(TIMELINE + list(words))]
    for n, (scene, count, values) in enumerate(rows, 1):
        lines.append(f"{n} " + " ".join(f"{v:08X}" for v in [scene, n, 0, 0x8070E3C0, count, *values.values()]))
    return "\n".join(lines) + "\n"


def dragoon_words(words: dict, passes: range, scene: int = RACE) -> str:
    """Dragoon at pass P on frame P + 100, each of WORDS its function's value at the pass."""
    lines = ["frame " + " ".join(TIMELINE + list(words))]
    for p in passes:
        values = [scene, 0, 0, 0, p, *(f(p) for f in words.values())]
        lines.append(f"{p + 100} " + " ".join(f"{v:08X}" for v in values))
    return "\n".join(lines) + "\n"


def folder(test: unittest.TestCase, dolphin: dict, dragoon: dict, passes: range = range(1, 19),
           scene: int = RACE, again: tuple = None) -> Path:
    out = temp_dir(test)
    write(out / "dolphin" / "ram.txt", dolphin_ram(dolphin, again=again))
    write(out / "dragoon" / race_words.WORDS, dragoon_words(dragoon, passes, scene))
    return out


def diff(out: Path) -> race_words.Diff:
    return race_words.compare(out / "dolphin" / "ram.txt", out / "dragoon" / race_words.WORDS)


class ExpandTest(unittest.TestCase):
    def test_a_word_is_its_own_watch(self):
        self.assertEqual(race_words.expand("8055b338+2c+300"), ["8055B338+2C+300"])
        self.assertEqual(race_words.expand("80536280"), [SPEED])

    def test_a_span_steps_the_last_offset_by_a_word(self):
        self.assertEqual(race_words.expand("8055B338+2C+300:3"),
                         ["8055B338+2C+300", "8055B338+2C+304", "8055B338+2C+308"])
        self.assertEqual(race_words.expand("8053627C:2"), ["8053627C", SPEED])

    def test_a_bad_span_is_refused(self):
        for text in ("80536280:0", "80536280:x", "8055B338+FFFC:2"):
            with self.subTest(text=text), self.assertRaises(argparse.ArgumentTypeError):
                race_words.expand(text)


class WatchListTest(unittest.TestCase):
    def test_the_timeline_comes_first_and_each_word_once(self):
        self.assertEqual(race_words.watch_list([SPEED, "8053627C:2"]), TIMELINE + ["80536280", "8053627C"])

    def test_a_datagram_over_what_macos_lets_through_is_refused(self):
        # Each chain word's line pair is 15 + 1 + 8 + 1 bytes, the timeline's 5 are 18 each.
        fits = (race_words.DATAGRAM - 1 - 5 * 18) // 25
        race_words.watch_list([f"8055B338+2C+300:{fits}"])
        with self.assertRaisesRegex(Bad, "over the 2048 macOS lets through"):
            race_words.watch_list([f"8055B338+2C+300:{fits + 1}"])

    def test_a_datagram_of_exactly_2048_bytes_goes_through(self):
        # The timeline's 5 lines and the NUL are 91 bytes, 99 plain words 18 each, 7 chain words 25.
        watched = race_words.watch_list(["80530000:99", "8055B338+2C+300:7"])
        self.assertEqual(race_words.datagram(watched), race_words.DATAGRAM)

    def test_the_datagram_counts_each_line_and_the_nul(self):
        self.assertEqual(race_words.datagram(["80536280"]), 8 + 1 + 8 + 1 + 1)


class ReadWordsTest(unittest.TestCase):
    def test_a_path_is_followed_and_its_words_read_together(self):
        link = FakeLink()
        link.put(0x8055B338, struct.pack(">I", 0x81000000))
        link.put(0x8100002C, struct.pack(">I", 0x81200000))
        link.put(0x81200300, struct.pack(">3I", 1, 2, 3))
        link.put(0x80536280, struct.pack(">I", ONE))
        got = race_words.read_words(link, ["8055B338+2C+300", "8055B338+2C+304", "8055B338+2C+308", SPEED])
        self.assertEqual(got, [1, 2, 3, ONE])
        self.assertIn((0x81200300, 12), link.reads)  # the three in one read
        self.assertEqual(link.reads.count((0x8055B338, 4)), 1)  # the path's pointers once

    def test_a_pointer_outside_ram_is_the_word_as_dolphin_s_watcher_gives_it(self):
        link = FakeLink()
        link.put(0x8055B338, struct.pack(">I", 0x81000000))  # +2C there holds 0, outside RAM
        self.assertEqual(race_words.read_words(link, ["8055B338+2C+300", "8055B338+2C"]), [0, 0])
        link.put(0x8100002C, struct.pack(">I", 0x00001234))
        self.assertEqual(race_words.read_words(link, ["8055B338+2C+300"]), [0x1234])

    def test_a_pointer_into_the_uncached_mirror_leads_into_ram(self):
        link = FakeLink()
        link.put(0x8055B338, struct.pack(">I", 0xC1000000))
        link.put(0x8100002C, struct.pack(">I", 0x81200000))
        link.put(0x81200300, struct.pack(">I", 7))
        self.assertEqual(race_words.read_words(link, ["8055B338+2C+300", "8055B338+2C"]), [7, 0x81200000])

    def test_a_run_of_words_longer_than_one_read_takes_two(self):
        link = FakeLink()
        count = race_words.kar_ram.READ_MAX // 4 + 1
        watched = race_words.expand(f"81200000:{count}")
        link.put(0x81200000 + 4 * (count - 1), struct.pack(">I", 9))
        self.assertEqual(race_words.read_words(link, watched)[-1], 9)
        self.assertEqual(link.reads, [(0x81200000, race_words.kar_ram.READ_MAX),
                                      (0x81200000 + race_words.kar_ram.READ_MAX, 4)])


class CompareTest(unittest.TestCase):
    def test_words_that_match_say_how_far(self):
        d = diff(folder(self, {SPEED: lambda p: p}, {SPEED: lambda p: p}))
        self.assertEqual((d.race, d.through, d.differing()), ("Top Ride's race", 18, []))
        self.assertEqual(d.lines()[-1], "1 words match through pass 18")

    def test_each_word_s_first_difference_earliest_first(self):
        d = diff(folder(self, {SPEED: lambda p: ONE, X: lambda p: ONE},
                        {SPEED: lambda p: ONE + (p >= 9), X: lambda p: ONE + 3 * (p >= 5)}))
        self.assertEqual([(w.watch, w.at, w.frame) for w in d.differing()], [(X, 5, 105), (SPEED, 9, 109)])
        self.assertEqual(d.differing()[0].text(),
                         f"{X} first differs at frame 105, pass 5: Dragoon 3F800003, Dolphin 3F800000 "
                         "(1.00000036 against 1, 3 ulp)")

    def test_dolphin_s_value_a_pass_either_side_still_matches(self):
        d = diff(folder(self, {SPEED: lambda p: p}, {SPEED: lambda p: p + 1}, passes=range(1, 18)))
        self.assertEqual(d.differing(), [])
        d = diff(folder(self, {SPEED: lambda p: p}, {SPEED: lambda p: p + 2}))
        self.assertEqual([w.at for w in d.differing()], [1])

    def test_frames_outside_the_race_are_left_out(self):
        d = diff(folder(self, {SPEED: lambda p: p}, {SPEED: lambda p: 999}, scene=MENU))
        self.assertEqual((d.through, d.lines()), (None, ["Top Ride's race: no pass compared"]))

    def test_dragoon_past_the_last_pass_dolphin_shows_is_left_out(self):
        d = diff(folder(self, {SPEED: lambda p: p}, {SPEED: lambda p: p if p <= 18 else 999},
                        passes=range(1, 25)))
        self.assertEqual((d.through, d.frames, d.differing()), (18, (101, 118), []))

    def test_dolphin_s_value_shown_is_the_pass_s_first_field(self):
        d = diff(folder(self, {SPEED: lambda p: p}, {SPEED: lambda p: 500 if p == 9 else p},
                        again=(9, {SPEED: 77})))
        self.assertEqual([(w.at, w.ours, w.theirs) for w in d.differing()], [(9, 500, 9)])

    def test_a_lone_pass_read_at_another_point_of_the_same_draws_isn_t_counted(self):
        d = diff(folder(self, {SPEED: lambda p: p, RAND: lambda p: DRAWS[10 * p]},
                        {SPEED: lambda p: 500 if p == 9 else p,
                         RAND: lambda p: DRAWS[95] if p == 9 else DRAWS[10 * p]}))
        self.assertEqual((d.differing(), d.elsewhere), ([], {9: [SPEED, RAND]}))
        self.assertEqual(d.lines()[1:], [
            "Not counted, since Dragoon read them at another point of the same draws: pass 9 (2 words)",
            "2 words match through pass 18"])

    def test_a_lone_pass_whose_seed_isn_t_on_the_draws_still_counts(self):
        d = diff(folder(self, {SPEED: lambda p: p, RAND: lambda p: DRAWS[10 * p]},
                        {SPEED: lambda p: 500 if p == 9 else p,
                         RAND: lambda p: DRAWS[105] if p == 9 else DRAWS[10 * p]}))
        self.assertEqual([(w.watch, w.at) for w in d.differing()], [(SPEED, 9), (RAND, 9)])
        self.assertEqual(d.elsewhere, {})

    def test_a_lone_pass_counts_unless_every_frame_s_seed_is_on_the_draws(self):
        out = folder(self, {SPEED: lambda p: p, RAND: lambda p: DRAWS[10 * p]},
                     {SPEED: lambda p: 500 if p == 9 else p,
                      RAND: lambda p: DRAWS[95] if p == 9 else DRAWS[10 * p]})
        words = out / "dragoon" / race_words.WORDS
        lines = words.read_text().splitlines()
        lines.insert(10, f"110 {RACE:08X} 00000000 00000000 00000000 00000009 000001F4 {DRAWS[105]:08X}")
        lines[11:] = [f"{int(line.split()[0]) + 1} {line.split(' ', 1)[1]}" for line in lines[11:]]
        words.write_text("\n".join(lines) + "\n")
        self.assertEqual([(w.watch, w.at) for w in diff(out).differing()], [(SPEED, 9), (RAND, 9)])

    def test_a_word_that_differs_two_passes_running_still_counts(self):
        d = diff(folder(self, {SPEED: lambda p: p, RAND: lambda p: DRAWS[10 * p]},
                        {SPEED: lambda p: 500 if p in (9, 10) else p,
                         RAND: lambda p: DRAWS[10 * p + 5] if p in (9, 10) else DRAWS[10 * p]}))
        self.assertEqual([(w.watch, w.at) for w in d.differing()], [(SPEED, 9)])
        self.assertEqual(d.elsewhere, {9: [RAND], 10: [RAND]})
        self.assertIn("2 passes where only 805DCD30, rand.seed, differs", d.lines()[2])

    def test_a_lone_pass_with_dragoon_s_seed_behind_dolphin_s_isn_t_counted(self):
        # Air Ride's pass 1864: Dolphin's field took two steps, Dragoon's frame one.
        d = diff(folder(self, {SPEED: lambda p: p, RAND: lambda p: DRAWS[97] if p == 9 else DRAWS[10 * p]},
                        {SPEED: lambda p: 500 if p == 9 else p,
                         RAND: lambda p: DRAWS[85] if p == 9 else DRAWS[10 * p]}))
        self.assertEqual((d.differing(), d.elsewhere), ([], {9: [SPEED, RAND]}))

    def test_a_lone_pass_with_the_seed_in_step_still_counts(self):
        d = diff(folder(self, {SPEED: lambda p: p, RAND: lambda p: DRAWS[10 * p]},
                        {SPEED: lambda p: 500 if p == 9 else p, RAND: lambda p: DRAWS[10 * p]}))
        self.assertEqual(([(w.watch, w.at) for w in d.differing()], d.elsewhere), ([(SPEED, 9)], {}))

    def test_a_word_that_differs_every_other_pass_still_counts(self):
        d = diff(folder(self, {SPEED: lambda p: p, RAND: lambda p: DRAWS[10 * p]},
                        {SPEED: lambda p: 500 if p in (9, 11) else p, RAND: lambda p: DRAWS[10 * p]}))
        self.assertEqual(([(w.watch, w.at) for w in d.differing()], d.elsewhere), ([(SPEED, 9)], {}))

    def test_a_lone_pass_with_a_seed_dolphin_holds_still_still_counts(self):
        # Top Ride's seed never moves.
        for seed in (DRAWS[0], DRAWS[1]):
            with self.subTest(seed=seed):
                d = diff(folder(self, {SPEED: lambda p: p, RAND: lambda p: DRAWS[0]},
                                {SPEED: lambda p: 500 if p == 9 else p,
                                 RAND: lambda p: seed if p == 9 else DRAWS[0]}))
                self.assertIn((SPEED, 9), [(w.watch, w.at) for w in d.differing()])
                self.assertEqual(d.elsewhere, {})

    def test_a_lone_pass_counts_when_a_frame_s_seed_is_in_step(self):
        for seed in (DRAWS[80], DRAWS[90], DRAWS[100]):  # Dolphin's at passes 8, 9 and 10
            with self.subTest(seed=seed):
                out = folder(self, {SPEED: lambda p: p, RAND: lambda p: DRAWS[10 * p]},
                             {SPEED: lambda p: 500 if p == 9 else p,
                              RAND: lambda p: seed if p == 9 else DRAWS[10 * p]})
                words = out / "dragoon" / race_words.WORDS
                lines = words.read_text().splitlines()
                lines.insert(10, f"110 {RACE:08X} 00000000 00000000 00000000 00000009 00000009 {DRAWS[95]:08X}")
                lines[11:] = [f"{int(line.split()[0]) + 1} {line.split(' ', 1)[1]}" for line in lines[11:]]
                words.write_text("\n".join(lines) + "\n")
                self.assertEqual([(w.watch, w.at) for w in diff(out).differing()], [(SPEED, 9), (RAND, 9)])

    def test_a_lone_pass_at_the_first_pass_compared_still_counts(self):
        d = diff(folder(self, {SPEED: lambda p: p, RAND: lambda p: DRAWS[10 * p]},
                        {SPEED: lambda p: 500 if p == 1 else p,
                         RAND: lambda p: DRAWS[15] if p == 1 else DRAWS[10 * p]}))
        self.assertEqual([(w.watch, w.at) for w in d.differing()], [(SPEED, 1), (RAND, 1)])

    def test_a_lone_pass_before_one_dragoon_skips_still_counts(self):
        d = diff(folder(self, {SPEED: lambda p: p, RAND: lambda p: DRAWS[10 * p]},
                        {SPEED: lambda p: 500 if p == 9 else p,
                         RAND: lambda p: DRAWS[95] if p == 9 else DRAWS[10 * p]},
                        passes=[*range(1, 10), *range(11, 19)]))
        self.assertEqual([(w.watch, w.at) for w in d.differing()], [(SPEED, 9), (RAND, 9)])

    def test_a_seed_a_draw_off_for_good_counts_from_its_first_pass(self):
        d = diff(folder(self, {SPEED: lambda p: p, RAND: lambda p: DRAWS[10 * p]},
                        {SPEED: lambda p: 500 if p == 9 else p,
                         RAND: lambda p: DRAWS[10 * p + (p >= 5)]}))
        self.assertEqual([(w.watch, w.at) for w in d.differing()], [(RAND, 5), (SPEED, 9)])
        self.assertEqual(d.elsewhere, {})

    def test_a_seed_s_run_counts_when_one_pass_of_it_isn_t_between(self):
        d = diff(folder(self, {SPEED: lambda p: p, RAND: lambda p: DRAWS[10 * p]},
                        {SPEED: lambda p: p,
                         RAND: lambda p: {9: DRAWS[95], 10: DRAWS[115]}.get(p, DRAWS[10 * p])}))
        self.assertEqual(([(w.watch, w.at) for w in d.differing()], d.elsewhere), ([(RAND, 9)], {}))

    def test_one_pass_where_only_the_seed_differs(self):
        d = diff(folder(self, {SPEED: lambda p: p, RAND: lambda p: DRAWS[10 * p]},
                        {SPEED: lambda p: p, RAND: lambda p: DRAWS[95] if p == 9 else DRAWS[10 * p]}))
        self.assertEqual(d.lines()[1], "Not counted, since Dragoon read them at another point of the same "
                                       "draws: 1 pass where only 805DCD30, rand.seed, differs")

    def test_a_lone_pass_at_the_last_pass_compared_still_counts(self):
        for last in (18, 17):  # Dolphin's last pass, then one Dolphin shows past Dragoon's last
            with self.subTest(last=last):
                d = diff(folder(self, {SPEED: lambda p: p, RAND: lambda p: DRAWS[10 * p]},
                                {SPEED: lambda p: 500 if p == last else p,
                                 RAND: lambda p: DRAWS[10 * p - 5] if p == last else DRAWS[10 * p]},
                                passes=range(1, last + 1)))
                self.assertEqual([(w.watch, w.at) for w in d.differing()], [(SPEED, last), (RAND, last)])

    def test_between_follows_hsd_rand_s_draws(self):
        self.assertEqual(race_words.draw(0x00B90000), (0x00B90000 * 214013 + 2531011) % 2 ** 32)
        self.assertTrue(race_words.between(DRAWS[0], DRAWS[3], DRAWS[7]))
        self.assertTrue(race_words.between(DRAWS[0], DRAWS[0], DRAWS[7]))
        self.assertTrue(race_words.between(DRAWS[0], DRAWS[7], DRAWS[7]))
        self.assertFalse(race_words.between(DRAWS[0], DRAWS[8], DRAWS[7]))
        self.assertFalse(race_words.between(DRAWS[0], DRAWS[3], DRAWS[7], most=6))
        self.assertTrue(race_words.between(DRAWS[0], DRAWS[3], DRAWS[7], most=7))

    def test_a_run_that_lost_a_field_is_refused(self):
        out = folder(self, {SPEED: lambda p: p}, {SPEED: lambda p: p})
        ram = out / "dolphin" / "ram.txt"
        lines = ram.read_text().splitlines()
        ram.write_text("\n".join(lines[:10] + lines[11:]) + "\n")
        with self.assertRaisesRegex(Bad, "vi.renew_count goes from 9 to 11 at line 11, so a field was lost"):
            diff(out)
        with self.assertRaisesRegex(Bad, "a field was lost"):
            race_words.show(ram, out / "dragoon" / race_words.WORDS, SPEED, range(1, 2))

    def test_renew_count_staying_or_going_back_to_0_loses_nothing(self):
        rows = [(n, {race_words.RENEW: v}) for n, v in enumerate([5, 5, 6, 0, 0, 1, 2], 1)]
        self.assertIsNone(race_words.lost_field(rows))
        self.assertIsNotNone(race_words.lost_field(rows + [(8, {race_words.RENEW: 1})]))

    def test_a_run_with_no_field_is_refused(self):
        out = folder(self, {SPEED: lambda p: p}, {SPEED: lambda p: p})
        ram = out / "dolphin" / "ram.txt"
        ram.write_text(ram.read_text().splitlines()[0] + "\n")
        with self.assertRaisesRegex(Bad, "no field"):
            race_words.show(ram, out / "dragoon" / race_words.WORDS, SPEED, range(1, 2))

    def test_a_pointer_isn_t_shown_as_a_float(self):
        self.assertEqual(race_words.values_text(0x80536280, 0x80536284), "Dragoon 80536280, Dolphin 80536284")

    def test_infinity_and_nan_aren_t_shown_as_floats(self):
        self.assertEqual(race_words.values_text(0x7F800000, 0x7FC00000), "Dragoon 7F800000, Dolphin 7FC00000")
        self.assertEqual(race_words.values_text(0xFF800000, 0x3F800000), "Dragoon FF800000, Dolphin 3F800000")

    def test_ulps_count_across_zero(self):
        self.assertEqual(race_words.ulps(0x00000001, 0x80000001), 2)
        self.assertEqual(race_words.ulps(0x80000000, 0x00000000), 0)

    def test_two_sides_watching_different_words_are_refused(self):
        out = folder(self, {SPEED: lambda p: p}, {X: lambda p: p})
        with self.assertRaisesRegex(Bad, "doesn't watch what"):
            diff(out)

    def test_show_marks_a_pass_whose_value_dolphin_doesn_t_have_near_it(self):
        out = folder(self, {SPEED: lambda p: p}, {SPEED: lambda p: p + (p >= 9) * 5})
        got = race_words.show(out / "dolphin" / "ram.txt", out / "dragoon" / race_words.WORDS, SPEED,
                              range(8, 10))
        self.assertEqual(got[1:], ["8: 00000008 | 00000008", "9: 0000000E | 00000009  *"])

    def test_show_takes_dolphin_s_value_a_pass_either_side_as_near(self):
        out = folder(self, {SPEED: lambda p: p}, {SPEED: lambda p: p + (p == 9) - (p == 12)})
        got = race_words.show(out / "dolphin" / "ram.txt", out / "dragoon" / race_words.WORDS, SPEED,
                              range(9, 13))
        self.assertEqual(got[1:], ["9: 0000000A | 00000009", "10: 0000000A | 0000000A",
                                   "11: 0000000B | 0000000B", "12: 0000000B | 0000000C"])


class CommandTest(unittest.TestCase):
    def route(self):
        return mock.patch.object(race_words, "select_routes", return_value=[Route("r", 30, 60, [20], [])])

    def test_dolphin_plays_the_movie_watching_the_timeline_and_the_words(self):
        out = temp_dir(self)
        with self.route(), mock.patch.object(race_words.subprocess, "run") as run:
            run.return_value.returncode = 0
            code, _, err = run_main(race_words.main, "dolphin", "r", "--movie", "m.dtm", "--fields", "99",
                                    "--out", str(out), "8053627C:2")
        self.assertEqual((code, err), (0, ""))
        cmd = run.call_args[0][0]
        watched = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--watch"]
        self.assertEqual(watched, TIMELINE + ["8053627C", SPEED])
        self.assertNotIn("--dump", cmd)
        self.assertEqual(cmd[cmd.index("--frames") + 1], "99")

    def test_dragoon_plays_pinned_with_the_settings_given_and_writes_the_words(self):
        out = temp_dir(self)
        write(out / "dolphin" / "ram.txt", dolphin_ram({SPEED: lambda p: p}))
        calls = {}

        def play(route, name, every, bot, settings, probe):
            calls.update(settings=settings, every=every, required=route.required)
            run_dir = out / "run"
            run_dir.mkdir()
            link = FakeLink()
            for frame in range(1, 40):
                link.frame = frame
                link.put(0x80536280, struct.pack(">I", frame))
                bot(link)
            return race_words.bot_link.Outcome(39, 39, "exit_after", "", run_dir), bot.states

        with self.route(), mock.patch.object(race_words.state_goldens, "play", side_effect=play):
            code, out_text, err = run_main(race_words.main, "dragoon", "r", "--out", str(out), "--from", "5",
                                           "--to", "7", "--", "GCN_INTERPRET=all")
        self.assertEqual((code, err), (0, ""), out_text)
        self.assertEqual(calls["settings"], ["--disc=console", "DRAGOON_SEED_PIN=1", "GCN_INTERPRET=all"])
        self.assertEqual((calls["every"], calls["required"]), (None, [7]))
        lines = (out / "dragoon" / race_words.WORDS).read_text().splitlines()
        self.assertEqual(lines[0], "frame " + " ".join(TIMELINE + [SPEED]))
        self.assertEqual([line.split()[0] + " " + line.split()[-1] for line in lines[1:]],
                         ["5 00000005", "6 00000006", "7 00000007"])

    def test_diff_prints_the_lines(self):
        out = folder(self, {SPEED: lambda p: p}, {SPEED: lambda p: p + 3 * (p >= 4)})
        code, text, err = run_main(race_words.main, "diff", str(out))
        self.assertEqual((code, err), (0, ""))
        self.assertIn(f"{SPEED} first differs at frame 104, pass 4: Dragoon 00000007, Dolphin 00000004", text)

    def test_a_missing_run_is_an_error(self):
        code, _, err = run_main(race_words.main, "diff", str(temp_dir(self)))
        self.assertEqual(code, 2)
        self.assertIn("ram.txt", err)


if __name__ == "__main__":
    unittest.main()
