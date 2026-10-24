"""How check_bundle.py reads Mach-O files and ar archives: their magic numbers, a fat file's
slices, an archive's members and the symbols nm lists.

nm reads every object in an archive and skips a member that isn't one without a word, so an
archive's members are read here first. A member other than the symbol table (__.SYMDEF*) that
isn't a thin Mach-O makes the archive unreadable.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import BinaryIO

AR_MAGIC = b"!<arch>\n"
THIN_MAGICS = frozenset(bytes.fromhex(h) for h in ("feedface", "cefaedfe", "feedfacf", "cffaedfe"))
# A fat header and the size of each slice's entry after it, all big-endian.
FAT_ENTRY = {bytes.fromhex("cafebabe"): 20, bytes.fromhex("cafebabf"): 32}
# The thin and fat headers in both byte orders.
MACHO_MAGICS = THIN_MAGICS | frozenset(FAT_ENTRY) | frozenset(bytes.fromhex(h) for h in ("bebafeca", "bfbafeca"))
# A 64-bit little-endian Mach-O whose filetype, at byte 12, is MH_OBJECT: what `ld -r` writes.
MH_OBJECT_64 = (bytes.fromhex("cffaedfe"), (1).to_bytes(4, "little"))
MAX_SLICES = 64
MEMBER_HEADER = 60
SYMDEF = "__.SYMDEF"
NM = "/usr/bin/nm"


def is_thin_object(head: bytes) -> bool:
    """Does HEAD start a thin 64-bit Mach-O object?"""
    return head[:4] == MH_OBJECT_64[0] and head[12:16] == MH_OBJECT_64[1]


def archives(f: BinaryIO, head: bytes) -> list[tuple[int, int]]:
    """(offset, size) of each ar archive in the open file F, which starts with HEAD: the whole
    file when it is one, or each slice of a fat file that is one. Raises ValueError when a fat
    header doesn't fit the file."""
    if head.startswith(AR_MAGIC):
        return [(0, os.fstat(f.fileno()).st_size)]
    entry = FAT_ENTRY.get(head[:4])
    if entry is None:
        return []
    count = int.from_bytes(head[4:8], "big")
    f.seek(8)
    table = f.read(count * entry) if count <= MAX_SLICES else b""
    if count > MAX_SLICES or len(table) != count * entry:
        raise ValueError("its fat header doesn't fit the file")
    width = 4 if entry == 20 else 8
    found = []
    for at in range(0, len(table), entry):
        offset = int.from_bytes(table[at + 8:at + 8 + width], "big")
        size = int.from_bytes(table[at + 8 + width:at + 8 + 2 * width], "big")
        f.seek(offset)
        if f.read(len(AR_MAGIC)) == AR_MAGIC:
            found.append((offset, size))
    return found


def is_archive(path: Path, head: bytes) -> bool:
    """Is the file at PATH, which starts with HEAD, an ar archive or a fat file holding one? A
    fat header that doesn't fit counts as no, and defined_symbols refuses that file."""
    try:
        with open(path, "rb") as f:
            return bool(archives(f, head))
    except ValueError:
        return False


def check_members(f: BinaryIO, offset: int, size: int) -> None:
    """Raise ValueError unless every member of the ar archive at OFFSET in F, SIZE bytes long,
    is a thin Mach-O or a symbol table."""
    at, end = offset + len(AR_MAGIC), offset + size
    while at < end:
        f.seek(at)
        header = f.read(MEMBER_HEADER)
        name = header[:16].decode("ascii", "replace").rstrip()
        length = header[48:58].strip()
        if len(header) != MEMBER_HEADER or header[58:] != b"`\n" or not length.isdigit():
            raise ValueError(f"its member header at byte {at - offset} can't be read")
        data, length = at + MEMBER_HEADER, int(length)
        if name.startswith("#1/") and name[3:].isdigit() and int(name[3:]) <= length:
            # BSD ar: the name's length is in the header and the name opens the member's data.
            skip = int(name[3:])
            name = f.read(skip).rstrip(b"\0").decode("utf-8", "replace")
            data, length = data + skip, length - skip
        if data + length > end:
            raise ValueError(f"its member {name} runs past its end")
        if not name.startswith(SYMDEF):
            f.seek(data)
            if f.read(4) not in THIN_MAGICS:
                raise ValueError(f"its member {name} isn't Mach-O")
        at = data + length
        at += (at - offset) % 2


def defined_symbols(path: Path, head: bytes) -> list[str]:
    """The symbols the Mach-O file or archive at PATH, starting with HEAD, defines in any of its
    architectures, local ones included. Raises ValueError when it can't be read whole."""
    with open(path, "rb") as f:
        for offset, size in archives(f, head):
            check_members(f, offset, size)
    done = subprocess.run([NM, "--defined-only", "-j", "-arch", "all", str(path)], capture_output=True)
    if done.returncode != 0:
        raise ValueError(f"nm exited {done.returncode}")
    # Between the symbols are blank lines and a "lib.a(member.o):" line per member, with the
    # architecture after it for a fat file.
    return done.stdout.decode(errors="replace").splitlines()
