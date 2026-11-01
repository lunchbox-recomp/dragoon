from __future__ import annotations

import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path

import bot_watch
from bot_link import Pad
from bot_watch import FROZEN, MUSIC, Detected, Frozen, LogWatch, Resets
from testutil import FakeLink

STILL = Pad()
PRESS = Pad(buttons=0x0100)
MUSIC_LOOP = "01808A02"  # a music stream's slot, and its end
MUSIC_END = "018189FF"
SFX_LOOP = "00DCB362"  # an effect's loop address, and its end
SFX_END = "00DD49F4"
PB = "80579F88"
OTHER = "80579FA8"
RESET = "[reset] the game reset the console (restart, code 0)\n"


def axv(n: int, kind: str, pb: str = PB, loop: str = MUSIC_LOOP, end: str = MUSIC_END,
        flags: str = "0 stream=0", cur: str = "00DD0195") -> str:
    return (f"[axv] list={n} pb={pb} {kind} run=1 looping={flags} fmt=00 src=0 loop={loop} end={end} "
            f"cur={cur} ratio=00010000\n")


class Source:
    """The picture a link shows at each frame: the last one set at or before it, None before the first."""

    def __init__(self, *changes: tuple[int, object]) -> None:
        self.changes = sorted(changes, key=lambda c: c[0])
        self.calls = 0

    def __call__(self, link: FakeLink) -> object:
        self.calls += 1
        shown = None
        for frame, picture in self.changes:
            if frame <= link.frame:
                shown = picture
        return shown


def feed(frozen: Frozen, link: FakeLink, frames: range, pads_at: Callable[[int], Pad],
         racing_at: Callable[[int], bool] = lambda frame: True) -> None:
    """Step FROZEN through FRAMES. PADS_AT and RACING_AT say the pads and whether the race bots made them."""
    for frame in frames:
        link.frame = frame
        frozen.look(link, {1: pads_at(frame)}, racing_at(frame))


def pressing(frame: int) -> Pad:
    """A pad that changes every 20 frames, as a bot steering does."""
    return PRESS if (frame // 20) % 2 else STILL


class FrozenTest(unittest.TestCase):
    def test_a_picture_that_stays_for_ten_seconds_while_the_input_changes_is_frozen(self) -> None:
        frozen, link = Frozen(Source((0, b"\x01\x02"))), FakeLink()
        with self.assertRaises(Detected) as caught:
            feed(frozen, link, range(0, 2000), pressing)
        e = caught.exception
        self.assertEqual((e.kind, e.frame), (FROZEN, 600))
        self.assertEqual(str(e), e.detail)
        self.assertEqual(e.detail, "the picture's hash 0102 stayed the same from frame 0 to frame 600, 10.0 s of "
                                   "game time, while the bots' input changed on 30 frames of the last 10 s")

    def test_it_does_not_fire_a_frame_early(self) -> None:
        feed(Frozen(Source((0, 1))), FakeLink(), range(0, 600), pressing)

    def test_a_picture_that_changes_every_nine_seconds_is_not_frozen(self) -> None:
        feed(Frozen(Source(*[(540 * i, i) for i in range(50)])), FakeLink(), range(0, 20000), pressing)

    def test_a_picture_that_changes_every_ten_seconds_exactly_is_not_frozen(self) -> None:
        feed(Frozen(Source(*[(600 * i, i) for i in range(30)])), FakeLink(), range(0, 12000), pressing)

    def test_the_window_starts_at_the_frame_the_picture_changed(self) -> None:
        frozen, link = Frozen(Source((0, 1), (500, 2))), FakeLink()
        with self.assertRaises(Detected) as caught:
            feed(frozen, link, range(0, 3000), pressing)
        self.assertEqual(caught.exception.frame, 1100)
        self.assertIn("from frame 500 to frame 1100", caught.exception.detail)

    def test_a_picture_that_stays_while_the_input_does_is_not_frozen(self) -> None:
        feed(Frozen(Source((0, 1))), FakeLink(), range(0, 5000), lambda frame: STILL)

    def test_one_change_of_the_pads_is_not_enough_and_two_are(self) -> None:
        feed(Frozen(Source((0, 1))), FakeLink(), range(0, 900), lambda frame: PRESS if frame >= 100 else STILL)
        with self.assertRaises(Detected) as caught:
            feed(Frozen(Source((0, 1))), FakeLink(), range(0, 900),
                 lambda frame: PRESS if 100 <= frame < 130 else STILL)
        self.assertEqual(caught.exception.frame, 600)

    def test_changes_older_than_the_window_do_not_count(self) -> None:
        frozen, link = Frozen(Source((0, 1))), FakeLink()
        feed(frozen, link, range(0, 40), lambda frame: PRESS if 10 <= frame < 20 else STILL)
        feed(frozen, link, range(700, 720), lambda frame: STILL)  # the frames can jump; the changes are long past

    def test_the_pads_are_compared_whole(self) -> None:
        with self.assertRaises(Detected):
            feed(Frozen(Source((0, 1))), FakeLink(), range(0, 1000), lambda frame: Pad(sx=100 + (frame // 10) % 2))

    def test_a_frame_the_menus_play_starts_the_window_over(self) -> None:
        with self.assertRaises(Detected) as caught:
            feed(Frozen(Source((0, 1))), FakeLink(), range(0, 2500), pressing, racing_at=lambda frame: frame != 500)
        self.assertEqual(caught.exception.frame, 1101)
        self.assertIn("from frame 501 to frame 1101", caught.exception.detail)

    def test_the_picture_is_not_asked_for_on_a_menu_frame(self) -> None:
        shown = Source((0, 1))
        feed(Frozen(shown), FakeLink(), range(0, 100), pressing, racing_at=lambda frame: False)
        self.assertEqual(shown.calls, 0)

    def test_a_link_with_no_hash_never_fires_and_counts_none(self) -> None:
        frozen = Frozen()
        feed(frozen, FakeLink(), range(0, 5000), pressing)
        self.assertEqual(frozen.hashes, 0)

    def test_a_picture_attribute_on_the_link_is_the_default_source(self) -> None:
        frozen, link = Frozen(), FakeLink()
        link.picture = b"\xaa"  # type: ignore[attr-defined]
        with self.assertRaises(Detected):
            feed(frozen, link, range(0, 1000), pressing)
        self.assertEqual(frozen.hashes, 601)

    def test_a_hash_that_goes_missing_starts_the_window_over(self) -> None:
        feed(Frozen(Source((0, 1), (400, None), (410, 1))), FakeLink(), range(0, 1000), pressing)

    def test_a_new_connection_starts_the_window_over(self) -> None:
        frozen, link = Frozen(Source((0, 1))), FakeLink()
        feed(frozen, link, range(0, 500), pressing)
        link.starts = 2
        feed(frozen, link, range(500, 1000), pressing)

    def test_frame_numbers_that_go_back_start_the_window_over(self) -> None:
        frozen, link = Frozen(Source((0, 1))), FakeLink()
        feed(frozen, link, range(400, 900), pressing)
        feed(frozen, link, range(0, 500), pressing)

    def test_the_time_is_a_setting(self) -> None:
        with self.assertRaises(Detected) as caught:
            feed(Frozen(Source((0, 1)), seconds=2), FakeLink(), range(0, 1000), pressing)
        self.assertEqual(caught.exception.frame, 120)


class ResetsTest(unittest.TestCase):
    SHADERS = ("[shaders] 70 programs from cache (0 from binaries, 70 compiled, 0 of them from the game's key list) "
               "in 2107 ms")

    def feed(self, resets: Resets, *lines: str) -> None:
        for line in lines:
            resets.add(line)

    def test_restarts_and_hot_resets_count_and_a_shutdown_does_not(self) -> None:
        resets = Resets()
        self.feed(resets, "[reset] the game reset the console (restart, code 0)",
                  "[reset] the game reset the console (hot reset, code 0)",
                  "[reset] the game reset the console (shutdown, code 0)")
        self.assertEqual(resets.count, 2)

    def test_the_first_resets_shader_line_is_kept(self) -> None:
        seen: list[tuple[str, int]] = []
        resets = Resets(lambda line, ms: seen.append((line, ms)))
        self.feed(resets, RESET.strip(), "[session] build/probe/t/session/run-2", self.SHADERS)
        self.assertEqual((resets.shaders, resets.shaders_ms), (self.SHADERS, 2107))
        self.assertEqual(seen, [(self.SHADERS, 2107)])

    def test_the_boot_before_any_reset_is_not_the_restart(self) -> None:
        resets = Resets()
        self.feed(resets, self.SHADERS)
        self.assertEqual((resets.shaders, resets.count), (None, 0))

    def test_a_later_resets_line_does_not_replace_the_first(self) -> None:
        seen: list[int] = []
        resets = Resets(lambda line, ms: seen.append(ms))
        self.feed(resets, RESET.strip(), self.SHADERS, RESET.strip(), self.SHADERS.replace("2107", "99"))
        self.assertEqual((resets.count, resets.shaders_ms, seen), (2, 2107, [2107]))

    def test_a_shutdown_waits_for_no_shader_line(self) -> None:
        resets = Resets()
        self.feed(resets, "[reset] the game reset the console (shutdown, code 0)", self.SHADERS)
        self.assertIsNone(resets.shaders)

    def test_the_background_build_lines_are_not_the_restart(self) -> None:
        resets = Resets()
        self.feed(resets, RESET.strip(), "[shaders] built program 12 in the background in 4.5 ms")
        self.assertIsNone(resets.shaders)


class LogWatchTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "stdout.txt"
        self.watch = LogWatch(self.path)

    def write(self, text: str, mode: str = "a") -> None:
        with open(self.path, mode) as f:
            f.write(text)

    def test_no_log_yet_is_nothing_to_see(self) -> None:
        self.watch.look(0)
        self.watch.finish(0)
        self.assertFalse(self.watch.axv)

    def test_a_stream_that_ends_early_raises_music_cut_with_its_row(self) -> None:
        self.write(axv(100, "run") + axv(120, "end"))
        with self.assertRaises(Detected) as caught:
            self.watch.look(500)
        e = caught.exception
        self.assertEqual((e.kind, e.frame), (MUSIC, 500))
        self.assertIn(f"a music stream ended early: pb {PB}  list 100", e.detail)
        self.assertIn("ended early at list 120", e.detail)

    def test_a_stream_the_game_stops_is_not_early(self) -> None:
        self.write(axv(100, "run", flags="1 stream=1") + axv(120, "stop", flags="1 stream=1"))
        self.watch.look(0)
        self.assertTrue(self.watch.axv)

    def test_music_the_game_ends_by_giving_one_voice_an_effect_and_stopping_the_other_is_not_a_cut(self) -> None:
        # Soak 544282's stop, in one list: the other voice stopped and this one given an effect's sample.
        self.write(axv(601347, "run", loop="01878A02", end="018889FF", flags="1 stream=0", cur="01878A02")
                   + axv(601347, "run", pb=OTHER, loop="01868A02", end="018789FF", flags="1 stream=0", cur="01868A02")
                   + axv(608157, "stop", pb=OTHER, loop="01848A02", end="01897DBF", flags="1 stream=0")
                   + axv(608157, "set", loop="00BEC7C2", end="00BED1EC", cur="00BEC7C2")
                   + axv(608185, "end", loop="00BEC7C2", end="00BED1EC", cur="00BED1ED"))
        self.watch.look(0)
        self.watch.finish(0)
        self.assertTrue(self.watch.axv)

    def test_an_effect_the_mixer_ends_is_not_early(self) -> None:
        self.write(axv(100, "run", loop=SFX_LOOP, end=SFX_END, flags="1 stream=1")
                   + axv(120, "end", loop=SFX_LOOP, end=SFX_END, flags="0 stream=0"))
        self.watch.look(0)

    def test_the_log_is_read_every_sixty_frames_and_not_in_between(self) -> None:
        self.watch.look(0)
        self.write(axv(100, "run") + axv(120, "end"))
        for frame in (1, 30, 59):
            self.watch.look(frame)
        with self.assertRaises(Detected):
            self.watch.look(60)

    def test_a_line_is_taken_once(self) -> None:
        self.write(axv(100, "run"))
        self.watch.look(0)
        self.write(axv(120, "end"))
        with self.assertRaises(Detected):
            self.watch.look(60)
        self.watch.look(120)  # the end line isn't read again

    def test_half_a_line_waits_for_the_rest(self) -> None:
        end = axv(120, "end")
        self.write(axv(100, "run") + end[:50])
        self.watch.look(0)
        self.write(end[50:])
        with self.assertRaises(Detected):
            self.watch.look(60)

    def test_a_log_that_starts_over_is_read_from_its_start(self) -> None:
        self.write(axv(100, "run") + "x" * 400 + "\n")
        self.watch.look(0)
        self.write(axv(5, "run") + axv(9, "end"), mode="w")
        with self.assertRaises(Detected):
            self.watch.look(60)

    def test_frames_that_go_back_make_the_next_look_a_read(self) -> None:
        self.watch.look(9000)
        self.write(axv(100, "run") + axv(120, "end"))
        with self.assertRaises(Detected):
            self.watch.look(3)

    def moved(self) -> tuple[str, str]:
        """The lines of a voice the game moved to the next slot, and the mixer's end of it."""
        return (axv(100, "run", loop=SFX_LOOP, end=SFX_END) + axv(110, "set", loop=SFX_LOOP, end=MUSIC_END),
                axv(120, "end", loop=SFX_LOOP, end=MUSIC_END))

    def test_a_voice_the_game_moved_and_the_mixer_ended_is_early(self) -> None:
        run_and_set, end = self.moved()
        self.write(run_and_set + end)
        with self.assertRaises(Detected):
            self.watch.look(0)

    def test_a_new_session_starts_the_voices_over(self) -> None:
        run_and_set, end = self.moved()
        self.write(run_and_set + "[session] build/probe/t/session/run-2\n" + end)
        self.watch.look(0)

    def test_resets_are_counted_as_the_lines_come(self) -> None:
        self.write(RESET)
        self.watch.look(0)
        self.assertEqual(self.watch.resets.count, 1)

    def test_the_first_resets_shader_line_reaches_the_callback(self) -> None:
        seen: list[int] = []
        watch = LogWatch(self.path, lambda line, ms: seen.append(ms))
        self.write(RESET + "[shaders] 70 programs from cache (0 from binaries, 70 compiled) in 21500 ms\n")
        watch.look(0)
        self.assertEqual(seen, [21500])

    def test_finish_reads_the_lines_a_look_has_not_got_to(self) -> None:
        self.watch.look(0)
        self.write(axv(100, "run") + axv(120, "end"))
        self.watch.look(10)
        with self.assertRaises(Detected) as caught:
            self.watch.finish(77)
        self.assertEqual(caught.exception.frame, 77)

    def test_a_log_bigger_than_a_chunk_is_read_in_pieces(self) -> None:
        old = bot_watch.LOG_CHUNK
        bot_watch.LOG_CHUNK = 300
        self.addCleanup(setattr, bot_watch, "LOG_CHUNK", old)
        self.write("".join(axv(n, "run", pb=f"{0x80000000 + n * 0x40:08X}") for n in range(40))
                   + axv(5000, "run", pb=OTHER) + axv(5001, "end", pb=OTHER))
        with self.assertRaises(Detected):
            self.watch.finish(10)

    SHADERS = "[shaders] 70 programs from cache (0 from binaries, 70 compiled) in 2107 ms\n"

    def test_every_line_of_a_read_is_handled_when_one_of_them_is_a_cut(self) -> None:
        self.write("[session] /a/session\n" + axv(100, "run") + axv(120, "end") + RESET
                   + "[session] /a/session/run-2\n" + self.SHADERS)
        with self.assertRaises(Detected):
            self.watch.look(0)
        self.assertEqual((self.watch.resets.count, self.watch.resets.shaders_ms), (1, 2107))

    def test_a_cut_knows_the_resets_that_came_before_it_and_the_session_it_was_in(self) -> None:
        self.write("[session] /a/session\n" + axv(100, "run") + axv(120, "end") + RESET)
        with self.assertRaises(Detected) as caught:
            self.watch.look(0)
        self.assertEqual((caught.exception.resets, caught.exception.session), (0, "/a/session"))

    def test_a_cut_after_a_reset_counts_it_and_is_in_the_new_session(self) -> None:
        self.write("[session] /a/session\n" + RESET + "[session] /a/session/run-2\n" + axv(100, "run")
                   + axv(120, "end"))
        with self.assertRaises(Detected) as caught:
            self.watch.look(0)
        self.assertEqual((caught.exception.resets, caught.exception.session), (1, "/a/session/run-2"))

    def test_the_first_cut_of_a_read_is_the_one_that_is_raised(self) -> None:
        self.write(axv(100, "run") + axv(120, "end") + axv(200, "run", pb=OTHER) + axv(220, "end", pb=OTHER))
        with self.assertRaises(Detected) as caught:
            self.watch.look(0)
        self.assertIn("pb 80579F88  list 100", caught.exception.detail)

    def test_a_cut_is_raised_once(self) -> None:
        self.write(axv(100, "run") + axv(120, "end"))
        with self.assertRaises(Detected):
            self.watch.look(0)
        self.watch.look(60)
        self.watch.finish(60)

    def test_finish_reads_all_the_pieces_of_a_big_log_before_it_raises_the_cut(self) -> None:
        old = bot_watch.LOG_CHUNK
        bot_watch.LOG_CHUNK = 300
        self.addCleanup(setattr, bot_watch, "LOG_CHUNK", old)
        self.write(axv(100, "run") + axv(120, "end")
                   + "".join(axv(n, "run", pb=f"{0x80000000 + n * 0x40:08X}") for n in range(40)) + RESET)
        with self.assertRaises(Detected) as caught:
            self.watch.finish(10)
        self.assertEqual((caught.exception.resets, self.watch.resets.count), (0, 1))

    def test_a_log_with_no_axv_lines_says_so(self) -> None:
        self.write("[session] x\nsome other line\n")
        self.watch.finish(0)
        self.assertFalse(self.watch.axv)


if __name__ == "__main__":
    unittest.main()
