"""What did tonight's run find, against the last report? nightly.py's checks, read into
summary.txt and report.json in the run's directory under build/nightly/.

A check is one route at one aspect for one step, or one timed number. `changes` compares each
with the same check in the last report:

  flipped    it passed last time and fails now, or failed and passes now
  new        it fails now and the last report has no such check, or there is no last report
  moved      a timed number more than 10% off its value in the last report, or off the number
             status.md gave, whether or not it's inside its bar
  same       it fails now as it did last time

summary.txt fits on one screen. The regressions come first, the flipped, new and moved checks,
each with the route, the frame or field, and the dump or log to look at. Then the checks that
fail as they did last time, then one line per step for what passed, then what was skipped.
report.json holds every check in full, for tools. It has no command line.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

PASS, FAIL = "pass", "fail"
SKIPPED_BATTERY, NOT_RUN = "skipped-battery", "not-run"
MOVE = 0.10  # how far a timed number may move from its last value or status.md's
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


def to_json(checks: list[Check]) -> list[dict]:
    return [asdict(c) for c in checks]


def from_json(rows: list[dict]) -> list[Check]:
    return [Check(**{**r, "problems": [Problem(**p) for p in r.get("problems", [])]}) for r in rows]


def off(value: Optional[float], against: Optional[float]) -> Optional[float]:
    """How far VALUE is from AGAINST, as a share of AGAINST. None when either is missing or AGAINST
    is 0, which no share can be taken of."""
    if value is None or against is None or against == 0:
        return None
    return abs(value - against) / abs(against)


def changes(checks: list[Check], last: Optional[list[Check]]) -> dict[str, list[str]]:
    """Each check's id with the reasons it's a regression, or ["same"] for one that fails as it
    did last time. A check with neither is left out."""
    before = {c.id: c for c in last or []}
    out: dict[str, list[str]] = {}
    for c in checks:
        if c.status not in (PASS, FAIL):
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
                share = off(c.value, against)
                if share is not None and share > MOVE:
                    reasons.append(f"{share:.0%} off {name}'s {against:g}")
        if not reasons and c.status == FAIL:
            reasons.append("same")
        if reasons:
            out[c.id] = reasons
    return out


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
    skipped: dict[str, list[str]] = {}
    for c in checks:
        if c.status in (SKIPPED_BATTERY, NOT_RUN):
            skipped.setdefault(f"{c.step}: {c.status}", []).append(c.id)
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
    passed = pass_lines(checks)
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
