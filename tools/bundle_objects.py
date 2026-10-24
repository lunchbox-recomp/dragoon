"""How check_bundle.py reads Mach-O files and ar archives: their magic numbers, a fat file's
slices, an archive's members and the symbols nm lists.

nm reads every object in an archive and skips a member that isn't one without a word, so an
archive's members are read here first. The symbol table may open an archive, under one of its
four names. Every other member has to be a thin Mach-O that ends where the string table its
LC_SYMTAB names ends, as clang and ld end one, padded to 8 bytes with newlines as ar and strip
pad one. Anything else makes the archive unreadable.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import BinaryIO

AR_MAGIC = b"!<arch>\n"
# The 32-bit and 64-bit headers as a big-endian and a little-endian file starts.
BIG_ENDIAN = frozenset(bytes.fromhex(h) for h in ("feedface", "feedfacf"))
LITTLE_ENDIAN = frozenset(bytes.fromhex(h) for h in ("cefaedfe", "cffaedfe"))
THIN_MAGICS = BIG_ENDIAN | LITTLE_ENDIAN
HEADER_32 = frozenset(bytes.fromhex(h) for h in ("feedface", "cefaedfe"))
# A fat header and the size of each slice's entry after it, all big-endian.
FAT_ENTRY = {bytes.fromhex("cafebabe"): 20, bytes.fromhex("cafebabf"): 32}
# The thin and fat headers in both byte orders.
MACHO_MAGICS = THIN_MAGICS | frozenset(FAT_ENTRY) | frozenset(bytes.fromhex(h) for h in ("bebafeca", "bfbafeca"))
# A 64-bit little-endian Mach-O whose filetype, at byte 12, is MH_OBJECT: what `ld -r` writes.
MH_OBJECT_64 = (bytes.fromhex("cffaedfe"), (1).to_bytes(4, "little"))
LC_SYMTAB = 2
MAX_SLICES = 64
MEMBER_HEADER = 60
MEMBER_ALIGN = 8
SYMDEF_NAMES = frozenset(("__.SYMDEF", "__.SYMDEF SORTED", "__.SYMDEF_64", "__.SYMDEF_64 SORTED"))
NM = "/usr/bin/nm"


def is_thin_object(head: bytes) -> bool:
    """Does HEAD start a thin 64-bit Mach-O object?"""
    return head[:4] == MH_OBJECT_64[0] and head[12:16] == MH_OBJECT_64[1]


def macho_end(f: BinaryIO, start: int, limit: int) -> int:
    """Where the thin Mach-O at START in F, LIMIT bytes long at most, ends: at the end of the
    string table its LC_SYMTAB names, counted from START. Raises ValueError, saying what it is,
    when it isn't a thin Mach-O or its load commands don't say."""
    f.seek(start)
    head = f.read(32)
    magic = head[:4]
    if magic not in THIN_MAGICS:
        raise ValueError("isn't Mach-O")
    order = "big" if magic in BIG_ENDIAN else "little"
    header = 28 if magic in HEADER_32 else 32
    ncmds, sizeofcmds = (int.from_bytes(head[at:at + 4], order) for at in (16, 20))
    if len(head) < header or header + sizeofcmds > limit:
        raise ValueError("has load commands that don't fit it")
    f.seek(start + header)
    commands = f.read(sizeofcmds)
    at = 0
    for _ in range(ncmds):
        cmd, size = (int.from_bytes(commands[at + i:at + i + 4], order) for i in (0, 4))
        if size < 8 or at + size > len(commands):
            raise ValueError("has load commands that don't fit it")
        if cmd == LC_SYMTAB and size >= 24:
            stroff, strsize = (int.from_bytes(commands[at + i:at + i + 4], order) for i in (16, 20))
            return stroff + strsize
        at += size
    raise ValueError("has no symbol table")


def is_lone_object(path: Path, head: bytes) -> bool:
    """Is the file at PATH, which starts with HEAD, a thin 64-bit Mach-O object that ends
    exactly where its string table does, as `ld -r` leaves one?"""
    if not is_thin_object(head):
        return False
    try:
        with open(path, "rb") as f:
            size = os.fstat(f.fileno()).st_size
            return macho_end(f, 0, size) == size
    except ValueError:
        return False


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
    """Raise ValueError unless the ar archive at OFFSET in F, SIZE bytes long, holds a symbol
    table first, if at all, and then thin Mach-O files that each end at their string table."""
    at, end = offset + len(AR_MAGIC), offset + size
    first = True
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
        if not (first and name in SYMDEF_NAMES):
            try:
                stop = macho_end(f, data, length)
            except ValueError as e:
                raise ValueError(f"its member {name} {e}") from None
            f.seek(data + stop)
            pad = length - stop
            if pad < 0 or pad >= MEMBER_ALIGN or f.read(pad) != b"\n" * pad:
                raise ValueError(f"its member {name} doesn't end where its string table does")
        first = False
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
