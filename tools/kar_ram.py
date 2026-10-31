"""Where does Kirby Air Ride keep what a bot needs to see in guest RAM?

tools/kar_ram.json names each value by its address and type, as stable-retro's data.json does.
`load` reads the table into Entry records by name, `decode` turns the bytes read for an entry
into its value and `read` reads one through bot_link.py's Link. ram_peek.py prints them along a
route. It has no command line.

An entry is a big-endian integer of 1, 2 or 4 bytes (u8, s8, u16, s16, u32, s32), a float (f32)
or a fixed run of bytes (bytes, with its length). Each says what it means, what its values mean
where they were confirmed, and the route and frames it was watched over.

A value the game keeps in an object it allocates has a path. Its address then holds a pointer,
and each offset in the path is added to the pointer read there. Every offset but the last leads
to the next pointer, and the last leads to the value. A pointer that's null or leads outside
main RAM means the object isn't there, as for a player who isn't in the game, and `read` gives
None.
"""
from __future__ import annotations

import json
import re
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

TABLE = Path(__file__).resolve().parent / "kar_ram.json"
RAM_START = 0x80000000  # main RAM, as the link reads it
RAM_END = 0x81800000  # one past its last byte
READ_MAX = 256  # the most bytes the link reads at once
POINTER = 4  # a guest pointer's bytes
FORMATS = {"u8": ">B", "s8": ">b", "u16": ">H", "s16": ">h", "u32": ">I", "s32": ">i", "f32": ">f"}
BYTES = "bytes"
FIELDS = {"address", "path", "type", "length", "means", "values", "route", "frames"}
ADDRESS = re.compile(r"[0-9A-F]{8}")
OFFSET = re.compile(r"[0-9A-F]{1,4}")
NAME = re.compile(r"[a-z][a-z0-9_]*(\.[a-z0-9_]+)*")
VALUE = re.compile(r"-?(0|[1-9][0-9]*)")

Value = Union[int, float, bytes]


@dataclass(frozen=True)
class Entry:
    name: str
    address: int  # where the value is, or with a path where its first pointer is
    type: str  # a key of FORMATS, or BYTES
    length: int  # the bytes the value takes
    means: str
    values: Mapping[int, str]  # what its values mean, the ones that were confirmed
    route: str  # the route file in tests/routes/ it was watched on
    frames: tuple[int, int]  # the first and last frame it was watched over
    path: tuple[int, ...] = ()  # the offsets from pointer to pointer, empty for a fixed address

    def meaning(self, value: Value | None) -> str | None:
        """What VALUE means, when the table says."""
        return self.values.get(value) if isinstance(value, int) else None


def size(type_: str) -> int:
    """The bytes a value of TYPE_, a key of FORMATS, takes."""
    return struct.calcsize(FORMATS[type_])


def in_ram(address: int, length: int) -> bool:
    """Whether LENGTH bytes from ADDRESS are all in main RAM."""
    return RAM_START <= address and address + length <= RAM_END


def follow(link, address: int, path: Sequence[int], length: int) -> Optional[int]:
    """Where the LENGTH bytes that PATH leads to from ADDRESS are now, read through LINK. With no
    PATH that's ADDRESS. None when a pointer on the way is null or leads outside main RAM."""
    for i, offset in enumerate(path):
        pointer = struct.unpack(">I", link.read(address, POINTER))[0]
        address = pointer + offset
        if not in_ram(pointer, 1) or not in_ram(address, POINTER if i + 1 < len(path) else length):
            return None
    return address if in_ram(address, length) else None


def decode(entry: Entry, data: bytes) -> Value:
    """The value DATA holds for ENTRY: an int, a float or, for a run of bytes, the bytes."""
    if len(data) != entry.length:
        raise ValueError(f"{entry.name} is {entry.length} bytes, not {len(data)}")
    if entry.type == BYTES:
        return bytes(data)
    return struct.unpack(FORMATS[entry.type], data)[0]


def read(link, name: str, table: Mapping[str, Entry] | None = None) -> Value | None:
    """NAME's value now, read through LINK (bot_link.py's Link), or None when its path meets a
    null pointer. TABLE is the table to look NAME up in, kar_ram.json's by default. An unknown
    NAME is a KeyError."""
    entry = (table if table is not None else _default())[name]
    address = follow(link, entry.address, entry.path, entry.length)
    if address is None:
        return None
    return decode(entry, link.read(address, entry.length))


_loaded: dict[str, Entry] | None = None


def _default() -> dict[str, Entry]:
    global _loaded
    if _loaded is None:
        _loaded = load()
    return _loaded


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"{key} is named twice")
        out[key] = value
    return out


def load(path: str | Path | None = None) -> dict[str, Entry]:
    """The table at PATH, kar_ram.json by default, as Entry records by name. Raises ValueError
    naming the file and the entry for one that's malformed or reaches outside main RAM."""
    path = Path(path) if path is not None else TABLE
    try:
        raw = json.loads(path.read_text(), object_pairs_hook=_unique)
    except ValueError as e:
        raise ValueError(f"{path}: {e}") from None
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: not an object of entries by name")
    table = {}
    for name, fields in raw.items():
        try:
            table[name] = _entry(name, fields)
        except ValueError as e:
            raise ValueError(f"{path}: {name}: {e}") from None
    return table


def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _entry(name: str, fields: object) -> Entry:
    if not NAME.fullmatch(name):
        raise ValueError("a name is lowercase words joined by dots, such as player1.speed")
    if not isinstance(fields, dict):
        raise ValueError("not an object")
    missing = sorted(FIELDS - {"path", "length", "values"} - set(fields))
    if missing:
        raise ValueError(f"no {', no '.join(missing)}")
    unknown = sorted(set(fields) - FIELDS)
    if unknown:
        raise ValueError(f"unknown field {unknown[0]}")
    address = fields["address"]
    if not isinstance(address, str) or not ADDRESS.fullmatch(address):
        raise ValueError(f"address {address!r} isn't 8 uppercase hex digits")
    offsets = fields.get("path", [])
    if (not isinstance(offsets, list) or "path" in fields and not offsets
            or not all(isinstance(o, str) and OFFSET.fullmatch(o) for o in offsets)):
        raise ValueError(f"path {offsets!r} isn't a list of offsets of 1 to 4 uppercase hex digits")
    type_ = fields["type"]
    if type_ == BYTES:
        length = fields.get("length")
        if not _whole(length) or not 1 <= length <= READ_MAX:
            raise ValueError(f"a run of bytes needs a length from 1 to {READ_MAX}, not {length!r}")
    elif type_ in FORMATS:
        if "length" in fields:
            raise ValueError(f"a {type_} has no length")
        length = size(type_)
    else:
        raise ValueError(f"type {type_!r} isn't one of {', '.join([*FORMATS, BYTES])}")
    start = int(address, 16)
    held = POINTER if offsets else length  # what the address itself holds
    if not in_ram(start, held):
        raise ValueError(f"{start:08X} to {start + held - 1:08X} isn't all in main RAM, "
                         f"{RAM_START:08X} to {RAM_END - 1:08X}")
    for text in ("means", "route"):
        if not isinstance(fields[text], str) or not fields[text].strip():
            raise ValueError(f"{text} is empty")
    frames = fields["frames"]
    if (not isinstance(frames, list) or len(frames) != 2 or not all(_whole(f) and f >= 0 for f in frames)
            or frames[0] > frames[1]):
        raise ValueError(f"frames {frames!r} isn't [FIRST, LAST], two frame numbers in order")
    values = fields.get("values", {})
    if not isinstance(values, dict):
        raise ValueError("values isn't an object of value to meaning")
    meanings = {}
    for key, meaning in values.items():
        if type_ in (BYTES, "f32") or not VALUE.fullmatch(key):
            raise ValueError(f"value {key!r} isn't a whole number a {type_} holds")
        number = int(key)
        low, high = _range(type_)
        if not low <= number <= high or not isinstance(meaning, str) or not meaning.strip():
            raise ValueError(f"value {key} needs a meaning and has to fit a {type_}")
        meanings[number] = meaning
    return Entry(name, start, type_, length, fields["means"], meanings, fields["route"],
                 (frames[0], frames[1]), tuple(int(o, 16) for o in offsets))


def _range(type_: str) -> tuple[int, int]:
    bits = 8 * size(type_)
    if type_.startswith("s"):
        return -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return 0, (1 << bits) - 1
