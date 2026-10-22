"""The source-info.json at the root of a source snapshot: the commits it holds and the disc it builds.

A snapshot has no git history, so this file carries what git would say. export_source.py
writes it, warm_shaders.py reads the engine commit from it, and the launcher reads the disc ID
and main.dol SHA-1 it checks a disc against.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

NAME = "source-info.json"
_COMMIT = re.compile(r"[0-9a-f]{40}")
FIELDS = {
    "dragoon": _COMMIT,
    "gcn-recomp": _COMMIT,
    "disc_id": re.compile(r"[0-9A-Z]{6}"),
    "dol_sha1": re.compile(r"[0-9a-f]{40}"),
}


def _checked(data: object, path: Path) -> dict[str, str]:
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a JSON object")
    for key, pattern in FIELDS.items():
        value = data.get(key)
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise ValueError(f"{path}: {key} is missing or malformed")
    return {key: data[key] for key in FIELDS}


def read(path: Path) -> dict[str, str]:
    """The four FIELDS from PATH. Raises ValueError naming PATH when one is missing or
    malformed, and OSError when PATH can't be read."""
    try:
        data = json.loads(path.read_text())
    except ValueError as e:
        raise ValueError(f"{path}: not JSON ({e})") from None
    return _checked(data, path)


def write(path: Path, fields: dict[str, str]) -> None:
    """Write the four FIELDS to PATH, refusing what read() would refuse."""
    path.write_text(json.dumps(_checked(fields, path), indent=2, sort_keys=True) + "\n")
