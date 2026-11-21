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


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def dolphin_ram(words: dict, menu: int = 2, fields: int = 22) -> str:
    """A Dolphin run at the menu for MENU fields, then in Top Ride's race. The race's first
    field still shows the menu's count, 50, then 0, then pass k on the race's field k + 2. Each
    of WORDS, a watch to a function of the pass, holds that function's value at every field of
    the pass (of pass 0 before the race)."""
    lines = ["frame " + " ".join(TIMELINE + list(words))]
    for n in range(1, fields + 1):
        k = n - menu
        scene, count = (MENU, 50) if k < 1 else (RACE, 50 if k == 1 else k - 2)
        at = count if scene == RACE and k > 1 else 0
        values = [scene, n, 0, 0x8070E3C0, count, *(f(at) for f in words.values())]
        lines.append(f"{n} " + " ".join(f"{v:08X}" for v in values))
    return "\n".join(lines) + "\n"


def dragoon_words(words: dict, passes: range, scene: int = RACE) -> str:
    """Dragoon at pass P on frame P + 100, each of WORDS its function's value at the pass."""
    lines = ["frame " + " ".join(TIMELINE + list(words))]
    for p in passes:
        values = [scene, 0, 0, 0, p, *(f(p) for f in words.values())]
        lines.append(f"{p + 100} " + " ".join(f"{v:08X}" for v in values))
    return "\n".join(lines) + "\n"


def folder(test: unittest.TestCase, dolphin: dict, dragoon: dict, passes: range = range(1, 19),
           scene: int = RACE) -> Path:
    out = temp_dir(test)
    write(out / "dolphin" / "ram.txt", dolphin_ram(dolphin))
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

    def test_a_pointer_isn_t_shown_as_a_float(self):
        self.assertEqual(race_words.values_text(0x80536280, 0x80536284), "Dragoon 80536280, Dolphin 80536284")

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
