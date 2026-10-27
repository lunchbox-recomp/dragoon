"""How does a build copy a file without copying its bytes?

clone() makes DST an APFS clone of SRC through clonefile(2). The two share their blocks until
one of them changes, so a build's copy of a mod costs almost no disk, and editing the original
afterwards leaves the copy as it was. Where the volume can't clone, or the call fails for any
other reason, the bytes are copied instead. It has no command line.
"""
from __future__ import annotations

import ctypes
import os
import shutil
from pathlib import Path
from typing import Callable, Optional

CLONE_NOFOLLOW = 0x0001  # sys/clonefile.h: a link is cloned as a link, never followed
CHUNK = 1 << 20


def _clonefile() -> Optional[Callable[[bytes, bytes, int], int]]:
    """libc's clonefile, or None on a system that has none."""
    try:
        fn = ctypes.CDLL(None, use_errno=True).clonefile
    except (AttributeError, OSError):
        return None
    fn.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32)
    fn.restype = ctypes.c_int
    return fn


CLONEFILE = _clonefile()


def clone(src: Path, dst: Path) -> bool:
    """Make DST, which mustn't exist yet, hold SRC's bytes. True when DST is a clone and False
    when the bytes were copied. A DST that exists is a FileExistsError and stays as it was.
    Neither way follows a link: a clone of one is a link, and a copy of one is an OSError."""
    if CLONEFILE is not None and CLONEFILE(os.fsencode(src), os.fsencode(dst), CLONE_NOFOLLOW) == 0:
        return True
    with open(os.open(src, os.O_RDONLY | os.O_NOFOLLOW), "rb") as f, open(dst, "xb") as g:
        shutil.copyfileobj(f, g, CHUNK)
    return False
