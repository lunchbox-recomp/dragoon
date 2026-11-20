"""Has a triaged checkpoint moved? Tonight's Dolphin diff of a route against its lines in
tests/hashes/dolphin-triage.txt, as the nightly's checks.

A checkpoint's class tonight is refused when the diff refused it, within as dolphin_diff.within
says (at most the budget, with the state the same or a frame off, so a state never read isn't),
and over otherwise, for a person to triage. Against its triage line it fails when:
  - a within line is over or refused
  - any other line is refused, unless it was
  - an over line's share is more than the budget above the line's, the score taken at the
    line's tolerance
  - its state differs where the line's was same or near
and it improves when an over line is within, its share is more than the budget below the
line's, a refused line is matched or a state that differed matches.

A route's race is held to what its lines say. "FIELD first differs at frame N, pass P" puts the
race's first difference at pass P, the earliest a route's lines name, and "matches through
pass P" says no compared value differs through pass P. Tonight's first difference
(race_trace.py) fails at an earlier pass than P, or at P or before for "matches through". It
improves at a later one, or none, but none only when the race was compared to the last pass
Dolphin's run shows; a Dragoon run that never enters the race or leaves it early fails as
compared short. "Matches through" also fails when the race is compared to an earlier pass than
P and no further.

An improvement fails nothing and says to update the triage file. It has no command line.
"""
from __future__ import annotations

import re
from typing import Callable, Optional, Sequence

import dolphin_diff
from dolphin_diff import Triage
from nightly_report import FAIL, PASS, Check, Problem
from race_trace import Race

STEP = "dolphin"
FIRST_PASS = re.compile(r"first differs at frame \d+, pass (\d+)")
THROUGH = re.compile(r"matches through pass (\d+)")
MATCHING = dolphin_diff.MATCHING
UPDATE = "update tests/hashes/dolphin-triage.txt"
SHOWN = 2  # the values that differ a check names before "and N more"


def state_of(entry: dict) -> str:
    return dolphin_diff.STATES[entry["state"]]


def class_now(entry: dict) -> str:
    """Refused, within as dolphin_diff.within says, or over. The step plays only a triage file
    scored at the diff's own budget, so the entry's over is the triage file's."""
    if "refused" in entry:
        return "refused"
    return "within" if dolphin_diff.within(entry) else "over"


def was(t: Triage) -> str:
    if t.cls == "refused":
        return "refused"
    return f"{t.cls} at share {100 * t.share:.3f}% max {t.max}, state {t.state}"


def now(entry: dict) -> str:
    if "refused" in entry:
        return f"refused, {entry['refused']}"
    text = (f"{class_now(entry)} at share {100 * entry['share']:.3f}% max {entry['max']}, "
            f"state {state_of(entry)}")
    differs = entry.get("state_diff") or []
    more = f"; and {len(differs) - SHOWN} more" if len(differs) > SHOWN else ""
    return text + (f" ({'; '.join(differs[:SHOWN])}{more})" if differs else "")


def moves(t: Triage, entry: dict, budget: float) -> tuple[list[str], list[str]]:
    """How ENTRY, tonight's report entry, moved from T: what fails and what improved."""
    cls = class_now(entry)
    if t.cls == "within":
        return ([] if cls == "within" else ["left within"]), []
    if t.cls == "refused":
        return [], ([] if cls == "refused" else ["matched where it was refused"])
    if cls == "refused":
        return ["refused now"], []
    fails, better = [], []
    if cls == "within":
        better.append(f"within where it was {t.cls}")
    elif entry["share"] > t.share + budget:
        fails.append(f"its share rose more than the budget's {100 * budget:g}%")
    elif entry["share"] < t.share - budget:
        better.append(f"its share fell more than the budget's {100 * budget:g}%")
    matched = state_of(entry) in MATCHING
    if t.state in MATCHING and not matched:
        fails.append("its state differs now")
    elif t.state == "differs" and matched and cls != "within":
        better.append("its state matches now")
    return fails, better


Keep = Callable[[dict], Optional[str]]  # keeps a report entry's side-by-side, giving its path


def check(check_id: str, route: str, kind: str, where: str, detail: str, fails: list[str],
          better: list[str], dump: Callable[[], Optional[str]]) -> Check:
    """A failing check with one problem at WHERE when anything FAILS, else a passing one, an
    improvement when anything is BETTER. DUMP keeps the picture for either and gives its path."""
    if fails:
        png = dump()
        return Check(check_id, STEP, FAIL, kind=kind, route=route, detail=detail, dump=png,
                     problems=[Problem(where, f"{', '.join(fails)}: {detail}", png)])
    if better:
        return Check(check_id, STEP, PASS, route=route, detail=detail, dump=dump(),
                     better=f"{', '.join(better)}, {UPDATE}")
    return Check(check_id, STEP, PASS, route=route, detail=detail)


def checkpoint_check(route: str, t: Triage, entry: Optional[dict], budget: float,
                     keep: Keep) -> Check:
    check_id = f"{STEP} {route} {t.frame}"
    if entry is None:
        return Check(check_id, STEP, FAIL, kind="not compared", route=route,
                     detail=f"frame {t.frame} isn't in tonight's diff")
    fails, better = moves(t, entry, budget)
    detail = f"{was(t)} in the triage file, {now(entry)} tonight"
    return check(check_id, route, "moved", f"frame {t.frame}", detail, fails, better,
                 lambda: keep(entry))


def marks(lines: Sequence[Triage]) -> tuple[Optional[int], Optional[int]]:
    """The pass the earliest first difference LINES name comes at, and the furthest pass they
    say every value matches through, None for either they don't name."""
    first = [int(m[1]) for t in lines for m in FIRST_PASS.finditer(t.reason)]
    through = [int(m[1]) for t in lines for m in THROUGH.finditer(t.reason)]
    return (min(first) if first else None), (max(through) if through else None)


def race_moves(first: Optional[int], through: Optional[int], race: Race) -> tuple[list[str], list[str]]:
    if first is not None:
        if race.at is None:
            if race.reach is None or race.through is None or race.through < race.reach:
                return [f"compared short of pass {race.reach}, Dolphin's last, where the first "
                        f"difference was at pass {first}"], []
            return [], [f"no difference now where the first was at pass {first}"]
        if race.at < first:
            return [f"the first difference comes before pass {first}"], []
        return [], ([f"the first difference comes after pass {first}"] if race.at > first else [])
    assert through is not None
    if race.at is not None and race.at <= through:
        return [f"a difference at or before pass {through}"], []
    if race.at is None and (race.through is None or race.through < through):
        return [f"compared short of pass {through}"], []
    return [], []


def race_check(route: str, lines: Sequence[Triage], found: list[Race], entries: list[dict],
               keep: Keep) -> Optional[Check]:
    """ROUTE's race held to what LINES say of it, None when they say nothing. Its picture is the
    side-by-side of the first of ENTRIES, tonight's, at or after the first difference."""
    first, through = marks(lines)
    if first is None and through is None:
        return None
    check_id = f"{STEP} {route} race"
    said = f"pass {first} in the triage file" if first is not None else f"matching through pass {through}"
    if not found:
        return Check(check_id, STEP, FAIL, kind="not compared", route=route,
                     detail=f"no race in tonight's diff, {said}")
    race = found[0]
    fails, better = race_moves(first, through, race)
    later = [e for e in sorted(entries, key=lambda e: e["frame"])
             if race.frame is not None and e["frame"] >= race.frame and "side" in e]
    where = (f"frame {race.frame} pass {race.at}" if race.frame is not None
             else f"pass {race.through}" if race.through is not None else race.name)
    return check(check_id, route, "differs earlier", where, f"{race.text()}, {said}", fails, better,
                 lambda: keep(later[0]) if later else None)


def checks(route: str, lines: Sequence[Triage], budget: float, report: dict, found: list[Race],
           keep: Keep) -> list[Check]:
    """Every check for ROUTE: each of its triage LINES against REPORT, dolphin_diff.compare's,
    then its race from FOUND, race_trace's."""
    entries = {e["frame"]: e for e in report["checkpoints"]}
    out = [checkpoint_check(route, t, entries.get(t.frame), budget, keep)
           for t in sorted(lines, key=lambda t: t.frame)]
    race = race_check(route, lines, found, list(entries.values()), keep)
    return out + ([race] if race is not None else [])
