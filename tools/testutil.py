"""Helpers the tools' tests share."""
from __future__ import annotations

import contextlib
import io
import math
import os
import random
import signal
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from array import array
from pathlib import Path
from types import FrameType
from typing import Callable, Optional

# Fixture repositories ignore the user's and the system's git config, so no signing, hook
# or filter of theirs runs, and commit as a fixed name.
GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


class FakeLink:
    """A bot_link.Link over made-up guest RAM: the bytes put at addresses, zero elsewhere. `reads`
    lists each (address, length) asked for, and `set` puts a kar_ram.json entry's value where the
    table says it lives (one without a path)."""

    def __init__(self, frame: int = 0, starts: int = 1) -> None:
        self.frame = frame
        self.starts = starts
        self.bytes: dict[int, int] = {}
        self.reads: list[tuple[int, int]] = []

    def put(self, address: int, data: bytes) -> None:
        for i, b in enumerate(data):
            self.bytes[address + i] = b

    _table: dict | None = None

    def set(self, name: str, value: int | float) -> None:
        import kar_ram
        if FakeLink._table is None:
            FakeLink._table = kar_ram.load()
        entry = FakeLink._table[name]
        assert not entry.path, name
        self.put(entry.address, struct.pack(kar_ram.FORMATS[entry.type], value))

    def read(self, address: int, length: int) -> bytes:
        assert 1 <= length <= 256 and 0x80000000 <= address and address + length <= 0x81800000, (hex(address), length)
        self.reads.append((address, length))
        return bytes(self.bytes.get(address + i, 0) for i in range(length))


# The wall seconds a test that starts a probe.sh run may take. The slowest takes about 3.
RUN_LIMIT = 120.0


class TimeLimit(BaseException):
    """A test ran past its time limit. It isn't an Exception, so code under test that takes an
    Exception for its own, as bot_link.run does a bot's, lets it through."""


def time_limit(test: unittest.TestCase, seconds: float) -> None:
    """Raises TimeLimit in TEST wherever it waits, once it has run SECONDS of wall time and again
    each SECONDS after that, so a cleanup that waits too can't hold it. A cleanup ends the limit,
    and since cleanups run last first, the ones TEST adds later run under it. TEST can't use
    SIGALRM or the real-time interval timer while it holds them."""
    def expired(signum: int, frame: Optional[FrameType]) -> None:
        raise TimeLimit(f"{test.id()} ran past its {seconds:g} s limit")

    before = signal.signal(signal.SIGALRM, expired)

    def end() -> None:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, before)

    test.addCleanup(end)
    signal.setitimer(signal.ITIMER_REAL, seconds, seconds)


def run_main(main: Callable[[list[str]], int], *argv: str) -> tuple[int, str, str]:
    """Run a tool's main with its output captured: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


def temp_dir(test: unittest.TestCase, prefix: str | None = None) -> Path:
    """A new temporary directory, removed when TEST ends."""
    tmp = tempfile.TemporaryDirectory(prefix=prefix)
    test.addCleanup(tmp.cleanup)
    return Path(tmp.name)


def write_file(directory: Path, name: str, data: bytes | str) -> Path:
    path = Path(directory, name)
    if isinstance(data, str):
        path.write_text(data)
    else:
        path.write_bytes(data)
    return path


def compile_c(source: str, out: Path, debug: bool = True, arch: str = "arm64") -> Path:
    """OUT, an object for ARCH the system's cc compiles from SOURCE, with debug info if DEBUG."""
    out.parent.mkdir(parents=True, exist_ok=True)
    src = write_file(out.parent, out.name + ".c", source)
    subprocess.run(["/usr/bin/cc", "-arch", arch, *(["-g"] if debug else []), "-O2", "-c", str(src),
                    "-o", str(out)], check=True)
    src.unlink()
    return out


def archive(out: Path, *objects: Path) -> Path:
    """OUT, a static library of OBJECTS made by the system's ar."""
    subprocess.run(["/usr/bin/ar", "rcs", str(out), *map(str, objects)], check=True)
    return out


def tone(n: int, rate: int, freq: float = 440, amp: float = 20000) -> list[int]:
    """N samples of a sine at RATE Hz."""
    return [round(amp * math.sin(2 * math.pi * freq * i / rate)) for i in range(n)]


def noise(n: int, amp: int, seed: int) -> list[int]:
    """N samples of white noise between -AMP and AMP."""
    r = random.Random(seed)
    return [r.randint(-amp, amp) for _ in range(n)]


def spliced(x: list[int], *cuts: int, skip: int = 37) -> list[int]:
    """X with SKIP samples thrown away at each index in CUTS (indices into the result)."""
    out = list(x)
    for at in cuts:
        out = out[:at] + out[at + skip:]
    return out


def pcm(left: list[int], right: list[int]) -> bytes:
    """Two channels as raw 16-bit little-endian stereo, the way GCN_AIDWAV writes them."""
    data = array("h", [v for f in zip(left, right) for v in f])
    if sys.byteorder == "big":
        data.byteswap()
    return data.tobytes()


def write_wav(path: Path, left: list[int], right: list[int], rate: int = 48000) -> Path:
    """Two channels as a 16-bit stereo WAV, the way GCN_WAV writes them."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm(left, right))
    return path


# A stand-in for hdiutil that mounts nothing real. "attach" copies <dmg>.contents into the
# -mountpoint and "detach" empties it, and each call's arguments go to the records file. A file
# named "attach fails" beside the script makes attach fail, "busy" makes detach fail until it's
# given -force and "detach fails" makes it fail always. "attach hangs" makes attach and
# "detach hangs" makes a detach without -force run for a minute, which a timeout cuts short, and
# "force hangs" does the same to a detach with -force.
FAKE_HDIUTIL = r"""#!@PYTHON@
import json, os, shutil, sys, time
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
with open(@RECORDS@, "a") as f:
    f.write(json.dumps(args) + "\n")
if args[0] == "attach":
    if os.path.exists(os.path.join(here, "attach hangs")):
        time.sleep(60)
    if os.path.exists(os.path.join(here, "attach fails")):
        print("hdiutil: attach failed - Resource temporarily unavailable", file=sys.stderr)
        sys.exit(1)
    mount = args[args.index("-mountpoint") + 1]
    assert os.path.isdir(mount) and not os.listdir(mount), mount
    shutil.copytree(args[-1] + ".contents", mount, symlinks=True, dirs_exist_ok=True)
elif args[0] == "detach":
    if os.path.exists(os.path.join(here, "detach hangs")) and "-force" not in args:
        time.sleep(60)
    if os.path.exists(os.path.join(here, "force hangs")) and "-force" in args:
        time.sleep(60)
    stuck = os.path.exists(os.path.join(here, "busy")) and "-force" not in args
    if stuck or os.path.exists(os.path.join(here, "detach fails")):
        print("hdiutil: couldn't unmount - Resource busy", file=sys.stderr)
        sys.exit(16)
    mount = args[-1]
    for name in os.listdir(mount):
        path = os.path.join(mount, name)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.unlink(path)
"""


def fake_hdiutil(directory: Path, records: Path) -> Path:
    """Write the FAKE_HDIUTIL script into DIRECTORY, recording each call as a JSON line in
    RECORDS."""
    text = FAKE_HDIUTIL.replace("@PYTHON@", sys.executable).replace("@RECORDS@", repr(str(records)))
    path = write_file(directory, "hdiutil", text)
    path.chmod(0o755)
    return path


def git(repo: Path, *args: str) -> str:
    """Run git in REPO under GIT_ENV and return its output, stripped."""
    done = subprocess.run(["git", "-C", str(repo), *args], env={**os.environ, **GIT_ENV},
                          capture_output=True, text=True, check=True)
    return done.stdout.strip()


def commit(repo: Path, files: dict[str, bytes | str]) -> str:
    """Write FILES (relative path: contents) into REPO, making it a repository first if it
    isn't one, commit them with anything already staged and return the commit."""
    if not (repo / ".git").exists():
        repo.mkdir(parents=True, exist_ok=True)
        git(repo, "init", "-q", "-b", "main")
    for name, data in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        write_file(path.parent, path.name, data)
    git(repo, "add", "--", *files)
    git(repo, "commit", "-q", "-m", "commit")
    return git(repo, "rev-parse", "HEAD")
