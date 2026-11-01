"""How do the bots get from the boot to a race and back to the menus?

`Menus` reads which screen is up (`scene.minor` in kar_ram.json) and where its cursor is, and
presses a button the way libmelee's menu helper does: down for a few frames, then up while the
screen answers. A menu value keeps its last value off its own screen, so the screen is read
first and a cursor only on the screen that owns it. `step` gives the pads for a menu frame, or
None while a race or the city plays, which is the race bots' turn (bot_walk.py).

The paths come from tests/routes/ and the values kar_ram.json confirms. A step no route or
read confirms is in UNCONFIRMED, and the first time the walker takes one it says so, for the
game run that checks it. It has no command line.
"""
from __future__ import annotations

import random
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import kar_ram
from bot_link import BUTTONS, Link, Pad

# The screens, as scene.minor numbers them.
BOOT = 38
TITLE = 0
MAIN_MENU = 2
CITY_SETTINGS = 5
AIR_COURSES = 6
TOP_COURSES = 7
AIR_MACHINES = 8
TOP_MACHINES = 9
CITY_PLAYERS = 10
AIR_RESULTS = 11
STADIUM_RESULTS = 13
CITY_STATS = 16
STADIUM_CARD = 17
RACE = 18  # an Air Ride race, the city or a stadium
TOP_RACE = 19
MOVIES = (23, 24, 25)
PLAYING = (RACE, TOP_RACE)

AIR_RIDE = "air-ride"
TOP_RIDE = "top-ride"
CITY_TRIAL = "city-trial"
MODE_CURSOR = {AIR_RIDE: 0, TOP_RIDE: 1, CITY_TRIAL: 2}  # menu.mode on the mode select
# The screen a race starts from says the mode being played.
STARTS = {AIR_MACHINES: AIR_RIDE, TOP_MACHINES: TOP_RIDE, CITY_PLAYERS: CITY_TRIAL}
# Air Ride's course select is a grid of five columns. Its cursor is row * 5 + column, and the
# slots with a course on a blank memory card are these.
COLUMNS = 5
COURSES = (0, 1, 2, 3, 4, 5, 6, 7)
CONFIRMED_COURSES = (0, 1, 2, 6)  # the cursor values read in the game

FPS = 60
HOLD = 5  # frames a button is down, as the routes press
SETTLE = 45  # frames a screen gets to answer a press; the routes space cursor presses 40 to 50
SLOW = 95  # the wait after a press that changes the screen, such as the title's
START_WAIT = 300  # and after the START that begins a race, which loads before its first frame
PLAY_CHECK = 60  # frames between looks at the screen while a race plays
RETRY = 600  # frames a try at leaving a race gets before the walker tries again
ROUND_SECONDS = 120  # game seconds a race lasts before the walker leaves it
STUCK_SECONDS = 120  # game seconds a menu screen may stay up
PLAY_SECONDS = 600  # and a race, the city or a stadium
CYCLE_STUCKS = 5  # and the menus together may go on without a race or the city, this many screen limits
TRAIL = 8  # screens a stop for that names, the ones before the screen it stopped on

UNCONFIRMED = {
    "boot": "A while the game boots (minor 38). The routes press A at frames 120 and 300 only.",
    "title": "A and START in turn on the opening movie and the title (minor 0). The routes press A "
             "at 900 and START at 1000.",
    "back to the mode select": "B on a mode's own menu, to change mode. No route presses it.",
    "course cursor": "Air Ride course cursors 3, 4, 5 and 7 (Frozen Hillside, Magma Flows, Beanstalk "
                     "Park and Checker Knights). They follow the routes' grid, and only 0, 1, 2 and 6 "
                     "have been read in the game.",
    "Top Ride machines": "A and START in turn on Top Ride's machine select (minor 9), which has no "
                         "RAM slot to read.",
    "stadium results": "START on a stadium's results (minor 13). The screen after it was never watched.",
    "other screen": "A on a screen scene.minor has no name for here.",
}

LEAVE = (  # the pause menu to End Game, as the courses routes press it
    ("START", SLOW), ("DOWN", SETTLE), ("DOWN", SETTLE), ("A", START_WAIT),
)


class Stuck(Exception):
    """A screen stayed up for longer than the walker allows."""


@dataclass(frozen=True)
class Tap:
    """A press: BUTTONS bits on PORTS for HOLD frames, then SETTLE frames up. Buttons of 0 is a
    wait."""
    buttons: int
    ports: tuple[int, ...] = (1,)
    hold: int = HOLD
    settle: int = SETTLE


class Schedule:
    """What the rounds play, from SEED: the next mode, which comes round MODES in a shuffled
    order each time through, and the Air Ride course to race."""

    def __init__(self, seed: int, modes: Sequence[str]) -> None:
        if not modes or any(mode not in MODE_CURSOR for mode in modes):
            raise ValueError(f"modes are some of {', '.join(MODE_CURSOR)}")
        if seed < 0:
            raise ValueError("a seed is a whole number from 0")
        self._rng = random.Random(seed * 5)  # and 5n + 1 to 5n + 4 are the ports' walks
        self._modes = list(modes)
        self._due: list[str] = []

    def mode(self) -> str:
        if not self._due:
            self._due = list(self._modes)
            for i in range(len(self._due) - 1, 0, -1):
                j = int(self._rng.random() * (i + 1))
                self._due[i], self._due[j] = self._due[j], self._due[i]
        return self._due.pop()

    def course(self) -> int:
        return COURSES[int(self._rng.random() * len(COURSES))]


class Menus:
    """Walks the menus for PORTS controllers, playing the rounds SCHEDULE says, and says what
    it's doing to SAY. A race is left after ROUND_SECONDS of game time through the pause menu,
    or never when `round_seconds` is None. Raises Stuck from `step` when a screen stays up for
    STUCK_SECONDS, a race for PLAY_SECONDS, or the menus go on for CYCLE_STUCKS times
    STUCK_SECONDS with no race or city, as when the screens take turns. TABLE is the kar_ram
    table to read by."""

    def __init__(self, ports: int, schedule: Schedule, *, round_seconds: float | None = ROUND_SECONDS,
                 stuck_seconds: float = STUCK_SECONDS, play_seconds: float = PLAY_SECONDS,
                 say: Callable[[str], None] | None = None,
                 table: Mapping[str, kar_ram.Entry] | None = None) -> None:
        if not 1 <= ports <= 4:
            raise ValueError("ports are 1 to 4")
        self.ports = ports
        self.schedule = schedule
        self.round_frames = None if round_seconds is None else round(round_seconds * FPS)
        self.stuck_frames = round(stuck_seconds * FPS)
        self.play_frames = round(play_seconds * FPS)
        self.cycle_frames = CYCLE_STUCKS * self.stuck_frames
        self.say = say or (lambda text: None)
        self.table = dict(table) if table is not None else kar_ram.load()
        self.minor: int | None = None  # the screen at the last look
        self.mode: str | None = None  # the mode being played, once a race has started
        self.goal: str | None = None  # the mode the main menu is heading for
        self.course: int | None = None  # the Air Ride course the next race is on
        self.rounds = 0
        self._told: set[str] = set()
        self._screens: dict[int, Callable[[Link], Tap]] = {
            BOOT: self._boot, TITLE: self._title, MAIN_MENU: self._main_menu,
            CITY_SETTINGS: self._back, AIR_COURSES: self._air_courses, TOP_COURSES: self._press_a,
            AIR_MACHINES: self._air_machines, TOP_MACHINES: self._top_machines,
            CITY_PLAYERS: self._city_players, AIR_RESULTS: self._press_start,
            STADIUM_RESULTS: self._stadium_results, CITY_STATS: self._press_a, STADIUM_CARD: self._press_a,
            **{movie: self._movie for movie in MOVIES},
        }
        self._restart(0, 0)

    def _restart(self, frame: int, starts: int) -> None:
        """Forget the press under way and the screen, as after the game boots again."""
        self._starts = starts
        self._frame = frame
        self._tap: Tap | None = None
        self._held = 0  # frames of the press left
        self._wake = 0  # the frame the next look may be at
        self._look = 0  # and while a race plays, the next look
        self._script: deque[Tap] = deque()
        self._left: int | None = None  # the frame the last try at leaving began
        self._since = frame  # the frame the screen last changed
        self._began = frame  # the frame the race began
        self._visits = 0  # looks at this screen
        self._played: int | None = None  # the frame a race or the city was last on, or the first look
        self._trail: deque[int] = deque(maxlen=TRAIL)  # the screens before this one
        self.minor = None
        self.mode = None

    def step(self, link: Link) -> dict[int, Pad] | None:
        """The pads for this frame, or None when a race is on and nothing of the menus' is due."""
        frame = link.frame
        starts = getattr(link, "starts", 0)
        if starts != self._starts or frame < self._frame:
            self._restart(frame, starts)
        self._frame = frame
        if self._held:
            self._held -= 1
            return self._pads(self._tap)
        if frame < self._wake:
            return self._pads(None)
        if frame < self._look:
            return None
        tap = self._decide(link, frame)
        if tap is None:
            self._look = frame + PLAY_CHECK
            return None
        self._tap, self._held = tap, tap.hold - 1
        self._wake = frame + tap.hold + tap.settle
        return self._pads(tap)

    def _pads(self, tap: Tap | None) -> dict[int, Pad]:
        return {port: Pad(buttons=tap.buttons if tap is not None and port in tap.ports else 0)
                for port in range(1, self.ports + 1)}

    def _read(self, link: Link, name: str) -> int:
        value = kar_ram.read(link, name, self.table)
        assert isinstance(value, int), (name, value)
        return value

    def _decide(self, link: Link, frame: int) -> Tap | None:
        minor = self._read(link, "scene.minor")
        self._track(minor, frame)
        if minor in PLAYING:
            return self._play(frame)
        return self._screens.get(minor, self._other)(link)

    def _track(self, minor: int, frame: int) -> None:
        if minor != self.minor:
            if minor in PLAYING and self.minor not in PLAYING:
                self._began = frame
                if self.minor in STARTS:  # a round begins, and the next gets its own mode and course
                    self.mode = STARTS[self.minor]
                    self.goal = self.course = None
            if minor not in PLAYING:
                self._script.clear()
                self._left = None
            if self.minor is not None:
                self._trail.append(self.minor)
            self.minor, self._since, self._visits = minor, frame, 0
        else:
            self._visits += 1
        if minor in PLAYING or self._played is None:
            self._played = frame
        limit = self.play_frames if minor in PLAYING else self.stuck_frames
        if frame - self._since > limit:
            raise Stuck(f"screen {minor} ({self._name(minor)}) has stayed up for {(frame - self._since) / FPS:.0f} s "
                        f"of game time, which is past the {limit / FPS:.0f} s allowed")
        if frame - self._played > self.cycle_frames:
            raise Stuck(f"no race or city for {(frame - self._played) / FPS:.0f} s of game time, which is past the "
                        f"{self.cycle_frames / FPS:.0f} s allowed; the screens went "
                        f"{', '.join(map(str, self._trail))}, now {minor} ({self._name(minor)})")

    def _name(self, minor: int) -> str:
        return self.table["scene.minor"].meaning(minor) or "not named in kar_ram.json"

    def _unconfirmed(self, key: str) -> None:
        if key not in self._told:
            self._told.add(key)
            self.say(f"unconfirmed step, {key}: {UNCONFIRMED[key]}")

    def _play(self, frame: int) -> Tap | None:
        """A race, the city or a stadium is on. The walker presses only to leave one that's
        run its round, from the pause menu."""
        if self._script:
            return self._script.popleft()
        if (self.round_frames is not None and self.mode in (AIR_RIDE, TOP_RIDE)
                and frame - self._began >= self.round_frames
                and (self._left is None or frame - self._left >= RETRY)):
            self._left = frame
            self.say(f"leaving {self.mode} after {(frame - self._began) / FPS:.0f} s of game time")
            self._script.extend(Tap(BUTTONS[name], settle=wait) for name, wait in LEAVE)
            return self._script.popleft()
        return None

    def _goal(self) -> str:
        if self.goal is None:
            self.goal = self.schedule.mode()
            self.rounds += 1
            self.say(f"round {self.rounds}: {self.goal}")
        return self.goal

    def _all(self, button: str, settle: int = SETTLE) -> Tap:
        return Tap(BUTTONS[button], tuple(range(1, self.ports + 1)), settle=settle)

    def _boot(self, link: Link) -> Tap:
        self._unconfirmed("boot")
        return Tap(BUTTONS["A"])

    def _title(self, link: Link) -> Tap:
        self._unconfirmed("title")
        return Tap(BUTTONS["A" if self._visits % 2 == 0 else "START"], settle=SLOW)

    def _movie(self, link: Link) -> Tap:
        return self._all("A")

    def _press_a(self, link: Link) -> Tap:
        return Tap(BUTTONS["A"])

    def _press_start(self, link: Link) -> Tap:
        return Tap(BUTTONS["START"])

    def _back(self, link: Link) -> Tap:
        return Tap(BUTTONS["B"])

    def _stadium_results(self, link: Link) -> Tap:
        self._unconfirmed("stadium results")
        return Tap(BUTTONS["START"])

    def _other(self, link: Link) -> Tap:
        self._unconfirmed("other screen")
        minor = self.minor
        if f"screen {minor}" not in self._told:
            self._told.add(f"screen {minor}")
            self.say(f"screen {minor} isn't in kar_ram.json; pressing A")
        return Tap(BUTTONS["A"])

    def _main_menu(self, link: Link) -> Tap:
        want = MODE_CURSOR[self._goal()]
        mode = self._read(link, "menu.mode")
        if self._read(link, "menu.page") == 1:  # a mode's own menu, where Start Game is row 0
            if mode != want:
                self._unconfirmed("back to the mode select")
                return Tap(BUTTONS["B"])
            # The cursor stays where the player left it, as after B out of Game Settings.
            return Tap(BUTTONS["A" if self._read(link, "menu.item") == 0 else "UP"])
        if mode == want:
            return Tap(BUTTONS["A"])
        return Tap(BUTTONS["DOWN" if mode < want else "UP"])

    def _air_courses(self, link: Link) -> Tap:
        if self.course is None:
            self.course = self.schedule.course()
        if self.course not in CONFIRMED_COURSES:
            self._unconfirmed("course cursor")
        row, col = divmod(self._read(link, "course_select.cursor"), COLUMNS)
        want_row, want_col = divmod(self.course, COLUMNS)
        if col != want_col:
            return Tap(BUTTONS["RIGHT" if col < want_col else "LEFT"])
        if row != want_row:
            return Tap(BUTTONS["DOWN" if row < want_row else "UP"])
        return Tap(BUTTONS["A"])

    def _air_machines(self, link: Link) -> Tap:
        port = self._read(link, "machine_select.port1")
        if port == 3:  # OK
            return Tap(BUTTONS["START"], settle=START_WAIT)
        return Tap(BUTTONS["A"] if port in (0, 1) else 0)

    def _top_machines(self, link: Link) -> Tap:
        self._unconfirmed("Top Ride machines")
        if self._visits % 2 == 0:
            return Tap(BUTTONS["A"])
        return Tap(BUTTONS["START"], settle=START_WAIT)

    def _city_players(self, link: Link) -> Tap:
        states = {port: self._read(link, f"player_select.port{port}") for port in range(1, self.ports + 1)}
        out = tuple(port for port, state in states.items() if state == 0)
        if out:
            return Tap(BUTTONS["A"], out)
        if all(state == 3 for state in states.values()):  # all in and OK
            return Tap(BUTTONS["START"], settle=START_WAIT)
        return Tap(0)
