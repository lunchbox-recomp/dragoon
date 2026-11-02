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
    def test_a_run_that_reached_its_time_limit_is_no_stop(self) -> None:
        self.assertIsNone(classify(outcome(bot_link.TIME_LIMIT)))

    def test_a_run_that_reached_its_exit_after_is_no_stop_since_bot_link_reports_one_only_when_given(self) -> None:
        self.assertIsNone(classify(outcome(bot_link.EXIT_AFTER, "--exit-after=500")))

    def test_the_game_shutting_itself_down_is_an_exit(self) -> None:
        line = "[reset] the game reset the console (shutdown, code 0)"
        self.assertEqual(classify(outcome(bot_link.SHUTDOWN, line)), Stop(bot_stop.EXIT, line, 4000))

    def test_a_shutdown_after_a_reset_says_so(self) -> None:
        stop = classify(outcome(bot_link.SHUTDOWN, "x"), resets(RESET))
        assert stop is not None
        self.assertTrue(stop.after_reset)

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

    def cut(self, before: int = 0, session: str = "/r/session") -> Detected:
        return Detected(MUSIC, "a music stream ended early", 4000, before, session)

    def test_a_cut_the_log_put_before_a_reset_says_so_and_names_its_process(self) -> None:
        stop = classify(outcome(bot_link.BOT_RAISED, "x", 0, self.cut(0, "/r/session")), resets(RESET))
        self.assertEqual(stop, Stop(MUSIC, "a music stream ended early", None, 0, True, "/r/session"))
        self.assertFalse(stop.after_reset)

    def test_a_cut_after_a_reset_is_after_it_and_a_reset_after_that_is_before_the_next(self) -> None:
        stop = classify(outcome(bot_link.BOT_RAISED, "x", 0, self.cut(1, "/r/session/run-2")), resets(RESET))
        self.assertEqual(stop, Stop(MUSIC, "a music stream ended early", 4000, 1))
        stop = classify(outcome(bot_link.BOT_RAISED, "x", 0, self.cut(1, "/r/session/run-2")), resets(RESET, RESET))
        self.assertEqual(stop, Stop(MUSIC, "a music stream ended early", None, 1, True, "/r/session/run-2"))
        self.assertTrue(stop.after_reset)

    def test_a_cut_with_no_resets_around_it_is_just_a_cut(self) -> None:
        self.assertEqual(classify(outcome(bot_link.BOT_RAISED, "x", 0, self.cut(0)), resets()),
                         Stop(MUSIC, "a music stream ended early", 4000))

    def test_a_finding_that_came_from_no_log_is_after_the_resets_so_far(self) -> None:
        found = Detected(FROZEN, "the picture stayed", 3999)
        stop = classify(outcome(bot_link.BOT_RAISED, "x", 4000, found), resets(RESET, RESET))
        self.assertEqual(stop, Stop(FROZEN, "the picture stayed", 3999, 2))

    def test_a_cut_found_after_a_clean_end_is_the_stop(self) -> None:
        self.assertEqual(classify(outcome(bot_link.TIME_LIMIT), resets(RESET), late=self.cut(1)),
                         Stop(MUSIC, "a music stream ended early", 4000, 1))
        self.assertEqual(classify(outcome(bot_link.EXIT_AFTER, "--exit-after=9"), resets(), late=self.cut(0)),
                         Stop(MUSIC, "a music stream ended early", 4000))

    def test_a_cut_found_late_that_a_reset_followed_names_its_process(self) -> None:
        stop = classify(outcome(bot_link.TIME_LIMIT), resets(RESET), late=self.cut(0, "/r/session"))
        self.assertEqual(stop, Stop(MUSIC, "a music stream ended early", None, 0, True, "/r/session"))

    def test_a_cut_found_late_does_not_replace_a_stop_the_run_had(self) -> None:
        stop = classify(outcome(bot_link.PANIC, "boom"), resets(), late=self.cut())
        assert stop is not None
        self.assertEqual((stop.kind, stop.detail), (bot_stop.PANIC, "boom"))

    def test_nothing_found_late_and_a_clean_end_is_no_stop(self) -> None:
        self.assertIsNone(classify(outcome(bot_link.TIME_LIMIT), resets(RESET), late=None))

    def test_a_hang_after_a_slow_restart_names_the_restart(self) -> None:
        stop = classify(outcome(bot_link.HANG, "no frame for 30 s after frame 3"),
                        resets(RESET, SHADERS.format(24500)), hang=30)
        assert stop is not None
        self.assertEqual(stop.detail, "no frame for 30 s after frame 3. The first reset's shader rebuild took 24.5 s "
                                      "of the 30 s hang limit, so this may be that rebuild; run again with a higher "
                                      "--hang")

    def test_a_read_with_no_answer_after_a_slow_restart_is_not_blamed_on_it(self) -> None:
        detail = "no answer to a read for 30 s at frame 3"
        stop = classify(outcome(bot_link.HANG, detail), resets(RESET, SHADERS.format(24500)), hang=30)
        assert stop is not None
        self.assertEqual((stop.kind, stop.detail), (bot_stop.HANG, detail))

    def test_a_hang_on_the_games_assertion_after_a_slow_restart_is_not_blamed_on_it(self) -> None:
        detail = "no frame for 30 s after frame 3; the game asserted: '[OS] assertion \"made_up != 0\" failed'"
        stop = classify(outcome(bot_link.HANG, detail), resets(RESET, SHADERS.format(24500)), hang=30)
        assert stop is not None
        self.assertEqual((stop.kind, stop.detail), (bot_stop.HANG, detail))

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
