"""A stand-in for the game's menus, for the bot tools' tests."""
from __future__ import annotations

from collections.abc import Callable

import bot_menus
from bot_link import BUTTONS, Pad
from bot_menus import Menus
from testutil import FakeLink


class FakeGame:
    """The screens the routes pass through, and what a press does on each, as the routes and
    kar_ram.json show them. It is a model of those, which lets the walker's paths be played end
    to end with no game. A press counts when the button goes down. A race and the city end after
    `race` frames of play, not counting a pause, and a stadium after `stadium`, `race` by
    default. It keeps the screen's values in LINK.

    A mode's own menu has four rows. Its cursor is on row `item` when the menu first opens, and
    stays where the player left it after that, as city-trial-stadium.txt shows: B out of Game
    Settings (row 3 of City Trial's) leaves it there.

    A stadium's results wait for START from every player, as a four-player soak's Destruction
    Derby did, and then go back to City Trial's player entry with every port out, through the
    checklist the first time, as a soak showed. B held there for BACK_HELD frames goes back to
    City Trial's own menu, as a hold from city-trial.txt's player entry did. The city can't be
    paused here. A stadium's pause menu has two rows, Return to Game and End Game, and DOWN
    wraps, as Drag Race 3's did. Its End Game goes to City Trial's own menu."""

    BACK_HELD = 47  # frames of B the game took to leave the player entry

    def __init__(self, link: FakeLink, players: int = 1, race: int = 3000, item: int = 0,
                 stadium: int | None = None) -> None:
        self.link, self.players, self.race_length = link, players, race
        self.stadium_length = race if stadium is None else stadium
        self.opening_item = item
        self.item = 0
        self.minor, self.page, self.mode, self.cursor = bot_menus.BOOT, 0, 0, 0
        self.boot_presses = 0
        self.machine = 0
        self.joined = False
        self.in_game = {1: 0, 2: 0, 3: 0, 4: 0}
        self.raced = 0
        self.paused = False
        self.pause_row = 0
        self.stage = 0  # City Trial: 0 the city, 1 the stadium
        self.checked = False  # whether the checklist has shown
        self.held_b = 0  # frames port 1 has held B
        self.ready: set[int] = set()  # players who have pressed START on a stadium's results
        self.movies_seen: set[int] = set()
        self.visited: list[int] = [self.minor]
        self.started: list[tuple[str, int]] = []  # (mode, course) of each race that began
        self.last: dict[int, int] = {}
        self.sync()

    def sync(self) -> None:
        link = self.link
        link.set("scene.minor", self.minor)
        link.set("menu.page", self.page)
        link.set("menu.mode", self.mode)
        link.set("menu.item", self.item)
        link.set("course_select.cursor", self.cursor)
        link.set("machine_select.port1", self.machine)
        for port, state in self.in_game.items():
            link.set(f"player_select.port{port}", state)

    def go(self, minor: int) -> None:
        self.minor = minor
        self.visited.append(minor)
        self.raced = 0
        self.paused = False
        self.ready = set()

    def enter(self) -> None:
        """The mode's first screen after its menu, or after its movie."""
        self.go((bot_menus.AIR_COURSES, bot_menus.TOP_COURSES, bot_menus.CITY_PLAYERS)[self.mode])
        self.machine = 0
        self.in_game = {1: 0, 2: 0, 3: 0, 4: 0}

    def advance(self, pads: dict[int, Pad] | None) -> None:
        """One frame of the game with PADS pressed, or nothing pressed for None."""
        now = {port: pads[port].buttons if pads and port in pads else 0 for port in range(1, 5)}
        down = {port: now[port] & ~self.last.get(port, 0) for port in now}
        self.last = now
        self.held_b = self.held_b + 1 if now[1] & BUTTONS["B"] else 0

        def pressed(button: str, port: int = 1) -> bool:
            return bool(down[port] & BUTTONS[button])

        m = self.minor
        if m == bot_menus.BOOT:
            self.boot_presses += pressed("A")
            if self.boot_presses >= 2:
                self.go(bot_menus.TITLE)
        elif m == bot_menus.TITLE:
            if pressed("START"):
                self.go(bot_menus.MAIN_MENU)
                self.page = self.mode = 0
        elif m == bot_menus.MAIN_MENU:
            if self.page == 0:
                if pressed("DOWN"):
                    self.mode = min(4, self.mode + 1)
                if pressed("UP"):
                    self.mode = max(0, self.mode - 1)
                if pressed("A") and self.mode <= 2:
                    self.page, self.item = 1, self.opening_item
            elif pressed("B"):
                self.page = 0
            else:
                if pressed("DOWN"):
                    self.item = min(3, self.item + 1)
                if pressed("UP"):
                    self.item = max(0, self.item - 1)
                if pressed("A") and self.item == 3 and self.mode == 2:  # City Trial's Game Settings
                    self.go(bot_menus.CITY_SETTINGS)
                elif pressed("A") and self.item == 0:
                    if self.mode in self.movies_seen:
                        self.enter()
                    else:
                        self.movies_seen.add(self.mode)
                        self.go(bot_menus.MOVIES[self.mode])
        elif m == bot_menus.CITY_SETTINGS:
            if pressed("B"):
                self.go(bot_menus.MAIN_MENU)  # with the cursor where it was, on page 1
        elif m in bot_menus.MOVIES:
            if pressed("A"):
                self.enter()
        elif m == bot_menus.AIR_COURSES:
            row, col = divmod(self.cursor, 5)
            col = min(4, col + 1) if pressed("RIGHT") else max(0, col - 1) if pressed("LEFT") else col
            row = 1 if pressed("DOWN") else 0 if pressed("UP") else row
            self.cursor = row * 5 + col
            if pressed("A"):
                self.go(bot_menus.AIR_MACHINES)
                self.machine = 0
        elif m == bot_menus.AIR_MACHINES:
            if pressed("A") and self.machine < 3:
                self.machine = 1 if self.machine == 0 else 3
            elif pressed("START") and self.machine == 3:
                self.started.append(("air", self.cursor))
                self.go(bot_menus.RACE)
        elif m == bot_menus.TOP_COURSES:
            if pressed("A"):
                self.go(bot_menus.TOP_MACHINES)
                self.joined = False
        elif m == bot_menus.TOP_MACHINES:
            if pressed("A"):
                self.joined = True
            elif pressed("START") and self.joined:
                self.started.append(("top", 0))
                self.go(bot_menus.TOP_RACE)
        elif m == bot_menus.CITY_PLAYERS and self.held_b >= self.BACK_HELD:
            self.go(bot_menus.MAIN_MENU)  # City Trial's own menu, the cursor where it was
            self.page = 1
        elif m == bot_menus.CITY_PLAYERS:
            for port in range(1, 5):
                if pressed("A", port):
                    self.in_game[port] = 3  # in and OK at once, as city-trial-4p.txt shows
            if pressed("START") and all(self.in_game[p] == 3 for p in range(1, self.players + 1)):
                self.started.append(("city", 0))
                self.stage = 0
                self.go(bot_menus.RACE)
        elif m in bot_menus.PLAYING:
            self.play(pressed)
        elif m == bot_menus.AIR_RESULTS:
            if pressed("START"):
                self.go(bot_menus.AIR_COURSES)
        elif m == bot_menus.CITY_STATS:
            if pressed("A"):
                self.go(bot_menus.STADIUM_CARD)
        elif m == bot_menus.STADIUM_CARD:
            if pressed("A"):
                self.stage = 1
                self.go(bot_menus.RACE)
        elif m == bot_menus.STADIUM_RESULTS:
            self.ready |= {port for port in range(1, self.players + 1) if pressed("START", port)}
            if len(self.ready) == self.players and not self.checked:
                self.checked = True
                self.go(bot_menus.CHECKLIST)
            elif len(self.ready) == self.players:
                self.enter()
        elif m == bot_menus.CHECKLIST:
            if pressed("A"):
                self.enter()
        self.sync()

    def play(self, pressed: Callable[[str], bool]) -> None:
        in_city = self.started[-1][0] == "city"
        stadium = in_city and self.stage == 1
        if self.paused:
            if pressed("DOWN"):  # a stadium's two rows wrap, as Drag Race 3's did
                self.pause_row = (self.pause_row + 1) % 2 if stadium else min(2, self.pause_row + 1)
            if pressed("A"):
                if self.pause_row == (1 if stadium else 2):  # End Game: back to the mode's own menu
                    self.go(bot_menus.MAIN_MENU)
                    self.page = 1
                else:
                    self.paused = False
            return
        if pressed("START") and (stadium or not in_city):
            self.paused, self.pause_row = True, 0
            return
        self.raced += 1
        if self.raced < (self.stadium_length if stadium else self.race_length):
            return
        if in_city:
            self.go(bot_menus.CITY_STATS if self.stage == 0 else bot_menus.STADIUM_RESULTS)
        elif self.minor == bot_menus.RACE:
            self.go(bot_menus.AIR_RESULTS)
        else:
            self.go(bot_menus.MAIN_MENU)
            self.page = 1


def play_through(game: FakeGame, menus: Menus, frames: int) -> None:
    """Step MENUS against GAME for FRAMES frames, the race bots pressing nothing."""
    for frame in range(frames):
        game.link.frame = frame
        game.advance(menus.step(game.link))
