from __future__ import annotations

import unittest
from collections.abc import Callable

import bot_menus
import kar_ram
from bot_link import BUTTONS, Pad
from bot_menus import AIR_RIDE, CITY_TRIAL, TOP_RIDE, Menus, Schedule, Stuck
from testgame import FakeGame, play_through
from testutil import FakeLink

A, B, START = BUTTONS["A"], BUTTONS["B"], BUTTONS["START"]
UP, DOWN, LEFT, RIGHT = BUTTONS["UP"], BUTTONS["DOWN"], BUTTONS["LEFT"], BUTTONS["RIGHT"]
TABLE = kar_ram.load()

Steps = "list[tuple[int, dict[int, int] | None]]"


def screen(link: FakeLink, minor: int, **named: int) -> None:
    """Put the game on a screen, with the menu values named as menu__mode=2 for menu.mode."""
    link.set("scene.minor", minor)
    for name, value in named.items():
        link.set(name.replace("__", "."), value)


def run(menus: Menus, link: FakeLink, frames: int, first: int | None = None,
        changes: dict[int, Callable[[], None]] | None = None) -> Steps:
    """Step MENUS once for each of FRAMES frames from FIRST (the link's frame by default), as
    (frame, buttons by port), the buttons None where the menus gave the frame to the race bots.
    CHANGES is what to do to the game before a frame is stepped."""
    start = link.frame if first is None else first
    out = []
    for frame in range(start, start + frames):
        link.frame = frame
        if changes and frame in changes:
            changes[frame]()
        pads = menus.step(link)
        out.append((frame, None if pads is None else {port: pad.buttons for port, pad in pads.items()}))
    return out


def presses(steps: Steps) -> list[tuple[int, dict[int, int]]]:
    """The frames a button went down on a port, with the buttons that port held."""
    out: list[tuple[int, dict[int, int]]] = []
    last: dict[int, int] = {}
    for frame, buttons in steps:
        now = {} if buttons is None else buttons
        down = {port: b for port, b in now.items() if b and b != last.get(port)}
        if down:
            out.append((frame, down))
        last = now
    return out


def first_press(menus: Menus, link: FakeLink, frames: int = 200) -> dict[int, int]:
    found = presses(run(menus, link, frames))
    assert found, "nothing was pressed"
    return found[0][1]


def make(ports: int = 1, modes: tuple[str, ...] = (AIR_RIDE,), seed: int = 0, **kw) -> tuple[Menus, FakeLink, list[str]]:
    said: list[str] = []
    return Menus(ports, Schedule(seed, modes), say=said.append, **kw), FakeLink(), said


class ScheduleTest(unittest.TestCase):
    EVERY = (AIR_RIDE, TOP_RIDE, CITY_TRIAL)

    def modes(self, seed: int, modes: tuple[str, ...], n: int) -> list[str]:
        schedule = Schedule(seed, modes)
        return [schedule.mode() for _ in range(n)]

    def test_one_seed_gives_one_schedule(self) -> None:
        self.assertEqual(self.modes(3, self.EVERY, 60), self.modes(3, self.EVERY, 60))
        a, b = Schedule(3, self.EVERY), Schedule(3, self.EVERY)
        self.assertEqual([a.course() for _ in range(40)], [b.course() for _ in range(40)])

    def test_each_pass_through_the_modes_plays_each_once(self) -> None:
        got = self.modes(1, self.EVERY, 30)
        for i in range(0, 30, 3):
            self.assertEqual(sorted(got[i:i + 3]), sorted(self.EVERY))

    def test_the_order_changes_from_pass_to_pass_and_with_the_seed(self) -> None:
        got = self.modes(1, self.EVERY, 60)
        self.assertGreater(len({tuple(got[i:i + 3]) for i in range(0, 60, 3)}), 1)
        self.assertNotEqual(self.modes(1, self.EVERY, 60), self.modes(2, self.EVERY, 60))

    def test_one_mode_is_the_only_mode(self) -> None:
        self.assertEqual(set(self.modes(5, (CITY_TRIAL,), 10)), {CITY_TRIAL})

    def test_courses_are_the_eight_a_blank_card_opens(self) -> None:
        schedule = Schedule(4, (AIR_RIDE,))
        self.assertEqual({schedule.course() for _ in range(400)}, set(range(8)))

    def test_the_seed_gives_these_first_rounds_on_any_python(self) -> None:
        schedule = Schedule(0, self.EVERY)
        self.assertEqual(([schedule.mode() for _ in range(3)], [schedule.course() for _ in range(3)]),
                         (["city-trial", "top-ride", "air-ride"], [3, 2, 4]))

    def test_bad_modes_and_seeds_are_value_errors(self) -> None:
        for seed, modes in ((0, ()), (0, ("air",)), (-1, (AIR_RIDE,))):
            with self.subTest(seed=seed, modes=modes), self.assertRaises(ValueError):
                Schedule(seed, modes)


class PressTest(unittest.TestCase):
    def test_a_press_is_down_for_the_hold_and_then_up_while_the_screen_answers(self) -> None:
        menus, link, _ = make()
        screen(link, bot_menus.MOVIES[0])
        down = [frame for frame, buttons in run(menus, link, 120) if buttons and buttons[1]]
        self.assertEqual(down[:bot_menus.HOLD], list(range(bot_menus.HOLD)))
        self.assertEqual(down[bot_menus.HOLD], bot_menus.HOLD + bot_menus.SETTLE)

    def test_the_screen_is_read_only_when_a_press_is_due_and_not_while_one_is_down_or_settling(self) -> None:
        menus, link, _ = make()
        screen(link, bot_menus.MOVIES[0])
        run(menus, link, bot_menus.HOLD + bot_menus.SETTLE)
        self.assertEqual(link.reads, [(TABLE["scene.minor"].address, 1)])
        run(menus, link, 1, first=bot_menus.HOLD + bot_menus.SETTLE)
        self.assertEqual(len(link.reads), 2)

    def test_the_screen_is_the_first_thing_read_so_values_off_their_own_screen_are_not(self) -> None:
        menus, link, _ = make()
        screen(link, bot_menus.RACE, menu__page=1, menu__mode=2, player_select__port1=3)
        run(menus, link, 500)
        self.assertEqual({addr for addr, _ in link.reads}, {TABLE["scene.minor"].address})

    def test_a_cursor_is_read_after_the_screen_that_owns_it(self) -> None:
        menus, link, _ = make()
        screen(link, bot_menus.AIR_COURSES, course_select__cursor=0)
        run(menus, link, 1)
        self.assertEqual([addr for addr, _ in link.reads],
                         [TABLE["scene.minor"].address, TABLE["course_select.cursor"].address])

    def test_only_the_ports_a_tap_names_press(self) -> None:
        menus, link, _ = make(ports=4)
        screen(link, bot_menus.CITY_PLAYERS, player_select__port2=3, player_select__port4=3)
        self.assertEqual(first_press(menus, link), {1: A, 3: A})

    def test_every_port_gets_a_pad_every_frame(self) -> None:
        menus, link, _ = make(ports=3)
        screen(link, bot_menus.MOVIES[2])
        for _, buttons in run(menus, link, 200):
            self.assertEqual(sorted(buttons), [1, 2, 3])

    def test_the_pads_are_pads(self) -> None:
        menus, link, _ = make()
        screen(link, bot_menus.AIR_RESULTS)
        self.assertEqual(menus.step(link), {1: Pad(buttons=START)})

    def test_a_tap_with_no_buttons_is_a_wait(self) -> None:
        menus, link, _ = make()
        screen(link, bot_menus.AIR_MACHINES, machine_select__port1=2)
        self.assertEqual(presses(run(menus, link, 300)), [])
        self.assertGreater(len(link.reads), 5)

    def test_a_tap_holds_five_frames_and_waits_forty_five(self) -> None:
        tap = bot_menus.Tap(A)
        self.assertEqual((tap.hold, tap.settle, tap.ports), (5, 45, (1,)))


class ScreenTest(unittest.TestCase):
    def one(self, minor: int, ports: int = 1, **named: int) -> dict[int, int]:
        menus, link, _ = make(ports=ports, modes=(CITY_TRIAL,))
        screen(link, minor, **named)
        return first_press(menus, link)

    def test_the_first_screens_get_a(self) -> None:
        self.assertEqual(self.one(bot_menus.BOOT), {1: A})

    def test_the_title_takes_a_and_then_start_a_hundred_frames_apart_as_the_routes_do(self) -> None:
        menus, link, _ = make()
        screen(link, bot_menus.TITLE)
        self.assertEqual(presses(run(menus, link, 450))[:4],
                         [(0, {1: A}), (100, {1: START}), (200, {1: A}), (300, {1: START})])

    def test_a_movie_is_skipped_by_every_port(self) -> None:
        for minor in bot_menus.MOVIES:
            with self.subTest(minor=minor):
                self.assertEqual(self.one(minor, ports=4), {1: A, 2: A, 3: A, 4: A})

    def test_results_stats_and_the_stadium_card(self) -> None:
        self.assertEqual(self.one(bot_menus.AIR_RESULTS), {1: START})
        self.assertEqual(self.one(bot_menus.STADIUM_RESULTS), {1: START})
        self.assertEqual(self.one(bot_menus.CITY_STATS), {1: A})
        self.assertEqual(self.one(bot_menus.STADIUM_CARD), {1: A})

    def test_a_stadiums_results_take_start_on_every_port(self) -> None:
        # A four-player soak's Destruction Derby results waited for START from each player.
        self.assertEqual(self.one(bot_menus.STADIUM_RESULTS, ports=4), {1: START, 2: START, 3: START, 4: START})

    def test_a_stadiums_results_are_not_an_unconfirmed_step(self) -> None:
        # A soak watched START on them go to the checklist and then City Trial's player entry.
        menus, link, said = make()
        screen(link, bot_menus.STADIUM_RESULTS)
        run(menus, link, 1000)
        self.assertEqual([line for line in said if line.startswith("unconfirmed step") and "cadence" not in line], [])

    def test_game_settings_are_left_by_b(self) -> None:
        self.assertEqual(self.one(bot_menus.CITY_SETTINGS), {1: B})

    def test_top_rides_course_select_takes_a(self) -> None:
        self.assertEqual(self.one(bot_menus.TOP_COURSES), {1: A})

    def test_the_checklist_is_named_and_gets_a(self) -> None:
        menus, link, said = make()
        screen(link, bot_menus.CHECKLIST)
        self.assertEqual(first_press(menus, link), {1: A})
        self.assertIsNotNone(TABLE["scene.minor"].meaning(bot_menus.CHECKLIST))
        self.assertEqual([line for line in said if "screen 34" in line or "other screen" in line], [])

    def test_an_unnamed_screen_gets_a_and_is_said_once(self) -> None:
        menus, link, said = make()
        screen(link, 12)
        found = presses(run(menus, link, 500))
        self.assertGreater(len(found), 3)
        self.assertTrue(all(buttons == {1: A} for _, buttons in found))
        self.assertEqual([line for line in said if "screen 12" in line], ["screen 12 isn't in kar_ram.json; pressing A"])


class MainMenuTest(unittest.TestCase):
    def press(self, goal: str, page: int, mode: int) -> dict[int, int]:
        menus, link, _ = make(modes=(goal,))
        screen(link, bot_menus.MAIN_MENU, menu__page=page, menu__mode=mode)
        return first_press(menus, link)

    def test_the_mode_select_moves_the_cursor_to_the_goal(self) -> None:
        self.assertEqual(self.press(CITY_TRIAL, 0, 0), {1: DOWN})
        self.assertEqual(self.press(CITY_TRIAL, 0, 1), {1: DOWN})
        self.assertEqual(self.press(TOP_RIDE, 0, 0), {1: DOWN})
        self.assertEqual(self.press(AIR_RIDE, 0, 2), {1: UP})
        self.assertEqual(self.press(TOP_RIDE, 0, 4), {1: UP})

    def test_the_cursor_on_the_goal_takes_a(self) -> None:
        for goal, mode in ((AIR_RIDE, 0), (TOP_RIDE, 1), (CITY_TRIAL, 2)):
            with self.subTest(goal=goal):
                self.assertEqual(self.press(goal, 0, mode), {1: A})

    def test_a_modes_own_menu_starts_the_game_when_it_is_the_goals(self) -> None:
        for goal, mode in ((AIR_RIDE, 0), (TOP_RIDE, 1), (CITY_TRIAL, 2)):
            with self.subTest(goal=goal):
                self.assertEqual(self.press(goal, 1, mode), {1: A})

    def test_a_modes_own_menu_moves_the_cursor_up_to_start_game_before_it_presses_a(self) -> None:
        for item in (1, 2, 3):
            with self.subTest(item=item):
                menus, link, _ = make(modes=(CITY_TRIAL,))
                screen(link, bot_menus.MAIN_MENU, menu__page=1, menu__mode=2, menu__item=item)
                self.assertEqual(first_press(menus, link), {1: UP})

    def test_the_climb_gives_up_after_three_ups_that_leave_the_row_alone(self) -> None:
        for goal, mode in ((AIR_RIDE, 0), (TOP_RIDE, 1), (CITY_TRIAL, 2)):
            with self.subTest(goal=goal):
                menus, link, _ = make(modes=(goal,))
                screen(link, bot_menus.MAIN_MENU, menu__page=1, menu__mode=mode, menu__item=2)
                self.assertEqual([buttons[1] for _, buttons in presses(run(menus, link, 400))][:6],
                                 [UP, UP, UP, A, A, A])

    def test_the_ups_are_counted_again_when_the_menu_comes_back_after_another_screen(self) -> None:
        menus, link, _ = make(modes=(TOP_RIDE,))
        menu = dict(menu__page=1, menu__mode=1, menu__item=2)  # a row that never moves
        screen(link, bot_menus.MAIN_MENU, **menu)
        changes = {300: lambda: screen(link, bot_menus.AIR_RESULTS), 400: lambda: screen(link, bot_menus.MAIN_MENU, **menu)}
        found = presses(run(menus, link, 700, changes=changes))
        self.assertEqual([buttons[1] for frame, buttons in found if frame < 300][:4], [UP, UP, UP, A])
        self.assertEqual([buttons[1] for frame, buttons in found if frame >= 400][:4], [UP, UP, UP, A])

    def test_a_row_that_moves_is_climbed_however_many_ups_it_takes(self) -> None:
        menus, link, _ = make(modes=(TOP_RIDE,))
        screen(link, bot_menus.MAIN_MENU, menu__page=1, menu__mode=1, menu__item=3)
        # The looks come every 50 frames, and each row is seen twice, as when a press is missed.
        changes = {99: lambda: link.set("menu.item", 2), 199: lambda: link.set("menu.item", 1),
                   299: lambda: link.set("menu.item", 0)}
        self.assertEqual([buttons[1] for _, buttons in presses(run(menus, link, 400, changes=changes))][:8],
                         [UP, UP, UP, UP, UP, UP, A, A])

    def test_the_row_is_read_only_on_the_goals_own_menu(self) -> None:
        item = TABLE["menu.item"].address
        menus, link, _ = make(modes=(TOP_RIDE,))
        screen(link, bot_menus.MAIN_MENU, menu__page=1, menu__mode=0, menu__item=3)  # another mode's
        first_press(menus, link)
        self.assertNotIn(item, [addr for addr, _ in link.reads])
        menus, link, _ = make(modes=(TOP_RIDE,))
        screen(link, bot_menus.MAIN_MENU, menu__page=0, menu__mode=1, menu__item=3)  # the mode select
        first_press(menus, link)
        self.assertNotIn(item, [addr for addr, _ in link.reads])
        menus, link, _ = make(modes=(TOP_RIDE,))
        screen(link, bot_menus.MAIN_MENU, menu__page=1, menu__mode=1)
        first_press(menus, link)
        self.assertEqual([addr for addr, _ in link.reads][-1], item)

    def test_another_modes_own_menu_is_left_by_b_and_nothing_is_said_to_be_unconfirmed(self) -> None:
        # A soak changed modes this way and the next round began in the new mode.
        menus, link, said = make(modes=(TOP_RIDE,))
        screen(link, bot_menus.MAIN_MENU, menu__page=1, menu__mode=0)
        self.assertEqual(first_press(menus, link), {1: B})
        self.assertEqual([line for line in said if line.startswith("unconfirmed step") and "cadence" not in line], [])

    def test_the_goal_is_drawn_once_and_a_round_is_counted_for_it(self) -> None:
        menus, link, said = make(modes=(CITY_TRIAL,))
        screen(link, bot_menus.MAIN_MENU, menu__page=0, menu__mode=0)
        run(menus, link, 400)
        self.assertEqual((menus.rounds, menus.goal), (1, CITY_TRIAL))
        self.assertEqual([line for line in said if line.startswith("round ")], ["round 1: city-trial"])


class CourseTest(unittest.TestCase):
    def cursor(self, at: int, want: int) -> dict[int, int]:
        menus, link, _ = make()
        menus.course = want
        screen(link, bot_menus.AIR_COURSES, course_select__cursor=at)
        return first_press(menus, link)

    def test_the_cursor_goes_along_its_row_and_then_down_or_up(self) -> None:
        self.assertEqual(self.cursor(0, 2), {1: RIGHT})
        self.assertEqual(self.cursor(4, 2), {1: LEFT})
        self.assertEqual(self.cursor(5, 7), {1: RIGHT})
        self.assertEqual(self.cursor(7, 5), {1: LEFT})
        self.assertEqual(self.cursor(2, 7), {1: DOWN})
        self.assertEqual(self.cursor(7, 2), {1: UP})
        self.assertEqual(self.cursor(6, 1), {1: UP})

    def test_the_cursor_on_the_course_takes_a(self) -> None:
        for course in range(8):
            with self.subTest(course=course):
                self.assertEqual(self.cursor(course, course), {1: A})

    def test_the_target_is_drawn_once_and_kept_until_the_race_starts(self) -> None:
        menus, link, _ = make(seed=9)
        screen(link, bot_menus.AIR_COURSES, course_select__cursor=0)
        run(menus, link, 20)
        chosen = menus.course
        self.assertIsNotNone(chosen)
        run(menus, link, 500)
        self.assertEqual(menus.course, chosen)

    def test_every_course_is_one_the_game_showed_and_none_is_said_to_be_unconfirmed(self) -> None:
        for course in bot_menus.COURSES:
            with self.subTest(course=course):
                self.assertIsNotNone(TABLE["course_select.cursor"].meaning(course))
                menus, link, said = make()
                menus.course = course
                screen(link, bot_menus.AIR_COURSES, course_select__cursor=0)
                run(menus, link, 10)
                self.assertEqual([line for line in said if "course" in line], [])


class MachineTest(unittest.TestCase):
    def test_air_rides_machine_select_joins_then_is_ok_then_starts(self) -> None:
        for port, buttons in ((0, A), (1, A), (3, START)):
            with self.subTest(port=port):
                menus, link, _ = make()
                screen(link, bot_menus.AIR_MACHINES, machine_select__port1=port)
                self.assertEqual(first_press(menus, link), {1: buttons})

    def test_the_start_that_begins_a_race_is_not_repeated_while_it_loads(self) -> None:
        menus, link, _ = make()
        screen(link, bot_menus.AIR_MACHINES, machine_select__port1=3)
        self.assertEqual(len(presses(run(menus, link, bot_menus.START_WAIT))), 1)

    def test_top_rides_machine_select_takes_a_and_start_in_turn(self) -> None:
        menus, link, said = make()
        screen(link, bot_menus.TOP_MACHINES)
        self.assertEqual([b for _, b in presses(run(menus, link, 1500))[:3]], [{1: A}, {1: START}, {1: A}])
        self.assertEqual([line for line in said if line.startswith("unconfirmed step") and "cadence" not in line], [])

    def test_city_trials_player_select_has_each_port_in_that_is_not(self) -> None:
        menus, link, _ = make(ports=4)
        screen(link, bot_menus.CITY_PLAYERS)
        self.assertEqual(first_press(menus, link), {1: A, 2: A, 3: A, 4: A})

    def test_it_starts_when_every_port_is_in_and_ok_and_not_before(self) -> None:
        menus, link, _ = make(ports=4)
        screen(link, bot_menus.CITY_PLAYERS, player_select__port1=3, player_select__port2=3,
               player_select__port3=3)
        self.assertEqual(first_press(menus, link), {4: A})
        link.set("player_select.port4", 3)
        menus, link2, _ = make(ports=4)
        link2.bytes = link.bytes
        self.assertEqual(first_press(menus, link2), {1: START})

    def test_a_port_that_is_choosing_is_waited_for(self) -> None:
        menus, link, _ = make(ports=2)
        screen(link, bot_menus.CITY_PLAYERS, player_select__port1=3, player_select__port2=1)
        self.assertEqual(presses(run(menus, link, 300)), [])

    def test_city_trials_player_select_after_its_round_is_left_for_the_menus_by_holding_b(self) -> None:
        menus, link, _ = make(ports=4, modes=(CITY_TRIAL,))
        screen(link, bot_menus.CITY_PLAYERS)
        run(menus, link, 1)
        screen(link, bot_menus.RACE)
        run(menus, link, 100, first=1)  # the round began
        screen(link, bot_menus.CITY_PLAYERS)  # and its stadium's results came back here
        steps = run(menus, link, 130, first=101)  # the hold from the first look and its settling
        held = [frame for frame, buttons in steps if buttons and buttons[1] == B]
        self.assertEqual(held, list(range(held[0], held[0] + bot_menus.BACK_HOLD)) if held else "no B")
        self.assertEqual({buttons[port] for _, buttons in steps if buttons for port in (2, 3, 4)}, {0})

    def test_ports_past_the_players_are_not_asked_about(self) -> None:
        menus, link, _ = make(ports=2)
        screen(link, bot_menus.CITY_PLAYERS, player_select__port1=3, player_select__port2=3)
        self.assertEqual(first_press(menus, link), {1: START})
        self.assertNotIn(TABLE["player_select.port3"].address, {addr for addr, _ in link.reads})


class PlayTest(unittest.TestCase):
    def test_a_race_is_the_race_bots_and_the_walker_looks_at_every_frame(self) -> None:
        menus, link, _ = make()
        screen(link, bot_menus.RACE)
        steps = run(menus, link, 601)
        self.assertTrue(all(buttons is None for _, buttons in steps))
        self.assertEqual(len(link.reads), 601)

    def test_the_screen_after_play_is_the_walkers_from_its_first_frame(self) -> None:
        # So the race bots' A can't pass City Trial's stats or the card unseen.
        menus, link, _ = make(modes=(CITY_TRIAL,))
        screen(link, bot_menus.RACE)
        steps = run(menus, link, 200, changes={137: lambda: screen(link, bot_menus.CITY_STATS)})
        self.assertTrue(all(buttons is None for _, buttons in steps[:137]))
        self.assertEqual(steps[137], (137, {1: A}))

    def test_top_rides_race_is_too(self) -> None:
        menus, link, _ = make()
        screen(link, bot_menus.TOP_RACE)
        self.assertTrue(all(buttons is None for _, buttons in run(menus, link, 200)))

    def race(self, start: int, frames: int, **kw) -> tuple[Menus, FakeLink, list[str], Steps]:
        """A race that began from the screen START, whose first look at it is at frame 50."""
        menus, link, said = make(round_seconds=10, **kw)
        screen(link, start)
        steps = run(menus, link, frames, changes={20: lambda: screen(link, bot_menus.RACE)})
        return menus, link, said, steps

    def test_a_race_is_left_through_the_pause_menu_after_the_round_as_the_routes_do(self) -> None:
        menus, _, said, steps = self.race(bot_menus.AIR_MACHINES, 900)
        found = presses(steps)[1:]  # the first is the A that joined
        s = found[0][0]
        self.assertEqual(s, 650)  # 10 s after the race began at the walker's first look, at 50
        self.assertEqual(found, [(s, {1: START}), (s + 100, {1: DOWN}), (s + 150, {1: DOWN}), (s + 200, {1: A})])
        self.assertEqual(menus.mode, AIR_RIDE)
        self.assertTrue(any(line.startswith("leaving air-ride after 10 s") for line in said))

    def test_the_pad_is_at_rest_while_the_pause_menu_is_up(self) -> None:
        _, _, _, steps = self.race(bot_menus.TOP_MACHINES, 1300)
        s = presses(steps)[1][0]
        self.assertIsNone(steps[s - 1][1])
        for frame, buttons in steps[s:s + 505]:
            self.assertIsNotNone(buttons, frame)
        self.assertIsNone(steps[s + 505][1])

    def test_the_rest_of_the_path_is_dropped_when_the_screen_changes(self) -> None:
        menus, link, _ = make(round_seconds=10)
        screen(link, bot_menus.AIR_MACHINES)
        menu = lambda: screen(link, bot_menus.MAIN_MENU, menu__page=1, menu__mode=0)  # noqa: E731
        probe = run(menus, link, 800, changes={20: lambda: screen(link, bot_menus.RACE)})
        s = presses(probe)[1][0]
        menus, link, _ = make(round_seconds=10)
        screen(link, bot_menus.AIR_MACHINES)
        steps = run(menus, link, 1000, changes={20: lambda: screen(link, bot_menus.RACE), s + 10: menu})
        later = [(frame, buttons) for frame, buttons in presses(steps) if frame > s]
        self.assertEqual([buttons for _, buttons in later], [{1: A}] * len(later))
        self.assertGreater(len(later), 3)  # Start Game, over and over, and no DOWN

    def test_the_way_out_is_tried_again_when_the_race_goes_on(self) -> None:
        _, _, _, steps = self.race(bot_menus.AIR_MACHINES, 1600)
        starts = [frame for frame, buttons in presses(steps) if buttons == {1: START}]
        self.assertEqual(len(starts), 2)
        self.assertTrue(bot_menus.RETRY <= starts[1] - starts[0] < bot_menus.RETRY + 60, starts)

    def test_a_new_round_gets_its_own_goal_and_course(self) -> None:
        menus, link, _ = make(round_seconds=10)
        screen(link, bot_menus.MAIN_MENU, menu__page=1, menu__mode=0)
        run(menus, link, 60)
        self.assertEqual((menus.rounds, menus.goal), (1, AIR_RIDE))
        menus.course = 3
        screen(link, bot_menus.AIR_MACHINES, machine_select__port1=3)
        run(menus, link, 60, first=60)
        screen(link, bot_menus.RACE)
        run(menus, link, 400, first=120)  # the race is first looked at once the START has loaded it
        self.assertEqual((menus.goal, menus.course, menus.mode), (None, None, AIR_RIDE))

    def test_city_trial_is_not_left_early(self) -> None:
        _, _, _, steps = self.race(bot_menus.CITY_PLAYERS, 3000)
        self.assertTrue(all(buttons is None for frame, buttons in steps if frame >= 60))

    def test_the_stadium_after_the_stats_and_card_is_left_from_its_pause_menu_after_the_round(self) -> None:
        for before in (bot_menus.CITY_STATS, bot_menus.STADIUM_CARD):
            with self.subTest(before=before):
                menus, link, said = make(round_seconds=10)
                screen(link, bot_menus.CITY_PLAYERS)
                run(menus, link, 1)
                screen(link, bot_menus.RACE)
                run(menus, link, 100, first=1)
                screen(link, before)
                run(menus, link, 100, first=101)
                screen(link, bot_menus.RACE)
                steps = run(menus, link, 1200, first=201)
                self.assertEqual(menus.mode, CITY_TRIAL)
                # The stadium begins at 201, when the walker's A on the screen before has settled.
                self.assertEqual(presses(steps), [(801, {1: START}), (901, {1: DOWN}), (951, {1: A})])
                self.assertEqual(len([line for line in said if line.startswith("leaving the stadium after 10 s")]), 1)
                self.assertEqual([line for line in said if line.startswith("unconfirmed step") and "cadence" not in line],
                                 [])

    def test_a_race_that_began_where_the_walker_did_not_see_is_not_left_early(self) -> None:
        menus, link, _ = make(round_seconds=10)
        screen(link, bot_menus.RACE)
        self.assertTrue(all(buttons is None for _, buttons in run(menus, link, 3000)))

    def test_no_round_length_is_no_early_leaving(self) -> None:
        menus, link, _ = make(round_seconds=None)
        screen(link, bot_menus.AIR_MACHINES)
        steps = run(menus, link, 20000, changes={20: lambda: screen(link, bot_menus.RACE)})
        self.assertTrue(all(buttons is None for frame, buttons in steps if frame >= 60))

    def test_the_round_is_timed_from_the_race_and_not_the_boot(self) -> None:
        menus, link, _ = make(round_seconds=10)
        screen(link, bot_menus.AIR_MACHINES)
        steps = run(menus, link, 700, first=5000, changes={5020: lambda: screen(link, bot_menus.RACE)})
        s = presses(steps)[1][0]
        self.assertTrue(5650 <= s < 5710, s)


class StuckTest(unittest.TestCase):
    def test_a_menu_screen_that_stays_up_is_stuck_after_the_allowed_time(self) -> None:
        menus, link, _ = make(stuck_seconds=30)
        screen(link, bot_menus.AIR_COURSES, course_select__cursor=0)
        run(menus, link, 30 * 60)
        with self.assertRaisesRegex(Stuck, r"^screen 6 \(Air Ride's course select .*\) has stayed up for 3\d s "
                                           r"of game time, which is past the 30 s allowed$"):
            run(menus, link, 200, first=30 * 60)

    def test_a_screen_the_table_does_not_name_is_stuck_too(self) -> None:
        menus, link, _ = make(stuck_seconds=10)
        screen(link, 12)
        with self.assertRaisesRegex(Stuck, r"screen 12 \(not named in kar_ram.json\)"):
            run(menus, link, 2000)

    def test_a_new_screen_starts_the_time_again(self) -> None:
        menus, link, _ = make(stuck_seconds=30)
        screen(link, bot_menus.AIR_RESULTS)
        run(menus, link, 25 * 60)
        screen(link, bot_menus.AIR_COURSES, course_select__cursor=0)
        run(menus, link, 25 * 60, first=25 * 60)

    def test_a_race_is_stuck_after_its_own_longer_time(self) -> None:
        menus, link, _ = make(stuck_seconds=30, play_seconds=100)
        screen(link, bot_menus.RACE)
        run(menus, link, 100 * 60)
        with self.assertRaisesRegex(Stuck, "past the 100 s allowed"):
            run(menus, link, 200, first=100 * 60)

    def test_the_time_is_game_time_so_a_jump_in_frame_numbers_counts(self) -> None:
        menus, link, _ = make(stuck_seconds=30)
        screen(link, bot_menus.AIR_RESULTS)
        run(menus, link, 50)
        link.frame = 30 * 60 + 5
        with self.assertRaises(Stuck):
            menus.step(link)

    def go_round(self, link: FakeLink, frames: int, first: int = 0, every: int = 200) -> dict[int, Callable[[], None]]:
        """The game changing screen every EVERY frames between two menu screens, none of them stuck."""
        screens = (bot_menus.AIR_RESULTS, bot_menus.AIR_COURSES)
        return {f: (lambda minor=screens[i % 2]: screen(link, minor, course_select__cursor=0))
                for i, f in enumerate(range(first, first + frames, every))}

    def test_menu_screens_that_take_turns_are_stuck_after_five_times_the_screen_limit(self) -> None:
        menus, link, _ = make(stuck_seconds=30)
        run(menus, link, 150 * 60, changes=self.go_round(link, 150 * 60))
        with self.assertRaisesRegex(Stuck, r"^no race or city for 15\d s of game time, which is past the 150 s "
                                           r"allowed; the screens went 11, 6, 11, 6, 11, 6, 11, 6, now 11 "):
            run(menus, link, 400, first=150 * 60, changes=self.go_round(link, 400, first=150 * 60))

    def test_no_screen_in_the_turns_was_up_for_its_own_limit(self) -> None:
        menus, link, _ = make(stuck_seconds=30)
        run(menus, link, 140 * 60, changes=self.go_round(link, 140 * 60))

    def test_a_race_starts_the_time_without_one_again(self) -> None:
        menus, link, _ = make(stuck_seconds=30)
        run(menus, link, 140 * 60, changes=self.go_round(link, 140 * 60))
        screen(link, bot_menus.RACE)
        run(menus, link, 1, first=140 * 60)
        run(menus, link, 140 * 60, first=140 * 60 + 1, changes=self.go_round(link, 140 * 60, first=140 * 60 + 1))

    def test_the_time_without_a_race_starts_over_with_a_new_connection(self) -> None:
        menus, link, _ = make(stuck_seconds=30)
        run(menus, link, 140 * 60, changes=self.go_round(link, 140 * 60))
        link.starts = 2  # and the frame numbers go on, so only the new connection says it's a new game
        run(menus, link, 140 * 60, first=140 * 60, changes=self.go_round(link, 140 * 60, first=140 * 60))
        # 280 s from the first look but 140 from the new connection's, so the cap is still ahead
        with self.assertRaisesRegex(Stuck, r"^no race or city for 15\d s of game time"):
            run(menus, link, 2000, first=280 * 60, changes=self.go_round(link, 2000, first=280 * 60))
        self.assertGreater(link.frame, 290 * 60)  # 150 s after the new connection and not before


class RestartTest(unittest.TestCase):
    def test_a_new_connection_forgets_the_press_and_the_screen(self) -> None:
        menus, link, _ = make(stuck_seconds=30)
        screen(link, bot_menus.AIR_RESULTS)
        run(menus, link, 25 * 60)
        link.starts = 2
        run(menus, link, 25 * 60, first=0)  # would be stuck at 30 s if the first 25 still counted

    def test_frames_that_start_over_are_a_new_game_too(self) -> None:
        menus, link, _ = make(stuck_seconds=30)
        screen(link, bot_menus.AIR_RESULTS)
        run(menus, link, 25 * 60, first=10000)
        run(menus, link, 25 * 60, first=0)

    def test_the_goal_and_the_count_of_rounds_stay(self) -> None:
        menus, link, _ = make(modes=(CITY_TRIAL,))
        screen(link, bot_menus.MAIN_MENU, menu__page=0, menu__mode=0)
        run(menus, link, 100)
        link.starts = 2
        run(menus, link, 100, first=0)
        self.assertEqual((menus.rounds, menus.goal), (1, CITY_TRIAL))

    def test_the_mode_being_played_is_forgotten(self) -> None:
        menus, link, _ = make()
        screen(link, bot_menus.AIR_MACHINES)
        run(menus, link, 100, changes={20: lambda: screen(link, bot_menus.RACE)})
        self.assertEqual(menus.mode, AIR_RIDE)
        link.starts = 2
        run(menus, link, 1, first=0)
        self.assertIsNone(menus.mode)


class UnconfirmedTest(unittest.TestCase):
    CASES = {
        "other screen": (12, {}),
        "press cadence": (bot_menus.MOVIES[0], {}),
    }

    def test_each_unconfirmed_step_is_said_the_first_time_it_is_taken_and_not_again(self) -> None:
        for key, (minor, named) in self.CASES.items():
            with self.subTest(key=key):
                menus, link, said = make(modes=(AIR_RIDE,))
                screen(link, minor, **named)
                run(menus, link, 1000)
                self.assertEqual([line for line in said if line.startswith(f"unconfirmed step, {key}: ")],
                                 [f"unconfirmed step, {key}: {bot_menus.UNCONFIRMED[key]}"])

    def test_the_row_is_unconfirmed_on_no_modes_menu(self) -> None:
        # Air Ride's and Top Ride's rows were read in the game as City Trial's were.
        for goal, mode in ((AIR_RIDE, 0), (TOP_RIDE, 1), (CITY_TRIAL, 2)):
            with self.subTest(goal=goal):
                menus, link, said = make(modes=(goal,))
                screen(link, bot_menus.MAIN_MENU, menu__page=1, menu__mode=mode, menu__item=1)
                run(menus, link, 1000)
                self.assertEqual([line for line in said if "menu.item" in line], [])

    def test_every_unconfirmed_step_is_tested_here(self) -> None:
        self.assertEqual(set(bot_menus.UNCONFIRMED), {*self.CASES, "split stadium pause"})

    def test_a_stadium_left_with_two_or_three_players_is_one_and_with_one_or_four_is_not(self) -> None:
        for ports, said_so in ((1, False), (2, True), (3, True), (4, False)):
            with self.subTest(ports=ports):
                menus, link, said = make(ports, modes=(CITY_TRIAL,), round_seconds=10)
                screen(link, bot_menus.CITY_PLAYERS)
                run(menus, link, 1)
                screen(link, bot_menus.RACE)
                run(menus, link, 100, first=1)
                screen(link, bot_menus.STADIUM_CARD)
                run(menus, link, 100, first=101)
                screen(link, bot_menus.RACE)
                steps = run(menus, link, 1200, first=201)
                self.assertEqual([pads[1] for _, pads in presses(steps)], [START, RIGHT if ports > 1 else DOWN, A])
                self.assertEqual(any("split stadium pause" in line for line in said), said_so)

    def test_the_press_cadence_is_said_with_the_first_press_and_not_with_a_wait(self) -> None:
        cadence = f"unconfirmed step, press cadence: {bot_menus.UNCONFIRMED['press cadence']}"
        menus, link, said = make()
        screen(link, bot_menus.AIR_MACHINES, machine_select__port1=2)  # choosing, which is waited for
        run(menus, link, 300)
        self.assertNotIn(cadence, said)
        screen(link, bot_menus.AIR_MACHINES, machine_select__port1=0)
        run(menus, link, 100, first=300)
        self.assertEqual(said.count(cadence), 1)

    def test_the_steps_the_routes_walk_say_nothing_but_the_cadence_of_the_presses(self) -> None:
        menus, link, said = make(ports=4, modes=(CITY_TRIAL,))
        menus.course = 0
        for minor, named in ((bot_menus.MAIN_MENU, {"menu__page": 0, "menu__mode": 2}), (bot_menus.MOVIES[2], {}),
                             (bot_menus.CITY_PLAYERS, {}), (bot_menus.CITY_STATS, {}),
                             (bot_menus.STADIUM_CARD, {}), (bot_menus.AIR_COURSES, {"course_select__cursor": 0}),
                             (bot_menus.AIR_MACHINES, {"machine_select__port1": 0}), (bot_menus.AIR_RESULTS, {})):
            screen(link, minor, **named)
            run(menus, link, 100, first=link.frame + 1)
        self.assertEqual(said, ["round 1: city-trial",
                                f"unconfirmed step, press cadence: {bot_menus.UNCONFIRMED['press cadence']}"])


class PathTest(unittest.TestCase):
    """The paths, played against a model of the screens the routes show."""

    def path(self, mode: str, players: int = 1, frames: int = 4000, race: int = 3000, seed: int = 0,
             stadium: int | None = None, **kw):
        game = FakeGame(FakeLink(), players=players, race=race, stadium=stadium)
        menus = Menus(players, Schedule(seed, (mode,)), **kw)
        play_through(game, menus, frames)
        return game, menus

    def test_a_blank_card_goes_to_an_air_ride_race(self) -> None:
        game, _ = self.path(AIR_RIDE, frames=3000, race=100000)
        self.assertEqual(game.visited, [38, 0, 2, 23, 6, 8, 18])
        self.assertEqual(len(game.started), 1)

    def test_it_races_the_course_the_schedule_chose(self) -> None:
        for seed in range(8):
            with self.subTest(seed=seed):
                game, _ = self.path(AIR_RIDE, frames=3000, race=100000, seed=seed)
                self.assertEqual(game.started, [("air", Schedule(seed, (AIR_RIDE,)).course())])

    def test_a_blank_card_goes_to_a_top_ride_race(self) -> None:
        game, _ = self.path(TOP_RIDE, frames=3500, race=100000)
        self.assertEqual(game.visited, [38, 0, 2, 24, 7, 9, 19])

    def test_a_blank_card_goes_to_a_city_trial_with_one_to_four_players(self) -> None:
        for players in (1, 2, 3, 4):
            with self.subTest(players=players):
                game, _ = self.path(CITY_TRIAL, players=players, frames=3000, race=100000)
                self.assertEqual(game.visited, [38, 0, 2, 25, 10, 18])
                self.assertEqual(game.started, [("city", 0)])
                self.assertEqual([game.in_game[p] for p in range(1, 5)],
                                 [3 if p <= players else 0 for p in range(1, 5)])

    def test_an_air_ride_race_is_left_for_the_modes_menu_and_the_next_round_starts_there(self) -> None:
        game, menus = self.path(AIR_RIDE, frames=12000, race=100000, round_seconds=60)
        self.assertEqual(game.visited[:10], [38, 0, 2, 23, 6, 8, 18, 2, 6, 8])  # no movie the second time
        self.assertGreaterEqual(len(game.started), 2)
        self.assertIn(menus.rounds, (len(game.started), len(game.started) + 1))

    def test_a_race_that_ends_by_itself_goes_through_the_results_to_the_course_select(self) -> None:
        game, _ = self.path(AIR_RIDE, frames=14000, race=1500)
        self.assertEqual(game.visited[:10], [38, 0, 2, 23, 6, 8, 18, 11, 6, 8])
        self.assertGreaterEqual(len(game.started), 3)

    def test_a_top_ride_race_is_left_through_the_pause_menu_too(self) -> None:
        game, _ = self.path(TOP_RIDE, frames=12000, race=100000, round_seconds=60)
        self.assertEqual(game.visited[:9], [38, 0, 2, 24, 7, 9, 19, 2, 7])

    def test_a_city_trial_goes_through_the_stats_the_card_the_stadium_and_the_results_to_the_menus(self) -> None:
        game, menus = self.path(CITY_TRIAL, frames=9000, race=2000)
        self.assertEqual(game.visited[:13], [38, 0, 2, 25, 10, 18, 16, 17, 18, 13, 34, 10, 2])
        self.assertEqual(menus.rounds, 2)

    def test_a_four_player_city_trial_comes_back_to_the_menus_and_plays_again(self) -> None:
        game, menus = self.path(CITY_TRIAL, players=4, frames=16000, race=2000)
        self.assertEqual(game.visited[:14], [38, 0, 2, 25, 10, 18, 16, 17, 18, 13, 34, 10, 2, 10])
        self.assertGreaterEqual(len(game.started), 2)
        self.assertIn(menus.rounds, (len(game.started), len(game.started) + 1))

    def test_a_stadium_that_goes_on_is_ended_from_its_pause_menu_and_the_next_round_starts(self) -> None:
        game, menus = self.path(CITY_TRIAL, frames=12000, race=2000, stadium=10 ** 9, round_seconds=30)
        self.assertEqual(game.visited[:11], [38, 0, 2, 25, 10, 18, 16, 17, 18, 2, 10])
        self.assertGreaterEqual(len(game.started), 2)

    def test_a_four_player_stadium_that_goes_on_is_ended_from_its_side_by_side_pause_menu(self) -> None:
        game, menus = self.path(CITY_TRIAL, players=4, frames=12000, race=2000, stadium=10 ** 9, round_seconds=30)
        self.assertEqual(game.visited[:11], [38, 0, 2, 25, 10, 18, 16, 17, 18, 2, 10])
        self.assertGreaterEqual(len(game.started), 2)

    def test_the_modes_take_turns(self) -> None:
        game = FakeGame(FakeLink(), race=100000)
        menus = Menus(1, Schedule(0, (AIR_RIDE, TOP_RIDE)), round_seconds=30)
        play_through(game, menus, 40000)
        modes = [mode for mode, _ in game.started]
        self.assertGreaterEqual(len(modes), 6)
        for i in range(0, len(modes) - 1, 2):
            self.assertEqual(sorted(modes[i:i + 2]), ["air", "top"])

    def test_a_console_reset_comes_back_through_the_boot_to_the_menus(self) -> None:
        link = FakeLink()
        game = FakeGame(link, race=100000)
        menus = Menus(1, Schedule(0, (AIR_RIDE,)))
        play_through(game, menus, 3000)
        self.assertEqual(game.minor, 18)
        game = FakeGame(link, race=100000)
        link.starts = 2
        play_through(game, menus, 3000)
        self.assertEqual(game.visited, [38, 0, 2, 23, 6, 8, 18])

    def test_a_modes_menu_that_opens_on_a_lower_row_is_climbed_to_start_game(self) -> None:
        for mode in (AIR_RIDE, TOP_RIDE, CITY_TRIAL):
            with self.subTest(mode=mode):
                game = FakeGame(FakeLink(), item=3, race=100000)
                play_through(game, Menus(1, Schedule(0, (mode,))), 5000)
                self.assertEqual(len(game.started), 1)
                self.assertNotIn(bot_menus.CITY_SETTINGS, game.visited)

    def test_a_row_that_never_moves_does_not_keep_the_walker_off_the_game(self) -> None:
        class Stale(FakeGame):
            """A game whose menu.item reads a row the cursor isn't on, as if the byte were stale."""

            def sync(self) -> None:
                super().sync()
                self.link.set("menu.item", 2)

        for mode in (AIR_RIDE, TOP_RIDE, CITY_TRIAL):
            with self.subTest(mode=mode):
                game = Stale(FakeLink(), race=100000)
                play_through(game, Menus(1, Schedule(0, (mode,))), 5000)
                self.assertEqual(len(game.started), 1)

    def test_menus_that_go_round_in_a_circle_end_as_stuck(self) -> None:
        class Bouncing(FakeGame):
            """A game whose Start Game opens Game Settings, so the walker's A and B go round."""

            def enter(self) -> None:
                self.go(bot_menus.CITY_SETTINGS)

        game = Bouncing(FakeLink(), race=100000)
        menus = Menus(1, Schedule(0, (CITY_TRIAL,)), stuck_seconds=30)
        with self.assertRaisesRegex(Stuck, r"^no race or city for 15\d s of game time"):
            play_through(game, menus, 12000)
        self.assertEqual(game.started, [])
        self.assertGreater(game.visited.count(bot_menus.CITY_SETTINGS), 10)

    def test_the_walker_is_never_stuck_on_any_of_the_paths(self) -> None:
        for mode, players in ((AIR_RIDE, 1), (TOP_RIDE, 1), (CITY_TRIAL, 1), (CITY_TRIAL, 4)):
            for seed in (0, 1, 2):
                with self.subTest(mode=mode, players=players, seed=seed):
                    game, _ = self.path(mode, players=players, frames=60000, race=2500, seed=seed, round_seconds=40)
                    self.assertGreaterEqual(len(game.started), 6)


if __name__ == "__main__":
    unittest.main()
