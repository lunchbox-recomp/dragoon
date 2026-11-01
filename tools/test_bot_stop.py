from __future__ import annotations

import unittest
from pathlib import Path

import bot_link
import bot_stop
from bot_menus import Stuck
from bot_stop import SoakError, Stop, classify, near_hang
from bot_watch import FROZEN, MUSIC, Detected, Resets

RESET = "[reset] the game reset the console (restart, code 0)"
SHADERS = "[shaders] 70 programs from cache (0 from binaries, 70 compiled) in {} ms"


def outcome(reason: str, detail: str = "why", last_frame: int | None = 4000,
            error: BaseException | None = None) -> bot_link.Outcome:
    return bot_link.Outcome(100, last_frame, reason, detail, Path("/x/build/probe/t"), None, error)


def resets(*lines: str) -> Resets:
    found = Resets()
    for line in lines:
        found.add(line)
    return found


class ClassifyTest(unittest.TestCase):
    def test_a_run_that_ended_as_a_bot_run_should_is_no_stop(self) -> None:
        for reason in bot_link.CLEAN:
            with self.subTest(reason=reason):
                self.assertIsNone(classify(outcome(reason)))

    def test_the_game_exiting_or_dying_is_an_exit(self) -> None:
        for reason in (bot_link.GAME_EXITED, bot_link.GAME_DIED):
            with self.subTest(reason=reason):
                self.assertEqual(classify(outcome(reason, "the game ended at frame 4000")),
                                 Stop(bot_stop.EXIT, "the game ended at frame 4000", 4000))

    def test_a_panic_is_a_panic(self) -> None:
        self.assertEqual(classify(outcome(bot_link.PANIC, "guest panic: foo.c:12: boom")),
                         Stop(bot_stop.PANIC, "guest panic: foo.c:12: boom", 4000))

    def test_the_engine_stopping_the_game_is_a_stop_with_its_line(self) -> None:
        line = "[bot] frame 4000: a read outside RAM"
        self.assertEqual(classify(outcome(bot_link.ENGINE_STOP, line)), Stop(bot_stop.ENGINE_STOP, line, 4000))

    def test_no_frame_for_the_hang_limit_is_a_hang(self) -> None:
        self.assertEqual(classify(outcome(bot_link.HANG, "no frame for 30 s after frame 4000")),
                         Stop(bot_stop.HANG, "no frame for 30 s after frame 4000", 4000))

    def test_a_frozen_picture_is_the_watchers_finding_and_keeps_its_frame(self) -> None:
        found = Detected(FROZEN, "the picture stayed", 3999)
        self.assertEqual(classify(outcome(bot_link.BOT_RAISED, "Detected: ...", 4000, found)),
                         Stop(FROZEN, "the picture stayed", 3999))

    def test_a_music_stream_ending_early_is_the_watchers_finding_too(self) -> None:
        found = Detected(MUSIC, "a music stream ended early", 4000)
        self.assertEqual(classify(outcome(bot_link.BOT_RAISED, "x", 4000, found)),
                         Stop(MUSIC, "a music stream ended early", 4000))

    def test_a_stuck_menu_is_a_stop_with_the_walkers_words(self) -> None:
        self.assertEqual(classify(outcome(bot_link.BOT_RAISED, "Stuck: x", 4000, Stuck("screen 12 stayed up"))),
                         Stop(bot_stop.MENUS_STUCK, "screen 12 stayed up", 4000))

    def test_a_bot_that_raised_anything_else_says_nothing_about_the_game(self) -> None:
        error = KeyError("scene.minor")
        with self.assertRaisesRegex(SoakError, r"^a bot raised KeyError: 'scene.minor'$") as caught:
            classify(outcome(bot_link.BOT_RAISED, "KeyError: 'scene.minor'", error=error))
        self.assertIs(caught.exception.__cause__, error)

    def test_a_game_that_never_connected_or_a_bad_link_is_not_a_finding(self) -> None:
        for reason in (bot_link.NEVER_LINKED, bot_link.CONNECT_FAILED, bot_link.BAD_LINK):
            with self.subTest(reason=reason), self.assertRaisesRegex(SoakError, f"^{reason}: why$"):
                classify(outcome(reason))

    def test_a_reason_bot_link_adds_later_is_not_taken_for_a_clean_run(self) -> None:
        with self.assertRaisesRegex(SoakError, "^something_new: why$"):
            classify(outcome("something_new"))

    def test_each_reason_bot_link_has_is_a_stop_nothing_or_a_soak_error(self) -> None:
        for reason in (bot_link.TIME_LIMIT, bot_link.EXIT_AFTER, bot_link.SHUTDOWN, bot_link.GAME_EXITED,
                       bot_link.GAME_DIED, bot_link.HANG, bot_link.ENGINE_STOP, bot_link.CONNECT_FAILED,
                       bot_link.PANIC, bot_link.BOT_RAISED, bot_link.NEVER_LINKED, bot_link.BAD_LINK):
            with self.subTest(reason=reason):
                try:
                    found = classify(outcome(reason, error=KeyError("x")))
                except SoakError:
                    continue
                self.assertTrue(found is None or found.kind in bot_stop.KINDS)

    def test_a_stop_after_a_reset_says_so(self) -> None:
        stop = classify(outcome(bot_link.PANIC), resets(RESET))
        assert stop is not None
        self.assertTrue(stop.after_reset)

    def test_a_stop_with_no_reset_before_it_says_so(self) -> None:
        stop = classify(outcome(bot_link.PANIC), resets("[reset] the game reset the console (shutdown, code 0)"))
        assert stop is not None
        self.assertFalse(stop.after_reset)

    def test_a_watchers_stop_after_a_reset_says_so_too(self) -> None:
        found = Detected(MUSIC, "x", 10)
        stop = classify(outcome(bot_link.BOT_RAISED, "x", 10, found), resets(RESET))
        assert stop is not None
        self.assertTrue(stop.after_reset)

    def test_a_hang_after_a_slow_restart_names_the_restart(self) -> None:
        stop = classify(outcome(bot_link.HANG, "no frame for 30 s after frame 3"),
                        resets(RESET, SHADERS.format(24500)), hang=30)
        assert stop is not None
        self.assertEqual(stop.detail, "no frame for 30 s after frame 3. The first reset's shader rebuild took 24.5 s "
                                      "of the 30 s hang limit, so this may be that rebuild; run again with a higher "
                                      "--hang")

    def test_a_hang_after_a_quick_restart_is_just_a_hang(self) -> None:
        stop = classify(outcome(bot_link.HANG, "no frame"), resets(RESET, SHADERS.format(2500)), hang=30)
        assert stop is not None
        self.assertEqual(stop.detail, "no frame")

    def test_another_stop_after_a_slow_restart_is_not_blamed_on_it(self) -> None:
        stop = classify(outcome(bot_link.PANIC, "boom"), resets(RESET, SHADERS.format(29000)), hang=30)
        assert stop is not None
        self.assertEqual(stop.detail, "boom")


class NearHangTest(unittest.TestCase):
    def test_two_thirds_of_the_limit_is_near(self) -> None:
        self.assertFalse(near_hang(19999, 30))
        self.assertTrue(near_hang(20000, 30))
        self.assertTrue(near_hang(60000, 30))

    def test_no_limit_is_never_near(self) -> None:
        self.assertFalse(near_hang(10 ** 9, None))


if __name__ == "__main__":
    unittest.main()
