"""The routes in tests/hashes/manifest.txt, and the route files in tests/routes/ they play."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "hashes" / "manifest.txt"
ROUTES = ROOT / "tests" / "routes"
# The manifest's two settings for warm_shaders.py, which probe.sh never sees
WARM = "warm="
WARM_FROM = "warm-from="
FRAME = re.compile(r"[1-9][0-9]*")  # ASCII digits only, with no sign, underscore or leading 0


@dataclass
class Route:
    name: str
    seconds: int
    dump_every: int
    required: list[int]
    extra: list[str]  # probe.sh settings
    warm: Optional[int] = None  # the frame warm_shaders.py plays the route to, if the manifest says
    warm_from: Optional[str] = None  # the route whose warm-up pass plays what this one does


def warm_settings(settings: list[str], required: list[int]) -> tuple[Optional[int], Optional[str]]:
    """The frame the one warm=N in SETTINGS names and the route its one warm-from=ROUTE names,
    each None when there's none.

    Raises ValueError for a second warm= or warm-from=, for both on one route, for an N that
    isn't a whole number past the last of REQUIRED, and for a setting that looks like a
    misspelled one, such as WARM= or warm:.
    """
    frame, source = None, None
    for s in settings:
        if s.startswith(WARM_FROM):
            if source is not None:
                raise ValueError(f"{s} is a second warm-from=")
            source = s[len(WARM_FROM):]
            if not source:
                raise ValueError(f"{s} names no route")
            continue
        if not s.startswith(WARM):
            if s.lstrip("-").lower().startswith("warm"):
                raise ValueError(f"{s} isn't a setting, and the warm-up's are warm=N and "
                                 f"warm-from=ROUTE")
            continue
        if frame is not None:
            raise ValueError(f"{s} is a second warm=")
        value = s[len(WARM):]
        if not FRAME.fullmatch(value) or int(value) <= max(required):
            raise ValueError(f"{s} isn't a whole frame number past the last required frame, "
                             f"{max(required)}")
        frame = int(value)
    if frame is not None and source is not None:
        raise ValueError(f"warm={frame} and warm-from={source} together, but a route with "
                         f"warm-from= has no pass of its own to play to frame {frame}")
    return frame, source


def parse_manifest(text: str) -> list[Route]:
    """The routes TEXT lists. A bad warm= or warm-from= raises ValueError naming the route and
    the line. A warm-from= has to name another route in TEXT that has a pass of its own."""
    routes, lines = [], []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, seconds, every, required, *settings = line.split()
        frames = [int(f) for f in required.split(",")]
        try:
            warm, warm_from = warm_settings(settings, frames)
        except ValueError as e:
            raise ValueError(f"manifest line {number}, route {name}: {e}") from None
        routes.append(Route(name, int(seconds), int(every), frames,
                            [s for s in settings if not s.startswith((WARM, WARM_FROM))],
                            warm, warm_from))
        lines.append(number)
    by_name = {r.name: r for r in routes}
    for r, number in zip(routes, lines):
        if r.warm_from is None:
            continue
        source = by_name.get(r.warm_from)
        if source is None or r.warm_from == r.name:
            why = "names no other route in the manifest"
        elif source.warm_from is not None:
            why = f"names a route that {source.warm_from}'s pass plays"
        else:
            continue
        raise ValueError(f"manifest line {number}, route {r.name}: warm-from={r.warm_from} {why}")
    return routes


def select_routes(names: list[str], manifest: Path = MANIFEST) -> list[Route]:
    """The manifest's routes called NAMES, or all of them when NAMES is empty."""
    routes = parse_manifest(manifest.read_text())
    unknown = set(names) - {r.name for r in routes}
    if unknown:
        raise ValueError(f"not in the manifest: {sorted(unknown)}")
    return [r for r in routes if r.name in names] if names else routes


def route_file(name: str) -> Path:
    return ROUTES / f"{name}.txt"


# A route file's presses, as gcn-recomp's runtime/input_script.cpp reads them.
BUTTONS = ("A", "B", "X", "Y", "Z", "L", "R", "START", "UP", "DOWN", "LEFT", "RIGHT")
STICKS = {"SL": (0, -1), "SR": (0, 1), "SU": (1, 1), "SD": (1, -1)}  # axis (x 0, y 1), sign
PORTS = 4
FULL_PUSH = 100  # SL, SR, SU and SD with no amount


@dataclass(frozen=True)
class Press:
    """One item of a route: BUTTONS down and the main stick pushed STICK (x, y, -100 to 100, 0
    for an axis it leaves alone, as the engine's `if (s.sx)` does) on PORT (0 is port 1) for the
    game's frames AT to AT + DURATION - 1."""
    port: int
    at: int
    duration: int
    buttons: frozenset
    stick: tuple = (0, 0)


def route_script(text: str) -> str:
    """A route file's script: every line that isn't a # comment, joined."""
    return "".join(line.strip() for line in text.splitlines()
                   if line.strip() and not line.strip().startswith("#"))


def parse_route(script: str) -> list[Press]:
    """SCRIPT's presses, `[port/]frame:BUTTON[+BUTTON]:duration` each, comma-separated. Raises
    ValueError for an item the engine would skip or misread, where the engine goes on without
    it, since a press left out sends a route somewhere else."""
    presses = []
    for item in filter(None, (part.strip() for part in script.split(","))):
        port, _, rest = item.rpartition("/")
        fields = rest.split(":")
        bad = ValueError(f"{item!r}: not [port/]frame:BUTTON[+BUTTON]:duration")
        if len(fields) != 3 or not all(FRAME.fullmatch(f) or f == "0" for f in
                                       (fields[0], fields[2], port or "1")):
            raise bad
        chan, at, duration = int(port or "1") - 1, int(fields[0]), int(fields[2])
        if not 0 <= chan < PORTS or duration < 1:
            raise bad
        buttons, stick = set(), [0, 0]
        for name in fields[1].split("+"):
            amount = name[2:]
            if name in BUTTONS:
                buttons.add(name)
            elif name[:2] in STICKS and (not amount or amount == "0" or FRAME.fullmatch(amount)):
                axis, sign = STICKS[name[:2]]
                stick[axis] = sign * (int(amount) if amount else FULL_PUSH)
            else:
                raise ValueError(f"{item!r}: no button {name}")
        presses.append(Press(chan, at, duration, frozenset(buttons), (stick[0], stick[1])))
    return presses
