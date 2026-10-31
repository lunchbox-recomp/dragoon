#!/usr/bin/env python3
"""Drive the game from Python through the engine's bot link (gcn-recomp's docs/diagnostics.md, "Bots").

Usage: bot_link.py [--script ROUTE] [--pads N] [--send N] [--every N] [--watch ADDR:LEN ...]
                   NAME SECONDS [-- SETTING ...]

Runs tools/probe.sh as NAME for SECONDS with a bot that presses nothing on ports 1 to N, and says
how the link ended. ROUTE is probe.sh's INPUT_SCRIPT, whose presses go on top of the bot's, and
every SETTING is one of probe.sh's, such as --exit-after=1500 or GCN_SESSION=DIR. --watch prints
the LEN bytes at ADDR (hex address, decimal length) at every frame they change. --send N makes
the bot send pads for ports 1 to N, which is only different from --pads when you want to see the
engine refuse a port it doesn't drive or one the bot leaves out.

Exits 0 when the game ended by itself (the time limit or --exit-after), 1 when the run ended any
other way, and 2 on a bad argument or when the run could not be started.

As a module, `run` does the same with a bot of your own:

    def bot(link: Link) -> dict[int, Pad]:
        pressed = link.read(0x80000000, 4)
        return {1: Pad(buttons=BUTTONS["START"] if pressed[0] else 0)}

    outcome = run("mine", 60, bot, script="tests/routes/menu.txt", settings=["--exit-after=1500"])

The socket is listened on first and the game started second, with GCN_BOT set to the socket's
absolute path, so the game connects with nothing left to chance. A run is judged by the link's
own end and what the game wrote to build/probe/NAME/, never by probe.sh's exit status, which is
0 whatever the game did. A stdout.txt or panic.txt an earlier run of NAME left is deleted first.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import re
import select
import socket
import stat
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

PROBE = Path(__file__).resolve().parent / "probe.sh"
# A Unix socket's path is 104 bytes with its NUL on macOS, and the engine refuses a longer one.
SOCKET_PATH_MAX = 103
# How much of the end of stdout.txt to look through; a stop, a crash or a failed connect is
# the last thing the game says.
TAIL = 1 << 17

# The PADStatus bits (gcn-recomp's runtime/hw/pad.h).
BUTTONS = {
    "LEFT": 0x0001, "RIGHT": 0x0002, "DOWN": 0x0004, "UP": 0x0008, "Z": 0x0010, "R": 0x0020,
    "L": 0x0040, "A": 0x0100, "B": 0x0200, "X": 0x0400, "Y": 0x0800, "START": 0x1000,
}

# How a run's link ended.
ENGINE_STOP = "engine_stop"        # the engine reported a stop, its `[bot] frame N: ...` line
CONNECT_FAILED = "connect_failed"  # the engine couldn't connect, its `--bot PATH: ...` line
PANIC = "panic"                    # panic.txt, or the engine's FATAL or FAULT line
BOT_RAISED = "bot_raised"          # the bot callback raised
GAME_ENDED = "game_ended"          # the time limit, --exit-after or the game exiting by itself
NEVER_LINKED = "never_linked"      # the game ended without connecting and without saying why
BAD_LINK = "bad_link"              # the engine sent something that isn't the protocol

STOP_LINE = re.compile(r"^\[bot\] frame \d+: .*$", re.M)
CONNECT_LINE = re.compile(r"^--bot .+: .+$", re.M)
CRASH_LINE = re.compile(r"^(?:FATAL|FAULT): .*$", re.M)
FRAME_LINE = re.compile(rb"frame (\d+)\n")
DATA_LINE = re.compile(rb"data ((?:[0-9a-fA-F]{2})*)\n")
EXIT_AFTER = re.compile(r"--exit-after=(\d+)")


@dataclass(frozen=True)
class Pad:
    """One port's state for a frame. `Pad()` is a pad at rest."""
    buttons: int = 0  # PADStatus bits, see BUTTONS
    sx: int = 128  # the sticks and triggers are 0 to 255, with 128 a stick at rest
    sy: int = 128
    cx: int = 128
    cy: int = 128
    l: int = 0
    r: int = 0


@dataclass
class Outcome:
    frames: int  # the frames the bot answered; the last may be one the engine refused
    last_frame: int | None  # the last frame number the engine sent, None if it sent none
    reason: str  # one of the reasons above
    detail: str  # the engine's line, the panic's first line, the exception, or what ended the game
    run_dir: Path  # build/probe/NAME/, where the game's output is
    error: BaseException | None = None  # what the bot callback raised, with its traceback


class LinkSetupError(Exception):
    """The run could not be started: the socket is taken or can't be made, or probe.sh won't run."""


class _Ended(BaseException):
    """The engine closed the link, or sent what isn't the protocol (`bad`). It's not an Exception
    so that a bot's own `except Exception` can't swallow it."""

    def __init__(self, bad: bytes | None = None) -> None:
        super().__init__(bad)
        self.bad = bad


class Link:
    """What a bot sees of the game: the frame it's stepped at, and guest RAM at that frame."""

    def __init__(self) -> None:
        self.frame = -1  # the last frame number the engine sent, -1 before the first
        self.starts = 0  # how many times the game has connected; a console reset connects again
        self._conn: socket.socket | None = None
        self._lines = None

    def read(self, addr: int, length: int) -> bytes:
        """`length` bytes at the guest address `addr` (0x80000000 to 0x817FFFFF, 1 to 256 bytes).
        A read the engine refuses stops the game, and the run ends as an engine stop."""
        self._send(f"read {addr:X} {length}\n".encode())
        line = self._line()
        m = DATA_LINE.fullmatch(line)
        if not m:
            raise _Ended(line)
        return bytes.fromhex(m[1].decode())

    def _attach(self, conn: socket.socket) -> None:
        self._conn = conn
        self._lines = conn.makefile("rb")
        self.starts += 1

    def _detach(self) -> None:
        if self._lines is not None:
            self._lines.close()
        if self._conn is not None:
            self._conn.close()
        self._conn = self._lines = None

    def _send(self, data: bytes) -> None:
        assert self._conn is not None
        try:
            self._conn.sendall(data)
        except OSError:  # the game is gone
            raise _Ended() from None

    def _line(self) -> bytes:
        assert self._lines is not None
        try:
            line = self._lines.readline()
        except OSError:  # a reset
            raise _Ended() from None
        if not line.endswith(b"\n"):  # the end of the stream, or the end partway through a line
            raise _Ended()
        return line


@dataclass
class _State:
    frames: int = 0
    last_frame: int | None = None
    error: BaseException | None = None
    bad_line: bytes | None = None


def encode_pads(pads: Mapping[int, Pad]) -> bytes:
    """The pad lines and `done` that answer a frame. A port the bot leaves out is left out, so
    the engine stops the game and names it, and no neutral pad stands in."""
    if not isinstance(pads, Mapping):
        raise TypeError(f"the bot returned {pads!r}, not a dict of port to Pad")
    lines = []
    for port in sorted(pads):
        p = pads[port]
        if not isinstance(p, Pad):
            raise TypeError(f"the bot's pad for port {port} is {p!r}, not a Pad")
        lines.append(f"pad {port} {p.buttons:04X} {p.sx} {p.sy} {p.cx} {p.cy} {p.l} {p.r}\n")
    return ("".join(lines) + "done\n").encode()


def socket_path(run_dir: Path) -> str:
    """Where the bot listens for a run in `run_dir`: bot.sock there, or when that path is too long
    for a Unix socket, a short one in /tmp named for the directory."""
    path = str(run_dir / "bot.sock")
    if len(os.fsencode(path)) <= SOCKET_PATH_MAX:
        return path
    digest = hashlib.sha1(os.fsencode(run_dir)).hexdigest()[:12]
    return f"/tmp/dragoon-bot-{digest}.sock"


def _listen(path: str) -> tuple[socket.socket, int]:
    """A socket listening at `path`, and the lock on `path`.lock held while it listens, as an
    open file to close once the socket file is gone. When another bot holds the lock, it's an
    OSError and neither file is touched, since two bots on one socket would take each other's
    games. With the lock taken, a socket file at `path` is one an earlier run left, and it's
    replaced; any other kind of file there is an OSError."""
    lock = os.open(path + ".lock", os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise OSError("another bot is listening on it") from None
        try:
            if stat.S_ISSOCK(os.stat(path).st_mode):
                os.unlink(path)
        except FileNotFoundError:
            pass
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(path)
            listener.listen(1)
        except OSError:
            listener.close()
            raise
    except OSError:
        os.close(lock)
        raise
    return listener, lock


def _accept(listener: socket.socket, proc: subprocess.Popen) -> socket.socket | None:
    """The game's next connection, or None once probe.sh has exited without one."""
    while True:
        ready, _, _ = select.select([listener], [], [], 0.2)
        if ready:
            return listener.accept()[0]
        if proc.poll() is not None:
            return None


def _step(link: Link, bot: Callable[[Link], dict[int, Pad]], state: _State) -> None:
    """Answers the engine's frames until it closes the link, the bot raises or the engine sends
    what isn't the protocol."""
    try:
        while True:
            line = link._line()
            m = FRAME_LINE.fullmatch(line)
            if not m:
                raise _Ended(line)
            link.frame = state.last_frame = int(m[1])
            try:
                data = encode_pads(bot(link))
            except Exception as e:
                state.error = e
                return
            link._send(data)
            state.frames += 1
    except _Ended as e:
        state.bad_line = e.bad


def _tail(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - TAIL))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _last(pattern: re.Pattern, text: str) -> str | None:
    found = pattern.findall(text)
    return found[-1] if found else None


def _game_verdict(run_dir: Path, starts: int, probe_err: str, ended_by: str) -> tuple[str, str]:
    """How a run whose link ended without a fault of the bot's ended, from what the game wrote."""
    tail = _tail(run_dir / "stdout.txt")
    line = _last(CONNECT_LINE, tail)
    if line is not None:
        return CONNECT_FAILED, line
    try:
        panic = (run_dir / "panic.txt").read_text(errors="replace")
    except OSError:
        panic = None
    crash = _last(CRASH_LINE, tail)
    if panic is not None or crash is not None:
        first = panic.strip().splitlines()[0] if panic is not None and panic.strip() else None
        return PANIC, first or crash or "panic.txt is empty"
    line = _last(STOP_LINE, tail)
    if line is not None:
        return ENGINE_STOP, line
    if starts == 0:
        said = probe_err.strip() or (tail.strip().splitlines() or [""])[-1]
        return NEVER_LINKED, said or "the game ended before it connected"
    return GAME_ENDED, ended_by


def run(name: str, seconds: int, bot: Callable[[Link], dict[int, Pad]], *, pads: int = 1,
        script: str = "", every: int = 60, settings: Sequence[str] = (),
        probe: str | os.PathLike | None = None) -> Outcome:
    """Plays the game as NAME in build/probe/NAME/ for up to `seconds`, calling `bot` once for
    each frame the engine steps it at. `bot` may read RAM through the Link and returns the pad
    for each port it drives, ports 1 to `pads`. `script` is probe.sh's INPUT_SCRIPT, `every`
    its DUMP_EVERY and `settings` more of its settings. `probe` is a probe.sh-compatible
    program for a fake in a test; its run directory is where probe.sh's would be.

    The game connects again after it resets the console, and the bot goes on with it. Raises
    ValueError for an argument probe.sh or the link would refuse, and LinkSetupError when no
    run could be started."""
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", name):
        raise ValueError(f"{name!r}: not a name for a run's directory")
    if seconds < 1 or every < 1:
        raise ValueError("seconds and every are whole numbers from 1")
    if not 1 <= pads <= 4:
        raise ValueError(f"pads is 1 to 4, not {pads}")
    for s in settings:
        if s.startswith(("GCN_BOT=", "--pads")):
            raise ValueError(f"{s}: run sets GCN_BOT and --pads itself")
    probe_path = Path(os.path.abspath(probe if probe is not None else PROBE))
    if not probe_path.is_file():
        raise LinkSetupError(f"no {probe_path}")
    run_dir = probe_path.parent.parent / "build" / "probe" / name  # as probe.sh finds it
    run_dir.mkdir(parents=True, exist_ok=True)
    sock = socket_path(run_dir)
    try:
        listener, lock = _listen(sock)
    except OSError as e:
        raise LinkSetupError(f"can't listen on {sock}: {e}") from None
    link, state, proc = Link(), _State(), None
    started = time.monotonic()
    try:
        for stale in ("stdout.txt", "panic.txt"):
            try:
                (run_dir / stale).unlink()
            except FileNotFoundError:
                pass
        argv = [str(probe_path), name, str(seconds), script, str(every), *settings,
                f"--pads={pads}", f"GCN_BOT={sock}"]
        try:
            proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
        except OSError as e:
            raise LinkSetupError(f"can't run {probe_path}: {e}") from None
        while (conn := _accept(listener, proc)) is not None:
            link._attach(conn)
            try:
                _step(link, bot, state)
            finally:
                link._detach()
            if state.error is not None or state.bad_line is not None:
                break
        _, probe_err = proc.communicate()
    except BaseException:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            proc.communicate()
        raise
    finally:
        listener.close()
        try:
            os.unlink(sock)
        except FileNotFoundError:
            pass
        # Only now, or a bot that took the lock first could have its new socket file removed.
        os.close(lock)
    elapsed = time.monotonic() - started
    if state.error is not None:
        reason, detail = BOT_RAISED, f"{type(state.error).__name__}: {state.error}"
    elif state.bad_line is not None:
        reason, detail = BAD_LINK, f"the engine sent {state.bad_line!r}, not a frame or data line"
    else:
        limit = EXIT_AFTER.search(" ".join(settings))
        if elapsed >= seconds:
            ended_by = f"the time limit, {seconds} s"
        elif limit:
            ended_by = f"--exit-after={limit[1]}"
        else:
            ended_by = "the game exited"
        reason, detail = _game_verdict(run_dir, link.starts, probe_err, ended_by)
    return Outcome(state.frames, state.last_frame, reason, detail, run_dir, state.error)


def _watch_arg(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"([0-9a-fA-F]{1,8}):(\d{1,3})", text)
    if not m:
        raise argparse.ArgumentTypeError(f"ADDR:LEN, ADDR in hex and LEN in decimal, not {text}")
    return int(m[1], 16), int(m[2])


def main(argv: list[str]) -> int:
    settings: list[str] = []
    if "--" in argv:
        split = argv.index("--")
        argv, settings = argv[:split], argv[split + 1:]
    ap = argparse.ArgumentParser(prog="bot_link.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--script", default="", metavar="ROUTE")
    ap.add_argument("--pads", type=int, choices=range(1, 5), default=1, metavar="N")
    ap.add_argument("--send", type=int, choices=range(1, 5), metavar="N")
    ap.add_argument("--every", type=int, default=60, metavar="N")
    ap.add_argument("--watch", type=_watch_arg, action="append", default=[], metavar="ADDR:LEN")
    ap.add_argument("--probe", help=argparse.SUPPRESS)
    ap.add_argument("name")
    ap.add_argument("seconds", type=int)
    args = ap.parse_args(argv)
    send = args.send or args.pads
    seen: dict[tuple[int, int], bytes] = {}

    def bot(link: Link) -> dict[int, Pad]:
        for addr, length in args.watch:
            data = link.read(addr, length)
            if seen.get((addr, length)) != data:
                seen[(addr, length)] = data
                print(f"frame {link.frame} {addr:08X} {data.hex()}", flush=True)
        return {port: Pad() for port in range(1, send + 1)}

    try:
        outcome = run(args.name, args.seconds, bot, pads=args.pads, script=args.script,
                      every=args.every, settings=settings, probe=args.probe)
    except (ValueError, LinkSetupError) as e:
        print(f"bot_link.py: {e}", file=sys.stderr)
        return 2
    last = "no frame" if outcome.last_frame is None else f"the last frame {outcome.last_frame}"
    print(f"{outcome.run_dir}: {outcome.reason}, {outcome.frames} frames answered, {last}")
    print(f"  {outcome.detail}")
    return 0 if outcome.reason == GAME_ENDED else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
