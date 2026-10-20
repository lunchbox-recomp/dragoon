#!/usr/bin/env python3
"""Read the engine's shader cache and key list files: what is cached, and what is new.

Usage: shader_cache.py count FILE
       shader_cache.py diff OLD NEW

count prints the file's version, key size, record count, distinct key count and the
trailing bytes it ignored. diff prints how many distinct keys in NEW are not in OLD, and
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
  bytes short of a whole key are ignored, as in tools/shader_keys.cpp.

Keys are compared as raw bytes, with no canonicalization of the tool's own. A key is made
canonical when it is built (shadergen.cpp:58), so every file in the current format holds
canonical keys. The loader canonicalizes again (render_gl.cpp:684) only to fix older caches,
which the format check refuses anyway.
"""
from __future__ import annotations

import argparse
import struct
import sys
from dataclasses import dataclass

CACHE_MAGIC = 0x43535257  # "WRSC"
LIST_MAGIC = 0x4B534347  # "GCSK"
CACHE_HEADER = 16
LIST_HEADER = 8
RECORD_TAIL = 16  # u64 src_hash, u32 binary format, u32 length


class FormatError(Exception):
    pass


@dataclass
class Keys:
    magic: int
    format_word: int
    keys: list[bytes]
    ignored: int

    @property
    def version(self) -> int:
        return self.format_word >> 16

    @property
    def key_size(self) -> int:
        return self.format_word & 0xFFFF


def load(path: str) -> Keys:
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 8:
        raise FormatError(f"{path}: {len(data)} bytes, too short for a header")
    magic, word = struct.unpack_from("<II", data)
    if magic not in (CACHE_MAGIC, LIST_MAGIC):
        raise FormatError(f"{path}: unknown magic {magic:08x}, expected {CACHE_MAGIC:08x} (cache) "
                          f"or {LIST_MAGIC:08x} (key list)")
    size = word & 0xFFFF
    if size == 0:
        raise FormatError(f"{path}: format word {word:08x} has key size 0")
    keys: list[bytes] = []
    if magic == LIST_MAGIC:
        o = LIST_HEADER
        while o + size <= len(data):
            keys.append(data[o:o + size])
            o += size
        return Keys(magic, word, keys, len(data) - o)
    if len(data) < CACHE_HEADER:
        raise FormatError(f"{path}: {len(data)} bytes, too short for a cache header")
    o = CACHE_HEADER
    while o + size + RECORD_TAIL <= len(data):
        (length,) = struct.unpack_from("<I", data, o + size + 12)
        nxt = o + size + RECORD_TAIL + length
        if nxt > len(data):
            break
        keys.append(data[o:o + size])
        o = nxt
    return Keys(magic, word, keys, len(data) - o)


def read_keys(path: str) -> list[bytes]:
    """Each record's key as raw bytes, in file order (repeats kept)."""
    return load(path).keys


def count(path: str) -> int:
    k = load(path)
    kind = "shader cache" if k.magic == CACHE_MAGIC else "key list"
    print(f"{path}: {kind}  version {k.version}  key size {k.key_size}  records {len(k.keys)}"
          f"  distinct {len(set(k.keys))}  ignored {k.ignored} trailing bytes")
    return 0


def diff(old_path: str, new_path: str) -> int:
    old, new = load(old_path), load(new_path)
    if old.format_word != new.format_word:
        raise FormatError(f"format words differ: {old_path} is {old.format_word:08x}, "
                          f"{new_path} is {new.format_word:08x}")
    have = set(old.keys)
    distinct = set(new.keys)
    added = distinct - have
    share = 100 * len(added) / len(distinct) if distinct else 0.0
    print(f"{len(added)} of {len(distinct)} keys in NEW are not in OLD ({share:.1f}%)")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Read shader cache and key list files.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("count").add_argument("file")
    d = sub.add_parser("diff")
    d.add_argument("old")
    d.add_argument("new")
    args = ap.parse_args(argv)
    try:
        return count(args.file) if args.cmd == "count" else diff(args.old, args.new)
    except FormatError as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
