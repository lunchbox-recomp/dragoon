"""The routes in tests/hashes/manifest.txt, and the route files in tests/routes/ they play."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "hashes" / "manifest.txt"
ROUTES = ROOT / "tests" / "routes"
WARM = "warm="  # the manifest's one setting for warm_shaders.py, which probe.sh never sees


@dataclass
class Route:
    name: str
    seconds: int
    dump_every: int
    required: list[int]
    extra: list[str]  # probe.sh settings
    warm: Optional[int] = None  # the frame warm_shaders.py plays the route to, if the manifest says


def parse_manifest(text: str) -> list[Route]:
    routes = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, seconds, every, required, *settings = line.split()
        warm = [s.removeprefix(WARM) for s in settings if s.startswith(WARM)]
        routes.append(Route(name, int(seconds), int(every),
                            [int(f) for f in required.split(",")],
                            [s for s in settings if not s.startswith(WARM)],
                            int(warm[-1]) if warm else None))
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
