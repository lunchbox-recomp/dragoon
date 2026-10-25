"""How many Core Audio overloads did macOS log while a session ran?

An overload is Core Audio's own report that an IO cycle missed its deadline, logged by
coreaudiod or inside the playing process as "HALC_ProxyIOContext::IOWorkLoop: skipping
cycle due to overload". This builds the read-only `log show` command for a window of wall
clock time and counts the lines of its compact output that match: subsystem
com.apple.coreaudio, with "overload" in the message, in any letter case. The predicate asks
`log` for exactly those, and the count checks each line again, so a line from another
subsystem can't be counted. The unified log keeps such messages for days, not weeks, so an
old session's window can come back empty. It has no command line.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

SUBSYSTEM = "com.apple.coreaudio"
WORD = "overload"
PREDICATE = f'subsystem == "{SUBSYSTEM}" AND eventMessage CONTAINS[c] "{WORD}"'
# 2026-10-22 15:39:18.670 Df coreaudiod[434:108cbe44] [com.apple.coreaudio:AMCP]   HALS_...
# A process name can hold spaces and brackets, so it runs up to the last [pid:tid] on the line.
LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+) +(\S+) +(.+)\[(\d+):[0-9a-f]+\] "
                  r"\[([^:\]]*):[^\]]*\] (.*)$")


def command(start: datetime, end: datetime) -> list[str]:
    """`log show` over [start, end], local wall-clock times, in compact style."""
    fmt = "%Y-%m-%d %H:%M:%S"
    return ["/usr/bin/log", "show", "--style", "compact", "--start", start.strftime(fmt),
            "--end", end.strftime(fmt), "--predicate", PREDICATE]


def overloads(text: str) -> Counter[str]:
    """The matching lines in compact `log show` output, counted by process."""
    found: Counter[str] = Counter()
    for line in text.splitlines():
        m = LINE.match(line)
        if m and m[5] == SUBSYSTEM and WORD in m[6].lower():
            found[m[3]] += 1
    return found
