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

EXIT = "game_exit"  # the game ended on its own, or without its input log's end
PANIC = "panic"  # panic.txt, or the engine's FATAL or FAULT line
ENGINE_STOP = "engine_stop"  # the engine stopped the game with its own `[bot] frame N: ...` line
HANG = "hang"  # no frame for the hang limit
MENUS_STUCK = "menus_stuck"  # a menu screen stayed up past the walker's limit
KINDS = (EXIT, PANIC, ENGINE_STOP, HANG, FROZEN, MUSIC, MENUS_STUCK)
# A first reset whose shader rebuild took this share of the hang limit may be what a later hang is.
NEAR_HANG = 2 / 3

_REASONS = {
    bot_link.GAME_EXITED: EXIT, bot_link.GAME_DIED: EXIT, bot_link.PANIC: PANIC,
    bot_link.ENGINE_STOP: ENGINE_STOP, bot_link.HANG: HANG,
}


class SoakError(Exception):
    """The run could not be judged: the game never connected, the link broke or a bot raised an
    error that isn't a finding."""


@dataclass
class Stop:
    kind: str  # one of KINDS
    detail: str
    frame: Optional[int]  # the last frame the engine sent
    after_reset: bool = False  # the game had reset the console before it, which a replay can't show


def near_hang(shaders_ms: int, hang: Optional[float]) -> bool:
    """Whether a restart that rebuilt the shader cache in SHADERS_MS is a good part of a HANG
    seconds limit, which that rebuild is counted against."""
    return hang is not None and shaders_ms / 1000 >= hang * NEAR_HANG


def classify(outcome: bot_link.Outcome, resets: Optional[Resets] = None,
             hang: Optional[float] = None) -> Optional[Stop]:
    """The stop OUTCOME is, or None for a run that ended as it should. RESETS is what the log
    showed of console resets, and HANG the limit the run had, for a hang that follows a slow
    restart. Raises SoakError for a run that says nothing about the game."""
    reason, error = outcome.reason, outcome.error
    if reason in bot_link.CLEAN:
        return None
    if reason == bot_link.BOT_RAISED:
        if isinstance(error, Detected):
            stop = Stop(error.kind, error.detail, error.frame)
        elif isinstance(error, Stuck):
            stop = Stop(MENUS_STUCK, str(error), outcome.last_frame)
        else:
            raise SoakError(f"a bot raised {outcome.detail}") from error
    elif reason in _REASONS:
        stop = Stop(_REASONS[reason], outcome.detail, outcome.last_frame)
    else:
        raise SoakError(f"{reason}: {outcome.detail}")
    if resets is not None:
        stop.after_reset = resets.count > 0
        if stop.kind == HANG and resets.shaders_ms is not None and near_hang(resets.shaders_ms, hang):
            stop.detail += (f". The first reset's shader rebuild took {resets.shaders_ms / 1000:.1f} s of the "
                            f"{hang:g} s hang limit, so this may be that rebuild; run again with a higher --hang")
    return stop
