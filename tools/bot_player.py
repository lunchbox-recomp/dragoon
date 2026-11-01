"""What does the soak's bot do on each frame?

`Player` is the callback `bot_link.run` takes. The menu walker (bot_menus.py) has the pads while
a menu is up, and the race bots (bot_walk.py) have them while a race or the city plays. Every
frame it tells the watchers (bot_watch.py) what the bots sent, so the picture's window and the
game's log are looked at on the frame the run stops at. The walk's streams go on in the menus
too, so the pads in a race are a function of the seed and the frame count alone. It prints a
line of progress every few minutes. It has no command line.
"""
from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Callable, Optional

from bot_link import Link, Pad
from bot_menus import LEAVE_SECONDS, PLAY_SECONDS, Menus, Schedule
from bot_walk import Walk
from bot_watch import Frozen, LogWatch

BEAT_SECONDS = 300  # wall seconds between lines of progress


def count(n: int, noun: str) -> str:
    """N NOUNs, with the s when there is not one."""
    return f"{n} {noun}" + ("" if n == 1 else "s")


class Player:
    """Plays PORTS controllers from SEED through the MODES. ROUND_SECONDS and STUCK_SECONDS are
    the menu walker's (bot_menus.Menus), and a race may last until LEAVE_SECONDS past the round
    when that is later than PLAY_SECONDS. FROZEN and LOG are the watchers, and SAY takes the lines
    it prints, each starting with the frame it was said at. A line of progress comes every
    BEAT_SECONDS of CLOCK's time, None for never."""

    def __init__(self, seed: int, ports: int, modes: Sequence[str], *, round_seconds: Optional[float],
                 stuck_seconds: float, frozen: Frozen, log: LogWatch, say: Callable[[str], None],
                 beat_seconds: Optional[float] = BEAT_SECONDS, clock: Callable[[], float] = time.monotonic) -> None:
        # A race may last its round and the time to leave it, or the usual limit when that is more.
        play_seconds = PLAY_SECONDS if round_seconds is None else max(PLAY_SECONDS, round_seconds + LEAVE_SECONDS)
        self.menus = Menus(ports, Schedule(seed, modes), round_seconds=round_seconds, stuck_seconds=stuck_seconds,
                           play_seconds=play_seconds, say=self._said)
        self.walk = Walk(seed, ports)
        self.frozen = frozen
        self.log = log
        self.racing = False  # whether the race bots had the pads on the last frame
        self._say = say
        self._beat_seconds = beat_seconds
        self._clock = clock
        self._began: Optional[float] = None
        self._beat_at = 0.0
        self._frame = 0

    def __call__(self, link: Link) -> dict[int, Pad]:
        """The pads for LINK's frame. Raises Stuck when a menu screen stays up too long, and
        Detected when a watcher sees a fault."""
        self._frame = link.frame
        walk = self.walk.pads()
        menu = self.menus.step(link)
        self.racing = menu is None
        pads = walk if menu is None else menu
        self.frozen.look(link, pads, self.racing)
        self.log.look(link.frame)
        self._beat()
        return pads

    def _said(self, text: str) -> None:
        self._say(f"frame {self._frame}: {text}")

    def _beat(self) -> None:
        if self._beat_seconds is None:
            return
        now = self._clock()
        if self._began is None:
            self._began, self._beat_at = now, now + self._beat_seconds
        elif now >= self._beat_at:
            self._beat_at = now + self._beat_seconds
            self._said(f"{(now - self._began) / 60:.0f} min in, {count(self.menus.rounds, 'round')}, "
                       f"{count(self.log.resets.count, 'console reset')}")
