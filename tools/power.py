"""Is the Mac on AC power? The nightly run asks before it starts each game process.

`pmset -g batt` names the source on its first line, "Now drawing from 'AC Power'" or "Now
drawing from 'Battery Power'". A Mac with no battery says 'AC Power' too. `source` reads that
name, `require_ac` raises `OnBattery` for any source but AC, and a pmset that won't run or
prints something else is a ValueError. It has no command line.
"""
from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence

PMSET = ("pmset", "-g", "batt")
AC = "AC Power"
SOURCE = re.compile(r"Now drawing from '([^']+)'")


class OnBattery(Exception):
    """The Mac is drawing from something other than AC power, which the message names."""


def source(text: str) -> str:
    """The power source the first line of `pmset -g batt` output TEXT names."""
    first = text.splitlines()[0] if text else ""
    m = SOURCE.match(first)
    if not m:
        raise ValueError(f"pmset -g batt: no power source on its first line, {first!r}")
    return m[1]


def require_ac(command: Sequence[str] = PMSET) -> None:
    """Return when COMMAND, pmset -g batt by default, says the Mac draws from AC power.
    Raises OnBattery when it names another source."""
    try:
        done = subprocess.run(list(command), capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        raise ValueError(f"{' '.join(command)}: {e}") from None
    now = source(done.stdout)
    if now != AC:
        raise OnBattery(f"drawing from {now!r}, not {AC!r}")
