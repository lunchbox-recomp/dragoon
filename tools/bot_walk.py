"""Where do the bots steer in a race or the city? Wherever a seeded walk says.

A `Walk` gives each port its own stream of numbers from the seed. A port holds the stick toward
a heading for half a second to two seconds, picks another and goes on, and taps A now and then.
It never presses START and never reads RAM, so two walks of one seed give the same pads
whatever the game does. It has no command line.
"""
from __future__ import annotations

import math
import random

from bot_link import BUTTONS, Pad

HEADING_FRAMES = (30, 120)  # a heading is held for this many frames, least and most
TAP_CHANCE = 1 / 45  # the chance each frame a port that's resting starts a tap of A
TAP_FRAMES = 4  # a tap holds A for this many frames
REST_FRAMES = 8  # and A stays up for at least this many after it
STICK_CENTER = 128
STICK_REACH = 127


class _Port:
    """One port's walk: the heading it holds and where its A tap is."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.left = 0  # frames the heading has left
        self.sx = self.sy = STICK_CENTER
        self.tap = 0  # frames of the tap left
        self.rest = 0  # frames before the next tap may start

    def _turn(self) -> None:
        low, high = HEADING_FRAMES
        self.left = low + int(self.rng.random() * (high - low + 1))
        angle = self.rng.random() * 2 * math.pi
        strength = 0.5 + 0.5 * self.rng.random()
        self.sx = STICK_CENTER + round(STICK_REACH * strength * math.cos(angle))
        self.sy = STICK_CENTER + round(STICK_REACH * strength * math.sin(angle))

    def pad(self) -> Pad:
        if self.left == 0:
            self._turn()
        self.left -= 1
        if self.tap:
            self.tap -= 1
            if not self.tap:
                self.rest = REST_FRAMES
        elif self.rest:
            self.rest -= 1
        elif self.rng.random() < TAP_CHANCE:
            self.tap = TAP_FRAMES
        return Pad(buttons=BUTTONS["A"] if self.tap else 0, sx=self.sx, sy=self.sy)


class Walk:
    """The pads for ports 1 to PORTS, one set of them for each call of `pads`. SEED is a whole
    number from 0, and a port's stream is its own, so adding a port leaves the others as they
    were."""

    def __init__(self, seed: int, ports: int) -> None:
        if seed < 0 or not 1 <= ports <= 4:
            raise ValueError("a walk needs a seed from 0 and 1 to 4 ports")
        # Seeds 5n + 1 to 5n + 4 are the ports', and 5n is left for the schedule of rounds.
        self.ports = {port: _Port(random.Random(seed * 5 + port)) for port in range(1, ports + 1)}

    def pads(self) -> dict[int, Pad]:
        return {port: walker.pad() for port, walker in self.ports.items()}
