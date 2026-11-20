"""What did tonight's run find, against the last report? nightly.py's checks, read into
summary.txt and report.json in the run's directory under build/nightly/.

A check is one route at one aspect for one step, or one timed number. `changes` compares each
with the same check in the last report:

  flipped    it passed last time and fails now, or failed and passes now
  new        it fails now and the last report has no such check, or there is no last report
  slower     a timed number more than 10% and more than FLOOR ms above its value in the last
             report, or above the number status.md gave, whether or not it's inside its bar
  same       it fails now as it did last time

A timed number that far below status.md's is improved, which fails nothing but says status.md
can be updated, and so is a passing check whose `better` says how it beat the file it's held to,
such as a Dolphin checkpoint that's now within (dolphin_moves.py). A check that's a known issue
(known_issues.py) is neither. A skipped check, a step with nothing to play on such as no Dolphin,
fails nothing and is listed with why.

summary.txt fits on one screen. The regressions come first, the flipped, new and slower checks,
each with the route, the frame or field, and the dump or log to look at. Then the checks that
fail as they did last time, the known issues, the improved numbers, one line per step for what
passed and last what was skipped. report.json holds every check in full, for tools. It has no
command line.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Optional

PASS, FAIL = "pass", "fail"
SKIPPED_BATTERY, NOT_RUN = "skipped-battery", "not-run"
SKIPPED = "skipped"  # a step with nothing to play it on, such as no Dolphin, its detail saying so
MOVE = 0.10  # how far a timed number may rise above its last value or status.md's
# And by more than this many ms. It's 1.5% of a 60 Hz frame's 16.67 ms, under which no number
# here costs a player a frame, and it keeps a 0.72 ms number from failing on a 0.08 ms wobble.
FLOOR = 0.25
REPORT = "report.json"
SUMMARY = "summary.txt"
LINES = 40  # the most lines the regressions and same-failure sections take between them


@dataclass
class Problem:
    where: str  # "frame 4200", or "frame 4200 scene.minor" for a state field
    what: str
    dump: Optional[str] = None  # a path under the report's directory


@dataclass
class Check:
    id: str  # unique in a report, such as "frames 16:9 air-ride-race"
    step: str
    status: str  # PASS, FAIL, SKIPPED_BATTERY or NOT_RUN
    detail: str = ""
    kind: str = ""  # what a failure means, such as "drew differently" or "played differently"
    route: Optional[str] = None
    problems: list[Problem] = field(default_factory=list)
    value: Optional[float] = None  # a timed number
    unit: str = ""
    limit: Optional[float] = None
    status_value: Optional[float] = None  # status.md's number, None where it has none
    timed: bool = False  # whether the 10% rule applies
    load: Optional[list[float]] = None  # the 1-minute load as the run began and ended
    dump: Optional[str] = None  # the file to look at for the whole check
    known: Optional[str] = None  # the bug, for a known issue failing where it's known to or passing now
    better: Optional[str] = None  # how a passing check got better than the file it's held to says


def to_json(checks: list[Check]) -> list[dict]:
    return [asdict(c) for c in checks]


def from_json(rows: list[dict]) -> list[Check]:
    """The checks in a report's rows. A field an older or newer report has that Check doesn't is
    dropped, and one it lacks takes Check's default."""
    names = {f.name for f in fields(Check)}
    return [Check(**{**{k: v for k, v in r.items() if k in names},
                     "problems": [Problem(**p) for p in r.get("problems", [])]}) for r in rows]


def past(value: Optional[float], against: Optional[float]) -> Optional[float]:
    """How far VALUE is above AGAINST as a share of it, when that's more than MOVE and more than
    FLOOR ms. None when it isn't or either is missing."""
    if value is None or against is None or against <= 0:
        return None
    if value > against * (1 + MOVE) and value - against > FLOOR:
        return (value - against) / against
    return None


def improved(c: Check) -> Optional[str]:
    """Why a check that passed should be written down again, None when it shouldn't: its own
    `better`, or a timed number as far below status.md's number as a regression would be above."""
    if c.status == PASS and c.better:
        return c.better
    if not c.timed or c.status != PASS or c.value is None or c.status_value is None:
        return None
    share = past(c.status_value, c.value)
    if share is None:
        return None
    return f"{(c.status_value - c.value) / c.status_value:.0%} under status.md's {c.status_value:g}, update status.md"


def changes(checks: list[Check], last: Optional[list[Check]]) -> dict[str, list[str]]:
    """Each check's id with the reasons it's a regression, or ["same"] for one that fails as it
    did last time. A check with neither, or a known issue, is left out."""
    before = {c.id: c for c in last or []}
    out: dict[str, list[str]] = {}
    for c in checks:
        if c.status not in (PASS, FAIL) or c.known is not None:
            continue
        reasons = []
        prior = before.get(c.id)
        if prior is not None and prior.status in (PASS, FAIL) and prior.status != c.status:
            reasons.append(f"flipped, {prior.status} last time")
        elif c.status == FAIL and prior is None:
            reasons.append("new")
        if c.timed:
            for name, against in (("last", prior.value if prior is not None else None),
                                  ("status.md", c.status_value)):
                share = past(c.value, against)
                if share is not None:
                    reasons.append(f"{share:.0%} slower than {name}'s {against:g}")
        if not reasons and c.status == FAIL:
            reasons.append("same")
        if reasons:
            out[c.id] = reasons
    return out


def failing(checks: list[Check]) -> list[Check]:
    """The checks that fail the run: every failure but a known issue's."""
    return [c for c in checks if c.status == FAIL and c.known is None]


def number(c: Check) -> str:
    if c.value is None:
        return "no value"
    text = f"{c.value:.2f}" if c.unit == "ms" else f"{c.value:g}"
    unit = f" {c.unit}" if c.unit and c.unit != "frame" else ""
    shown = f"frame {text}" if c.unit == "frame" else f"{text}{unit}"
    if c.limit is not None:
        shown += f" (bar {c.limit:g})"
    if c.load:
        shown += f", load {c.load[0]:.1f} to {c.load[1]:.1f}"
    return shown


def line(c: Check, reasons: list[str], dumps: bool = True) -> str:
    """One check as the summary shows it."""
    if c.timed or c.value is not None:
        what = number(c)
    else:
        what = c.kind if c.status == FAIL and c.kind else c.status
    first = c.problems[0] if c.problems else None
    text = f"  {c.id}: {what}"
    if first is not None:
        more = f", and {len(c.problems) - 1} more" if len(c.problems) > 1 else ""
        text += f", {first.where} {first.what}{more}"
    elif c.detail:
        text += f", {c.detail}"
    dump = first.dump if first is not None and first.dump else c.dump
    if dump and dumps:
        text += f" -> {dump}"
    if reasons and reasons != ["same"]:
        text += f" [{'; '.join(reasons)}]"
    return text


def pass_lines(checks: list[Check]) -> list[str]:
    """One line a step for its passes, and one for each that has a number, such as a timed one."""
    lines = []
    steps: dict[str, list[Check]] = {}
    for c in checks:
        if c.status == PASS:
            steps.setdefault(c.step, []).append(c)
    for step, passed in steps.items():
        counted = [c for c in passed if c.value is None]
        if counted:
            total = sum(1 for c in checks if c.step == step and c.value is None and c.status in (PASS, FAIL))
            kinds: dict[str, int] = {}
            for c in counted:
                kinds[c.id.split(" ")[0]] = kinds.get(c.id.split(" ")[0], 0) + 1
            parts = ", ".join(f"{n} {kind}" for kind, n in kinds.items())
            lines.append(f"  {step}: {len(counted)} of {total} checks pass ({parts})")
        lines += [line(c, [], dumps=False) for c in passed if c.value is not None]
    return lines


def summary(head: list[str], checks: list[Check], last: Optional[list[Check]]) -> str:
    found = changes(checks, last)
    regressions = [c for c in checks if c.id in found and found[c.id] != ["same"]]
    same = [c for c in checks if found.get(c.id) == ["same"]]
    known = [c for c in checks if c.known is not None and c.status in (PASS, FAIL)]
    better = [c for c in checks if improved(c) is not None and c not in regressions]
    skipped: dict[str, list[str]] = {}
    for c in checks:
        if c.status in (SKIPPED_BATTERY, NOT_RUN):
            skipped.setdefault(f"{c.step}: {c.status}", []).append(c.id)
        elif c.status == SKIPPED:
            skipped.setdefault(f"{c.step}: skipped: {c.detail}", []).append(c.id)
    out = list(head)
    budget = LINES
    for title, group in (("Regressions", regressions), ("Failing as last time", same)):
        if not group:
            continue
        out.append(f"{title} ({len(group)})")
        shown = group[:max(budget, 1)]
        out += [line(c, found[c.id]) for c in shown]
        budget -= len(shown)
        if len(group) > len(shown):
            out.append(f"  and {len(group) - len(shown)} more in {REPORT}")
    if known:
        out.append(f"Known issues ({len(known)})")
        out += [line(c, [f"known: {c.known}"]) if c.status == FAIL
                else f"  {c.id}: passes now, so its line in known-issues.txt can go [known: {c.known}]"
                for c in known]
    if better:
        out.append(f"Improved ({len(better)})")
        out += [line(c, [improved(c) or ""], dumps=c.better is not None) for c in better]
    passed = pass_lines([c for c in checks if c.value is None or (c not in regressions and c not in better)])
    if passed:
        out.append("Passes")
        out += passed
    if skipped:
        out.append("Skipped")
        out += [f"  {what} ({len(ids)} checks)" for what, ids in skipped.items()]
    return "\n".join(out) + "\n"


def last_report(nightly: Path, before: Path) -> Optional[Path]:
    """The newest report.json in NIGHTLY's run directories older than BEFORE's name, None for none."""
    if not nightly.is_dir():
        return None
    runs = sorted(d for d in nightly.iterdir() if d.is_dir() and d.name < before.name and (d / REPORT).is_file())
    return runs[-1] / REPORT if runs else None


def read(path: Path) -> list[Check]:
    return from_json(json.loads(path.read_text())["checks"])


def readable(path: Optional[Path]) -> tuple[Optional[Path], Optional[str]]:
    """PATH, a report.json or the directory holding one, when it reads as a report, or None and why
    it doesn't, so a run that can't compare says so up front instead of failing at the end."""
    if path is None:
        return None, None
    if path.is_dir():
        path = path / REPORT
    try:
        read(path)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        return None, f"{path} isn't a report ({type(e).__name__}: {e}), so nothing is compared"
    return path, None


def write(directory: Path, head: list[str], info: dict, checks: list[Check],
          last: Optional[list[Check]]) -> str:
    """Write summary.txt and report.json in DIRECTORY and return the summary."""
    text = summary(head, checks, last)
    found = changes(checks, last)
    data = {**info, "regressions": sorted(k for k, v in found.items() if v != ["same"]),
            "changes": found, "checks": to_json(checks)}
    (directory / REPORT).write_text(json.dumps(data, indent=1) + "\n")
    (directory / SUMMARY).write_text(text)
    return text
