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
        if source is None or source is r:
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
