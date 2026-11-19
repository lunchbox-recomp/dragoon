"""Which checks does the nightly run expect to fail? tests/hashes/known-issues.txt, one line a bug:

  state air-ride-courses-2 16:9 19400 Beanstalk Park plays differently at 16:9. ...

the check (frames or state), the route, the aspect, the first checkpoint it fails at and what's
wrong. `read` gives each check's id, as nightly_steps.py names it, with its Issue. A check that
fails first at that checkpoint is the known issue. It has no command line.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

NAME = "known-issues.txt"
LINE = re.compile(r"(frames|state) (\S+) (4:3|16:9) (\d+) (\S.*)")


@dataclass(frozen=True)
class Issue:
    checkpoint: int  # the first frame the check fails at
    bug: str


def parse(text: str, where: str = NAME) -> dict[str, Issue]:
    issues = {}
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        m = LINE.fullmatch(line.strip())
        if not m:
            raise ValueError(f"{where}: line {n}: not 'frames|state ROUTE ASPECT CHECKPOINT BUG': {line!r}")
        issues[f"{m[1]} {m[3]} {m[2]}"] = Issue(int(m[4]), m[5])
    return issues


def read(hashes: Path) -> dict[str, Issue]:
    """The known issues in HASHES/known-issues.txt, none when there's no such file."""
    path = hashes / NAME
    return parse(path.read_text(), str(path)) if path.is_file() else {}
