"""The routes in tests/hashes/manifest.txt, and the route files in tests/routes/ they play."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "hashes" / "manifest.txt"
ROUTES = ROOT / "tests" / "routes"


@dataclass
class Route:
    name: str
    seconds: int
    dump_every: int
    required: list[int]
    extra: list[str]


def parse_manifest(text: str) -> list[Route]:
    routes = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, seconds, every, required, *extra = line.split()
        routes.append(Route(name, int(seconds), int(every),
                            [int(f) for f in required.split(",")], extra))
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
