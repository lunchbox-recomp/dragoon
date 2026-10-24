"""Helpers the tools' tests share."""
from __future__ import annotations

import contextlib
import io
import math
import os
import subprocess
import sys
import wave
from array import array
from pathlib import Path
from typing import Callable

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


def run_main(main: Callable[[list[str]], int], *argv: str) -> tuple[int, str, str]:
    """Run a tool's main with its output captured: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


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
