from __future__ import annotations

import unittest
from typing import Optional

import bot_menus
from bot_link import Pad
from bot_menus import AIR_RIDE, CITY_TRIAL, Stuck
from bot_player import Player, count
from bot_walk import Walk
from bot_watch import Detected
from testgame import FakeGame
from testutil import FakeLink


class FrozenStub:
    """Stands in for Frozen, and keeps what it was told."""

    def __init__(self, raises_at: Optional[int] = None) -> None:
        self.looks: list[tuple] = []
        self.raises_at = raises_at

    def look(self, link: FakeLink, pads: dict, racing: bool) -> None:
        self.looks.append((link.frame, pads, racing))
        if link.frame == self.raises_at:
            raise Detected("frozen_picture", "stand-in", link.frame)


class LogStub:
    """Stands in for LogWatch."""

    def __init__(self) -> None:
        self.looks: list[int] = []
        self.resets = type("Resets", (), {"count": 0})()

    def look(self, frame: int) -> None:
        self.looks.append(frame)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make(ports: int = 1, modes=(AIR_RIDE,), seed: int = 4, frozen: Optional[FrozenStub] = None, **kw):
    frozen, log, said = frozen or FrozenStub(), LogStub(), []
    kw.setdefault("round_seconds", None)
    kw.setdefault("stuck_seconds", 120)
    kw.setdefault("beat_seconds", None)
    return Player(seed, ports, modes, frozen=frozen, log=log, say=said.append, **kw), frozen, log, said


def play(player: Player, game: FakeGame, frames: int) -> list[tuple[int, dict[int, Pad], bool, int]]:
    """The (frame, pads, racing, screen) of each of FRAMES frames the player plays GAME."""
    out = []
    for frame in range(frames):
        game.link.frame = frame
        pads = player(game.link)
        out.append((frame, pads, player.racing, game.minor))
        game.advance(pads)
    return out


class PlayerTest(unittest.TestCase):
    def test_a_race_frame_has_the_walks_pads_and_the_walk_goes_on_in_the_menus(self) -> None:
        player, _, _, _ = make()
        steps = play(player, FakeGame(FakeLink(), race=100000), 2600)
        walk = Walk(4, 1)
        expected = [walk.pads() for _ in range(2600)]
        racing = [(frame, pads) for frame, pads, was, _ in steps if was]
        self.assertGreater(len(racing), 500)
        for frame, pads in racing:
            self.assertEqual(pads, expected[frame], frame)

    def test_the_first_frames_are_the_menus_not_the_walk(self) -> None:
        player, _, _, _ = make()
        steps = play(player, FakeGame(FakeLink(), race=100000), 10)
        self.assertEqual(steps[0][1], {1: Pad(buttons=0x0100)})  # the boot's A
        self.assertFalse(any(racing for _, _, racing, _ in steps))

    def test_the_race_bots_only_play_once_a_race_has_started(self) -> None:
        player, _, _, _ = make()
        steps = play(player, FakeGame(FakeLink(), race=100000), 2600)
        first_race = next(i for i, step in enumerate(steps) if step[3] == bot_menus.RACE)
        first_racing = next(i for i, step in enumerate(steps) if step[2])
        self.assertLessEqual(first_race, first_racing)

    def test_the_watchers_are_told_each_frames_pads_and_whether_the_race_bots_made_them(self) -> None:
        player, frozen, log, _ = make()
        steps = play(player, FakeGame(FakeLink(), race=100000), 2600)
        self.assertEqual(frozen.looks, [(frame, pads, racing) for frame, pads, racing, _ in steps])
        self.assertEqual(log.looks, list(range(2600)))

    def test_every_port_gets_a_pad_in_the_menus_and_in_the_race(self) -> None:
        player, _, _, _ = make(ports=4, modes=(CITY_TRIAL,))
        steps = play(player, FakeGame(FakeLink(), players=4, race=100000), 3000)
        self.assertTrue(any(racing for _, _, racing, _ in steps))
        for _, pads, _, _ in steps:
            self.assertEqual(sorted(pads), [1, 2, 3, 4])

    def test_the_same_seed_plays_the_same_game_and_another_plays_another(self) -> None:
        def game_of(seed: int):
            player, _, _, _ = make(seed=seed, ports=2, modes=(AIR_RIDE, CITY_TRIAL), round_seconds=20)
            return play(player, FakeGame(FakeLink(), players=2, race=600), 6000)
        self.assertEqual(game_of(3), game_of(3))
        self.assertNotEqual(game_of(3), game_of(4))

    def test_a_menu_screen_that_stays_up_is_stuck(self) -> None:
        player, _, _, _ = make(stuck_seconds=5)
        link = FakeLink()
        link.set("scene.minor", 12)
        with self.assertRaises(Stuck):
            for frame in range(1000):
                link.frame = frame
                player(link)

    def race_that_never_ends(self, player: Player, seconds: int) -> int:
        """Play a link left on a race for SECONDS of game time, and the frame it was stuck at."""
        link = FakeLink()
        link.set("scene.minor", bot_menus.RACE)
        for frame in range(seconds * 60):
            link.frame = frame
            player(link)
        return link.frame

    def test_a_race_that_never_leaves_is_stuck_a_minute_after_a_round_longer_than_the_race_limit(self) -> None:
        player, _, _, _ = make(round_seconds=700)
        with self.assertRaisesRegex(Stuck, r"past the 760 s allowed$") as caught:
            self.race_that_never_ends(player, 800)
        self.assertRegex(str(caught.exception), r"has stayed up for 76\d s")

    def test_a_race_in_a_round_longer_than_the_race_limit_is_not_stuck_before_the_round_is_up(self) -> None:
        player, _, _, _ = make(round_seconds=700)
        self.assertEqual(self.race_that_never_ends(player, 759), 759 * 60 - 1)

    def test_the_race_limit_follows_the_round_only_past_the_point_where_a_minute_more_is_over_it(self) -> None:
        for round_seconds, allowed in ((None, 600), (120, 600), (540, 600), (541, 601), (3600, 3660)):
            with self.subTest(round_seconds=round_seconds):
                player, _, _, _ = make(round_seconds=round_seconds)
                with self.assertRaisesRegex(Stuck, rf"past the {allowed} s allowed$"):
                    self.race_that_never_ends(player, allowed + 30)

    def test_a_watcher_that_raises_ends_the_frame(self) -> None:
        player, _, _, _ = make(frozen=FrozenStub(raises_at=7))
        link = FakeLink()
        with self.assertRaises(Detected) as caught:
            for frame in range(100):
                link.frame = frame
                player(link)
        self.assertEqual(caught.exception.frame, 7)

    def test_what_the_walker_says_starts_with_the_frame_it_was_said_at(self) -> None:
        player, _, _, said = make(modes=(CITY_TRIAL,))
        play(player, FakeGame(FakeLink(), race=100000), 1000)
        self.assertEqual([line for line in said if "round" in line], ["frame 300: round 1: city-trial"])

    def test_a_line_of_progress_comes_every_beat(self) -> None:
        clock = Clock()
        player, _, log, said = make(beat_seconds=60, clock=clock)
        log.resets.count = 2
        link = FakeLink()
        for frame in range(10):
            link.frame = frame
            player(link)
            clock.now += 31
        beats = [line for line in said if "min in" in line]
        self.assertEqual(len(beats), 4)
        self.assertEqual(beats[0], "frame 2: 1 min in, 0 rounds, 2 console resets")

    def test_a_count_has_its_s_unless_it_is_one(self) -> None:
        self.assertEqual([count(n, "round") for n in (0, 1, 2)], ["0 rounds", "1 round", "2 rounds"])

    def test_no_beat_seconds_means_no_progress_lines(self) -> None:
        clock = Clock()
        player, _, _, said = make(beat_seconds=None, clock=clock)
        link = FakeLink()
        for frame in range(10):
            link.frame = frame
            player(link)
            clock.now += 1000
        self.assertFalse([line for line in said if "min in" in line])


if __name__ == "__main__":
    unittest.main()
