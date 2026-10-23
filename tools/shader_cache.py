#!/usr/bin/env python3
"""How many shaders does a cache or key list hold, and how many are new?

Usage: shader_cache.py count FILE
       shader_cache.py diff OLD NEW

count prints the file's version, key size, record count, distinct key count, a cache's
distinct program count (its distinct src_hash values) and the trailing bytes it ignored. diff prints how many distinct keys in NEW are not in OLD, and
their share of NEW's distinct keys; the two files must have the same format word.
Little-endian throughout. Both files open with u32 magic and u32 format word, where
format = kShaderKeyVersion << 16 | sizeof(ShaderKey) (gcn-recomp/runtime/gx/shadergen.h:70).
The key size is the low 16 bits. Any version is read; an unknown magic or a key size of 0
is refused with what was found.

Shader cache, saves/shaders.bin (magic "WRSC" 0x43535257, render_gl.cpp:424):
  header, 16 bytes: magic, format word, u64 driver id        (shader_cache_write_header,
                                                              render_gl.cpp:473-479)
  per record: key (key size bytes), u64 src_hash, u32 binary format, u32 length, then
  `length` bytes of binary                                    (shader_cache_write_record,
                                                              render_gl.cpp:446-471)
  A record cut off at the end (the game appends, and a kill can cut it) is skipped, as
  the loader's cache_next (render_gl.cpp:624-636) does; count reports the bytes ignored.

Key list (magic "GCSK" 0x4B534347, shadergen.h:72):
  header, 8 bytes: magic, format word, then the keys back to back, each once. Leftover
  bytes short of a whole key are ignored, as in gcn-recomp/tools/shader_keys.cpp.

Keys are compared as raw bytes, with no canonicalization of the tool's own. A key is made
canonical when it is built (shadergen.cpp:58), so every file in the current format holds
canonical keys. The loader canonicalizes again (render_gl.cpp:684) only to fix older caches.
The engine refuses older caches at load (render_gl.cpp:660); this tool still reads them.

Exits 0 once it has read the files, 2 on a bad argument or a file it can't read or doesn't
understand.
"""
from __future__ import annotations

import argparse
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

CACHE_MAGIC = 0x43535257  # "WRSC"
LIST_MAGIC = 0x4B534347  # "GCSK"
# Per format: header size, then the bytes after each key (u64 src_hash, u32 binary format,
# u32 length) before the binary. A key list has none.
LAYOUT = {CACHE_MAGIC: (16, 16), LIST_MAGIC: (8, 0)}


@dataclass
class KeyFile:
    magic: int
    format_word: int
    keys: list[bytes]
    ignored: int
    header: bytes = b""
    records: list[bytes] = field(default_factory=list)  # each whole record, a cache's only
    hashes: list[int] = field(default_factory=list)  # each record's src_hash, a cache's only

    @property
    def version(self) -> int:
        return self.format_word >> 16

    @property
    def key_size(self) -> int:
        return self.format_word & 0xFFFF

    @property
    def programs(self) -> int:
        """Distinct generated sources, which is what the driver compiles."""
        return len(set(self.hashes))


def load(path: Path) -> KeyFile:
    data = path.read_bytes()
    magic = int.from_bytes(data[:4], "little")
    if magic not in LAYOUT:
        raise ValueError(f"{path}: unknown magic {magic:08x}, expected {CACHE_MAGIC:08x} (cache) "
                         f"or {LIST_MAGIC:08x} (key list)")
    header, tail = LAYOUT[magic]
    if len(data) < header:
        raise ValueError(f"{path}: {len(data)} bytes, too short for a header")
    word = int.from_bytes(data[4:8], "little")
    size = word & 0xFFFF
    if size == 0:
        raise ValueError(f"{path}: format word {word:08x} has key size 0")
    keys: list[bytes] = []
    records: list[bytes] = []
    hashes: list[int] = []
    o = header
    while o + size + tail <= len(data):
        nxt = o + size + tail
        if tail:
            nxt += struct.unpack_from("<I", data, o + size + 12)[0]
        if nxt > len(data):
            break
        keys.append(data[o:o + size])
        if tail:
            records.append(data[o:nxt])
            hashes.append(struct.unpack_from("<Q", data, o + size)[0])
        o = nxt
    return KeyFile(magic, word, keys, len(data) - o, data[:header], records, hashes)


def merge(files: list[KeyFile]) -> bytes:
    """A cache holding every key of FILES: the first one's header, then each record whose key
    nothing before it held, in file order.

    The header names the format and the driver whose binaries the records carry, so caches
    whose headers differ are refused rather than mixed.
    """
    if not files or any(f.magic != CACHE_MAGIC for f in files):
        raise ValueError("only shader caches can be merged, and at least one")
    if any(f.header != files[0].header for f in files):
        raise ValueError("the caches' headers differ (another format or driver)")
    seen: set[bytes] = set()
    out = [files[0].header]
    for f in files:
        for k, r in zip(f.keys, f.records):
            if k not in seen:
                seen.add(k)
                out.append(r)
    return b"".join(out)


def count(path: Path) -> None:
    k = load(path)
    kind = "shader cache" if k.magic == CACHE_MAGIC else "key list"
    programs = f"  programs {k.programs}" if k.hashes else ""
    print(f"{path}: {kind}  version {k.version}  key size {k.key_size}  records {len(k.keys)}"
          f"  distinct {len(set(k.keys))}{programs}  ignored {k.ignored} trailing bytes")


def diff(old_path: Path, new_path: Path) -> None:
    old, new = load(old_path), load(new_path)
    if old.format_word != new.format_word:
        raise ValueError(f"format words differ: {old_path} is {old.format_word:08x}, "
                         f"{new_path} is {new.format_word:08x}")
    old_keys = set(old.keys)
    new_keys = set(new.keys)
    added = new_keys - old_keys
    share = 100 * len(added) / len(new_keys) if new_keys else 0.0
    print(f"{len(added)} of {len(new_keys)} keys in NEW are not in OLD ({share:.1f}%)")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("count", help="records and distinct keys in one file")
    c.add_argument("file", type=Path)
    d = sub.add_parser("diff", help="keys in NEW that OLD lacks")
    d.add_argument("old", type=Path)
    d.add_argument("new", type=Path)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "count":
            count(args.file)
        else:
            diff(args.old, args.new)
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
