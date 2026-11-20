"""Where does a race first play differently in Dragoon than in Dolphin? Each Dragoon frame of a
race against Dolphin's fields at the same pass.

dolphin_diff.py's Dragoon run reads every compared value, dolphin_diff.FIELDS, and the race's
pass at every frame of a race into state.json's trace. For each race in Dolphin's run, a race
by dolphin_diff.RACES, `races` takes the trace's frames in that scene in order. A frame matches
when its values are all the same as Dolphin's at a field whose pass is the frame's or one
either side, as dolphin_diff compares a race's checkpoint, since Dolphin reads RAM partway into
a pass. The first frame that doesn't is the race's first difference, with each value that
differs from Dolphin's first field at that pass. A frame whose pass no field of the race shows,
past the end of Dolphin's run, is left out. It has no command line.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import dolphin_diff
from dolphin_diff import PASSES, RACES

State = dict  # a field's name to its value as text, as state_goldens reads it
SHOWN = 3  # the values that differ `text` names before "and N more"


@dataclass
class Race:
    name: str  # RACES' name for it
    reach: Optional[int]  # the last pass Dolphin's run shows, None when it shows none
    through: Optional[int] = None  # the last pass compared before the first difference
    frame: Optional[int] = None  # the first difference's Dragoon frame, None when there's none
    at: Optional[int] = None  # and its pass
    differs: list[str] = field(default_factory=list)  # each value that differs there

    def text(self) -> str:
        if self.frame is not None:
            more = f"; and {len(self.differs) - SHOWN} more" if len(self.differs) > SHOWN else ""
            return (f"{self.name} first differs at frame {self.frame}, pass {self.at}: "
                    + "; ".join(self.differs[:SHOWN]) + more)
        if self.through is None:
            return f"{self.name}: no pass compared"
        return f"{self.name}: every compared value matches through pass {self.through}"


def read_trace(rows: dict) -> dict[int, State]:
    """state.json's trace, by frame."""
    return {int(f): s for f, s in rows.items()}


def first_difference(name: str, scene: tuple[int, int], keys: Sequence[Optional[int]],
                     rows: Sequence[dict[str, int]], trace: dict[int, State]) -> Race:
    """TRACE's frames in SCENE against ROWS, Dolphin's fields, whose passes KEYS gives (None
    outside the scene)."""
    fields_at: dict[int, list[int]] = {}
    for n, k in enumerate(keys):
        if k is not None:
            fields_at.setdefault(k, []).append(n)
    race = Race(name, max(fields_at) if fields_at else None)
    read: dict[int, State] = {}

    def dolphin(n: int, names: list[str]) -> State:
        if n not in read:
            read[n] = dolphin_diff.state_of(rows[n], names)
        return read[n]

    for frame in sorted(trace):
        state = trace[frame]
        if (int(state["scene.major"]), int(state["scene.minor"])) != scene:
            continue
        at = int(state[PASSES])
        if at not in fields_at:
            continue
        want = {k: v for k, v in state.items() if k != PASSES}
        names = list(want)
        if any(dolphin(n, names) == want for p in (at - 1, at, at + 1) for n in fields_at.get(p, ())):
            race.through = at
            continue
        got = dolphin(fields_at[at][0], names)
        race.frame, race.at = frame, at
        race.differs = [f"{k}: Dragoon {v}, Dolphin {got[k]}" for k, v in want.items() if got[k] != v]
        break
    return race


def races(lines: Sequence[str], trace: dict[int, State]) -> list[Race]:
    """Each race in Dolphin's run, its ram.txt LINES, against Dragoon's TRACE."""
    rows, counts = dolphin_diff.ram_rows(lines), dolphin_diff.passes(lines)
    found = dolphin_diff.scenes(lines)
    out = []
    for i, (_, scene, since) in enumerate(found):
        if scene in RACES:
            until = found[i + 1][2] if i + 1 < len(found) else 0
            out.append(first_difference(RACES[scene], scene,
                                        dolphin_diff.scene_passes(counts, since, until), rows, trace))
    return out
