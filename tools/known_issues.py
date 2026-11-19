"""Which state checks does the nightly run expect to fail? tests/hashes/known-issues.txt, one line a bug:

  state air-ride-courses-2 16:9 19400 player1.speed=26.0290222 ... Beanstalk Park plays differently ...

the route, the aspect, the checkpoint it fails at, each field that's wrong there with the value
the bug gives it, and what's wrong. `read` gives each check's id, as nightly_steps.py names it,
with its Issue. A check is the known issue only when its state is the golden's with those values
put in at that checkpoint, so a new failure anywhere, at that checkpoint too, still fails. It has
no command line.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

NAME = "known-issues.txt"
LINE = re.compile(r"state (\S+) (4:3|16:9) (\d+)((?: [a-z0-9_.]+=\S+)+) (\S.*)")


@dataclass(frozen=True)
class Issue:
    checkpoint: int  # the frame the check fails at
    values: dict[str, str] = field(hash=False)  # each field the bug changes there, with its value
    bug: str = ""

    def golden(self, golden: dict[int, tuple[int, dict]]) -> dict[int, tuple[int, dict]]:
        """GOLDEN as the bug plays it, with VALUES at CHECKPOINT."""
        out = dict(golden)
        if self.checkpoint in out:
            at, state = out[self.checkpoint]
            out[self.checkpoint] = (at, {**state, **self.values})
        return out


def parse(text: str, where: str = NAME) -> dict[str, Issue]:
    issues = {}
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        m = LINE.fullmatch(line.strip())
        if not m:
            raise ValueError(f"{where}: line {n}: not 'state ROUTE ASPECT CHECKPOINT FIELD=VALUE ... BUG': {line!r}")
        values = dict(p.split("=", 1) for p in m[4].split())
        issues[f"state {m[2]} {m[1]}"] = Issue(int(m[3]), values, m[5])
    return issues


def read(hashes: Path) -> dict[str, Issue]:
    """The known issues in HASHES/known-issues.txt, none when there's no such file."""
    path = hashes / NAME
    return parse(path.read_text(), str(path)) if path.is_file() else {}
