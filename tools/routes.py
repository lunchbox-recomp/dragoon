"""The routes in tests/hashes/manifest.txt, and the route files in tests/routes/ they play."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "hashes" / "manifest.txt"
ROUTES = ROOT / "tests" / "routes"
WARM = "warm="  # the manifest's one setting for warm_shaders.py, which probe.sh never sees
FRAME = re.compile(r"[1-9][0-9]*")  # ASCII digits only, with no sign, underscore or leading 0


@dataclass
class Route:
    name: str
    seconds: int
    dump_every: int
    required: list[int]
    extra: list[str]  # probe.sh settings
    warm: Optional[int] = None  # the frame warm_shaders.py plays the route to, if the manifest says


def warm_frame(settings: list[str], required: list[int]) -> Optional[int]:
    """The frame the one warm=N in SETTINGS names, or None when there's none.

    Raises ValueError for a second warm=, for an N that isn't a whole number past the last of
    REQUIRED, and for a setting that looks like a misspelled warm=, such as WARM= or warm:.
    """
    found = None
    for s in settings:
        if not s.startswith(WARM):
            if s.lstrip("-").lower().startswith("warm"):
                raise ValueError(f"{s} isn't a setting, and the warm-up's is warm=N")
            continue
        if found is not None:
            raise ValueError(f"{s} is a second warm=")
        value = s[len(WARM):]
        if not FRAME.fullmatch(value) or int(value) <= max(required):
            raise ValueError(f"{s} isn't a whole frame number past the last required frame, "
                             f"{max(required)}")
        found = int(value)
    return found


def parse_manifest(text: str) -> list[Route]:
    """The routes TEXT lists. A bad warm= raises ValueError naming the route and the line."""
    routes = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, seconds, every, required, *settings = line.split()
        frames = [int(f) for f in required.split(",")]
        try:
            warm = warm_frame(settings, frames)
        except ValueError as e:
            raise ValueError(f"manifest line {number}, route {name}: {e}") from None
        routes.append(Route(name, int(seconds), int(every), frames,
                            [s for s in settings if not s.startswith(WARM)], warm))
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
