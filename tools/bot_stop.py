"""How did the soak's run end, and was that a fault?

`classify` turns a `bot_link.run` Outcome into a `Stop`, or None when the run ended as a bot run
is meant to. The four things the soak stops on are the game exiting or panicking (and the engine
stopping the game), a hang, a frozen picture and a music stream that ended early. The last two
come from the bots' own watchers (bot_watch.py) and arrive as the exception that ended the run.
A walker that finds a menu screen stuck stops the run too. A run that couldn't be judged, such
as a game that never connected or a bot that raised something else, is a `SoakError`, because it
says nothing about the game. It has no command line.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import bot_link
from bot_menus import Stuck
from bot_watch import FROZEN, MUSIC, Detected, Resets

EXIT = "game_exit"  # the game ended on its own: it exited, shut down or died
PANIC = "panic"  # panic.txt, or the engine's FATAL or FAULT line
ENGINE_STOP = "engine_stop"  # the engine stopped the game with its own `[bot] frame N: ...` line
HANG = "hang"  # no frame for the hang limit
MENUS_STUCK = "menus_stuck"  # a menu screen stayed up past the walker's limit
KINDS = (EXIT, PANIC, ENGINE_STOP, HANG, FROZEN, MUSIC, MENUS_STUCK)
# A first reset whose shader rebuild took this share of the hang limit may be what a later hang is.
NEAR_HANG = 2 / 3

_REASONS = {
    bot_link.GAME_EXITED: EXIT, bot_link.GAME_DIED: EXIT, bot_link.SHUTDOWN: EXIT, bot_link.EXIT_AFTER: EXIT,
    bot_link.PANIC: PANIC, bot_link.ENGINE_STOP: ENGINE_STOP, bot_link.HANG: HANG,
}


class SoakError(Exception):
    """The run could not be judged: the game never connected, the link broke or a bot raised an
    error that isn't a finding."""


@dataclass
class Stop:
    kind: str  # one of KINDS
    detail: str
    frame: Optional[int]  # the last frame the engine sent, or None when it isn't known in its own process
    resets_before: int = 0  # console resets before it, so its process began from the card a reset left
    before_reset: bool = False  # a reset came after it, so the last process's replay can't show it
    session: Optional[str] = None  # the session directory of the process it was in, kept for that case

    @property
    def after_reset(self) -> bool:
        return self.resets_before > 0


def near_hang(shaders_ms: int, hang: Optional[float]) -> bool:
    """Whether a restart that rebuilt the shader cache in SHADERS_MS is a good part of a HANG
    seconds limit, which that rebuild is counted against."""
    return hang is not None and shaders_ms / 1000 >= hang * NEAR_HANG


def _found(found: Detected, resets: Optional[Resets]) -> Stop:
    """The Stop a watcher's finding is. One read from the log knows the resets before it, so a
    reset that came after it is told apart, and then the frame is in a process the last one
    isn't. One from no log (the picture) is after the resets the log has shown so far."""
    if found.resets is None:
        return Stop(found.kind, found.detail, found.frame, 0 if resets is None else resets.count)
    if resets is not None and resets.count > found.resets:
        return Stop(found.kind, found.detail, None, found.resets, True, found.session)
    return Stop(found.kind, found.detail, found.frame, found.resets)


def classify(outcome: bot_link.Outcome, resets: Optional[Resets] = None, hang: Optional[float] = None,
             *, asked_exit_after: bool = False, late: Optional[Detected] = None) -> Optional[Stop]:
    """The stop OUTCOME is, or None for a run that ended as it should: at its time limit, or at
    an --exit-after the run was given (ASKED_EXIT_AFTER). A game that shuts itself down, or ends
    at an --exit-after nobody asked for, has exited. RESETS is what the log showed of console
    resets, and HANG the limit the run had, for a hang that follows a slow restart. LATE is a
    finding from the log's last lines, which is the stop only when the run had none of its own.
    Raises SoakError for a run that says nothing about the game."""
    reason, error = outcome.reason, outcome.error
    if reason == bot_link.TIME_LIMIT or (reason == bot_link.EXIT_AFTER and asked_exit_after):
        return None if late is None else _found(late, resets)
    if reason == bot_link.BOT_RAISED:
        if isinstance(error, Detected):
            return _found(error, resets)
        if isinstance(error, Stuck):
            stop = Stop(MENUS_STUCK, str(error), outcome.last_frame)
        else:
            raise SoakError(f"a bot raised {outcome.detail}") from error
    elif reason in _REASONS:
        stop = Stop(_REASONS[reason], outcome.detail, outcome.last_frame)
    else:
        raise SoakError(f"{reason}: {outcome.detail}")
    if resets is not None:
        stop.resets_before = resets.count
        if stop.kind == HANG and resets.shaders_ms is not None and near_hang(resets.shaders_ms, hang):
            stop.detail += (f". The first reset's shader rebuild took {resets.shaders_ms / 1000:.1f} s of the "
                            f"{hang:g} s hang limit, so this may be that rebuild; run again with a higher --hang")
    return stop
