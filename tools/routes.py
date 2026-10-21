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


def route_file(name: str) -> Path:
    return ROUTES / f"{name}.txt"
