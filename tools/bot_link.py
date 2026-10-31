#!/usr/bin/env python3
"""Drive the game from Python through the engine's bot link (gcn-recomp's docs/diagnostics.md, "Bots").

Usage: bot_link.py [--script ROUTE] [--pads N] [--send N] [--every N] [--hang SECONDS]
                   [--watch ADDR:LEN ...] NAME SECONDS [-- SETTING ...]

Runs tools/probe.sh as NAME for SECONDS with a bot that presses nothing on ports 1 to N, and says
how the link ended. ROUTE is probe.sh's INPUT_SCRIPT, whose presses go on top of the bot's, and
every SETTING is one of probe.sh's, such as --exit-after=1500 or GCN_SESSION=DIR. --watch prints
the LEN bytes at ADDR (hex address, decimal length) at every frame they change. --send N makes
the bot send pads for ports 1 to N, which is only different from --pads when you want to see the
engine refuse a port it doesn't drive or one the bot leaves out. --hang stops the run when the
game sends no frame for SECONDS (30 by default, 0 for never).

The run is a session (GCN_SESSION) that keeps an input log, which replays with no bot, and
records no audio. The result names the log. Exits 0 when the run ended as a bot run is meant to
(time_limit, exit_after and shutdown), 1 when it ended any other way (a stop, a crash, a hang,
a game that died or exited, a bot that raised) and 2 on a bad argument or when the game never
connected, which includes not connecting before the time limit.

As a module, `run` does the same with a bot of your own:

    def bot(link: Link) -> dict[int, Pad]:
        pressed = link.read(0x80000000, 4)
        return {1: Pad(buttons=BUTTONS["START"] if pressed[0] else 0)}

    outcome = run("mine", 60, bot, script="tests/routes/menu.txt", settings=["--exit-after=1500"])

The socket is listened on first and the game started second, with GCN_BOT set to the socket's
absolute path, so the game connects with nothing left to chance. `run` owns the deadline: it
gives probe.sh a few seconds more than SECONDS and ends the game itself at SECONDS. A run is
judged by the link's own end, what the game wrote to build/probe/NAME/ and its input log, never
by probe.sh's exit status, which is 0 whatever the game did. A stdout.txt, a panic.txt or a
session an earlier run of NAME left is deleted first.
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

import session_log
from probe_dirs import remove_run

PROBE = Path(__file__).resolve().parent / "probe.sh"
# A Unix socket's path is 104 bytes with its NUL on macOS, and the engine refuses a longer one.
SOCKET_PATH_MAX = 103
# How many seconds more than the run's own deadline probe.sh is given, so the deadline is the
# run's and probe.sh's own kill is only there if the run is gone.
DEADLINE_SLACK = 5
# How long to wait for a game that was sent SIGTERM to exit and close the link.
CLOSE_WAIT = 10
# How much of the end of a log to look through; a stop, a crash or a failed connect is the last
# thing the game says, and `# end` is the last line of an input log.
TAIL = 1 << 17
LOG_TAIL = 1 << 12
# The PADStatus button bits that are buttons (gcn-recomp's runtime/hw/pad.h), as the engine takes them.
BUTTON_MASK = 0x1F7F

BUTTONS = {
    "LEFT": 0x0001, "RIGHT": 0x0002, "DOWN": 0x0004, "UP": 0x0008, "Z": 0x0010, "R": 0x0020,
    "L": 0x0040, "A": 0x0100, "B": 0x0200, "X": 0x0400, "Y": 0x0800, "START": 0x1000,
}

# How a run's link ended. The first three are the run ending as a bot run is meant to.
TIME_LIMIT = "time_limit"          # the run's SECONDS were up
EXIT_AFTER = "exit_after"          # --exit-after frames were shown
SHUTDOWN = "shutdown"              # the game shut the console down by itself
GAME_EXITED = "game_exited"        # the game ended some other way that left its input log whole
GAME_DIED = "game_died"            # the game ended with no `# end` in its input log
HANG = "hang"                      # no frame for `hang` seconds
ENGINE_STOP = "engine_stop"        # the engine reported a stop, its `[bot] frame N: ...` line
CONNECT_FAILED = "connect_failed"  # the engine couldn't connect, its `--bot PATH: ...` line
PANIC = "panic"                    # panic.txt, or the engine's FATAL or FAULT line
BOT_RAISED = "bot_raised"          # the bot callback raised
NEVER_LINKED = "never_linked"      # the game ended without connecting and without saying why
BAD_LINK = "bad_link"              # the engine sent something that isn't the protocol
# The reasons of a run that ended as a bot run is meant to.
CLEAN = (TIME_LIMIT, EXIT_AFTER, SHUTDOWN)

STOP_LINE = re.compile(r"^\[bot\] frame \d+: .*$", re.M)
CONNECT_LINE = re.compile(r"^--bot .+: .+$", re.M)
END_LINE = re.compile(r"^# end (\d+) (\d+)$", re.M)
FRAME_LINE = re.compile(rb"frame (\d+)\n")
DATA_LINE = re.compile(rb"data ((?:[0-9a-fA-F]{2})*)\n")
EXIT_AFTER_ARG = re.compile(r"--exit-after=(\d+)")


@dataclass(frozen=True)
class Pad:
    """One port's state for a frame. `Pad()` is a pad at rest. A value the engine would refuse
    is a ValueError here, so a bot that computes one raises."""
    buttons: int = 0  # PADStatus bits, see BUTTONS
    sx: int = 128  # the sticks and triggers are 0 to 255, with 128 a stick at rest
    sy: int = 128
    cx: int = 128
    cy: int = 128
    l: int = 0
    r: int = 0

    def __post_init__(self) -> None:
        for name in ("sx", "sy", "cx", "cy", "l", "r"):
            value = getattr(self, name)
            if not isinstance(value, int) or not 0 <= value <= 255:
                raise ValueError(f"Pad.{name} is a whole number from 0 to 255, not {value!r}")
        if not isinstance(self.buttons, int) or self.buttons & ~BUTTON_MASK:  # a negative one has high bits set
            raise ValueError(f"Pad.buttons is PADStatus bits within {BUTTON_MASK:04X}, not {self.buttons!r}")


@dataclass
class Outcome:
    frames: int  # the frames the bot answered; the last may be one the engine refused
    last_frame: int | None  # the last frame number the engine sent, None if it sent none
    reason: str  # one of the reasons above
    detail: str  # the engine's line, the panic's first line, the exception, or what ended the game
    run_dir: Path  # build/probe/NAME/, where the game's output is
    input_log: Path | None = None  # the last process's input log, what probe.sh's --replay= takes
    error: BaseException | None = None  # what the bot callback raised, with its traceback


class LinkSetupError(Exception):
    """The run could not be started: the socket is taken or can't be made, or probe.sh won't run."""


class _Ended(BaseException):
    """The engine closed the link, or sent what isn't the protocol (`bad`). It's not an Exception
    so that a bot's own `except Exception` can't swallow it."""

    def __init__(self, bad: bytes | None = None) -> None:
        super().__init__(bad)
        self.bad = bad


class _TimedOut(BaseException):
    """A wait for the engine ran out of time."""


class _TimeUp(Exception):
    """The run's deadline (TIME_LIMIT) or the hang (HANG) passed while the game hadn't connected."""

    def __init__(self, why: str) -> None:
        super().__init__(why)
        self.why = why


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
        self._conn.settimeout(None)
        try:
            self._conn.sendall(data)
        except OSError:  # the game is gone
            raise _Ended() from None

    def _line(self, timeout: float | None = None) -> bytes:
        """The next line, waiting up to `timeout` seconds for it (for ever when None)."""
        assert self._conn is not None and self._lines is not None
        self._conn.settimeout(timeout)
        try:
            line = self._lines.readline()
        except socket.timeout:  # before OSError, which it is one of
            raise _TimedOut() from None
        except OSError:  # a reset
            raise _Ended() from None
        if not line.endswith(b"\n"):  # the end of the stream, or the end partway through a line
            raise _Ended()
        return line


@dataclass
class _State:
    deadline: float  # on time.monotonic()'s clock
    frames: int = 0
    last_frame: int | None = None
    error: BaseException | None = None
    bad_line: bytes | None = None
    ended: str | None = None  # TIME_LIMIT or HANG, the run's own ends
    unconnected: bool = False  # the hang was the wait for the game to connect again


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


def _accept(listener: socket.socket, proc: subprocess.Popen, deadline: float,
            hang_at: float | None = None) -> socket.socket | None:
    """The game's next connection, or None once probe.sh has exited without one. It's a _TimeUp
    when `deadline` passes first (TIME_LIMIT) or `hang_at` does (HANG), both on time.monotonic()'s
    clock."""
    stop, why = deadline, TIME_LIMIT
    if hang_at is not None and hang_at < deadline:
        stop, why = hang_at, HANG
    while True:
        left = stop - time.monotonic()
        if left <= 0:
            raise _TimeUp(why)
        ready, _, _ = select.select([listener], [], [], min(0.2, left))
        if ready:
            return listener.accept()[0]
        if proc.poll() is not None:
            return None


def _step(link: Link, bot: Callable[[Link], dict[int, Pad]], state: _State, hang: float | None) -> None:
    """Answers the engine's frames until it closes the link, the bot raises, the engine sends
    what isn't the protocol, the deadline passes or `hang` seconds go by with no frame. The hang
    clock starts at the connect and again at each answer, so the time the bot takes isn't the
    game's."""
    waiting = time.monotonic()
    try:
        while True:
            now = time.monotonic()
            wait, why = state.deadline - now, TIME_LIMIT
            if hang is not None and hang - (now - waiting) < wait:
                wait, why = hang - (now - waiting), HANG
            if wait <= 0:
                state.ended = why
                return
            try:
                line = link._line(wait)
            except _TimedOut:
                state.ended = why
                return
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
            waiting = time.monotonic()
    except _Ended as e:
        state.bad_line = e.bad


def _wait_closed(link: Link) -> None:
    """Holds the link open until the game closes it by exiting, or CLOSE_WAIT seconds go by.
    probe.sh sends its game SIGTERM and exits without waiting for it, so the game is still
    shutting down when probe.sh is gone, and a link closed then would be logged as the bot
    hanging up and the input log would be cut short."""
    conn = link._conn
    assert conn is not None
    deadline = time.monotonic() + CLOSE_WAIT
    while (left := deadline - time.monotonic()) > 0:
        conn.settimeout(left)
        try:
            if not conn.recv(4096):  # the end of the stream; the buffered reader is spent after a timeout
                return
        except OSError:  # a reset, or the time running out
            return


def _tail(path: Path, size: int = TAIL) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - size))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _last_line(path: Path) -> str | None:
    lines = [t for t in _tail(path).splitlines() if t.strip()]
    return lines[-1] if lines else None


def _last(pattern: re.Pattern, text: str) -> str | None:
    found = pattern.findall(text)
    return found[-1] if found else None


def _last_crash(text: str) -> str | None:
    return next((line for line in reversed(text.splitlines()) if session_log.FATAL.match(line)), None)


def _session_lines(log: Path) -> tuple[str | None, str | None]:
    """What the game's stdout.txt says of its last process's session: the directory in its last
    `[session] DIR` line, and the `[reset]` line of a restart or hot reset that came after it.
    The second means the game started again and the new process never began a session. Every
    line is looked at, since a process says this at its start and a long run says much after."""
    session = reset = None
    try:
        with open(log, errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")
                if m := session_log.SESSION.match(line):
                    session, reset = m[1], None
                elif session_log.RESET.match(line) and session_log.SHUTDOWN not in line:
                    reset = line
    except OSError:
        pass
    return session, reset


def _reset_count(log: Path) -> int:
    """How many restart and hot-reset `[reset]` lines a game's stdout.txt has, whatever follows
    them. A shutdown isn't one, since the game doesn't start again."""
    try:
        with open(log, errors="replace") as f:
            return sum(1 for line in f if session_log.RESET.match(line) and session_log.SHUTDOWN not in line)
    except OSError:
        return 0


def _input_log(run_dir: Path, session: str | None) -> Path | None:
    """The inputs/ directory of the session a `[session] DIR` line names (an absolute DIR is
    used as it is and a relative one is taken from `run_dir`), when it holds an input log. It's
    what probe.sh's --replay= takes."""
    if session is None:
        return None
    inputs = run_dir / session / "inputs"
    return inputs if (inputs / "inputs.txt").is_file() else None


def _game_verdict(run_dir: Path, starts: int, probe_err: str, input_log: Path | None,
                  settings: Sequence[str], restarted: str | None = None,
                  timed_out: bool = False) -> tuple[str, str]:
    """How a run the game ended, and not the run, ended, from what the game wrote. Before the
    input log, the engine's own lines: a failed connect, a crash and a stop. Then the input log:
    the engine writes `# end POLL FRAME` on every way out it chooses (a clean exit, a reset, a
    signal, a stop or a fault), and a game that left none died. So did one that reset the console
    and started again (`restarted` is its `[reset]` line) without the new process getting as far
    as a session, since the log is then the first process's, which ended with the reset.
    `timed_out` is for a game still booting when the run's time was up."""
    tail = _tail(run_dir / "stdout.txt")
    line = _last(CONNECT_LINE, tail)
    if line is not None:
        return CONNECT_FAILED, line
    try:
        panic = (run_dir / "panic.txt").read_text(errors="replace")
    except OSError:
        panic = None
    crash = _last_crash(tail)
    if panic is not None or crash is not None:
        first = panic.strip().splitlines()[0] if panic is not None and panic.strip() else None
        return PANIC, first or crash or "panic.txt is empty"
    line = _last(STOP_LINE, tail)
    if line is not None:
        return ENGINE_STOP, line
    lines = [t for t in tail.splitlines() if t.strip()]
    if starts == 0:
        if timed_out:
            return NEVER_LINKED, "the game hadn't connected when the time limit came" + (
                f", and its last line is {lines[-1]!r}" if lines else "")
        return NEVER_LINKED, probe_err.strip() or (lines[-1] if lines else "the game ended before it connected")
    if restarted is not None:
        return GAME_DIED, f"{restarted}, and no session began after it"
    end = END_LINE.findall(_tail(input_log / "inputs.txt", LOG_TAIL)) if input_log is not None else []
    if not end:
        return GAME_DIED, lines[-1] if lines else "the game wrote nothing"
    frame = int(end[-1][1])
    shutdown = next((t for t in reversed(lines) if session_log.RESET.match(t) and session_log.SHUTDOWN in t), None)
    if shutdown is not None:
        return SHUTDOWN, shutdown
    limit = EXIT_AFTER_ARG.search(" ".join(settings))
    if limit and frame >= int(limit[1]):  # frames submitted run ahead of the ones shown
        return EXIT_AFTER, f"--exit-after={limit[1]}"
    return GAME_EXITED, f"the game ended at frame {frame}"


def run(name: str, seconds: int, bot: Callable[[Link], dict[int, Pad]], *, pads: int = 1,
        script: str = "", every: int = 60, settings: Sequence[str] = (), hang: float | None = None,
        probe: str | os.PathLike | None = None) -> Outcome:
    """Plays the game as NAME in build/probe/NAME/ for up to `seconds`, calling `bot` once for
    each frame the engine steps it at. `bot` may read RAM through the Link and returns the pad
    for each port it drives, ports 1 to `pads`. `script` is probe.sh's INPUT_SCRIPT, `every`
    its DUMP_EVERY and `settings` more of its settings. `hang` is the wall seconds without a
    frame before the run stops as a hang, None for never. `probe` is a probe.sh-compatible
    program for a fake in a test; its run directory is where probe.sh's would be.

    The run is a session, build/probe/NAME/session unless `settings` names a GCN_SESSION, so
    its input log replays with no bot. A session the run makes records no audio, unless
    `settings` sets GCN_WAV or GCN_AIDWAV. At `seconds`, and at a hang, the game is ended with
    the link still open, so the engine doesn't log that the bot hung up. The game connects again
    after it resets the console, and the bot goes on with it; `hang` counts the wait for that
    too, but not the wait after a game that exited, nor the wait for the first connection, which
    `seconds` bounds and which a game that never makes is a NEVER_LINKED. Raises ValueError for an argument probe.sh or the link would
    refuse, and LinkSetupError when no run could be started."""
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", name):
        raise ValueError(f"{name!r}: not a name for a run's directory")
    if seconds < 1 or every < 1:
        raise ValueError("seconds and every are whole numbers from 1")
    if hang is not None and hang <= 0:
        raise ValueError("hang is a number of seconds above 0, or None")
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
    ours = [s for s in settings if s.startswith("GCN_SESSION=") and len(s) > len("GCN_SESSION=")]
    session = run_dir / (ours[-1][len("GCN_SESSION="):] if ours else "session")  # an absolute one wins
    link, proc = Link(), None
    resets = 0  # the restart and hot-reset lines in stdout.txt that links have ended on
    started = time.monotonic()
    state = _State(started + seconds)
    err: str | None = None
    try:
        for stale in ("stdout.txt", "panic.txt"):
            try:
                (run_dir / stale).unlink()
            except FileNotFoundError:
                pass
        if not ours and session.exists():
            remove_run(session)
        # An empty GCN_WAV or GCN_AIDWAV is a recording the engine can't open, so it makes none.
        silent = [f"{var}=" for var in ("GCN_WAV", "GCN_AIDWAV") if not any(s.startswith(f"{var}=") for s in settings)]
        argv = [str(probe_path), name, str(seconds + DEADLINE_SLACK), script, str(every), *settings,
                *([] if ours else [f"GCN_SESSION={session}", *silent]), f"--pads={pads}", f"GCN_BOT={sock}"]
        try:
            proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
        except OSError as e:
            raise LinkSetupError(f"can't run {probe_path}: {e}") from None
        while True:
            # The hang clock runs from the end of a link the game ended by resetting the console,
            # which it says in stdout.txt before the relaunch closes the link. Any other end is
            # the game exiting, and probe.sh only notices at its next one-second tick. A game
            # that hasn't connected yet has the deadline. The reset lines are counted, since the
            # new process may have printed its [session] line by the time this looks.
            hang_at = None
            if hang is not None and link.starts:
                reset_lines = _reset_count(run_dir / "stdout.txt")
                if reset_lines > resets:
                    hang_at = time.monotonic() + hang
                resets = reset_lines
            try:
                conn = _accept(listener, proc, state.deadline, hang_at)
            except _TimeUp as e:
                state.ended, state.unconnected = e.why, e.why == HANG
                break
            if conn is None:
                break
            link._attach(conn)
            try:
                _step(link, bot, state, hang)
                if state.ended:  # with the link still open, or the engine would log the hang-up
                    proc.terminate()
                    _, err = proc.communicate()
                    _wait_closed(link)
            finally:
                link._detach()
            if state.error is not None or state.bad_line is not None or state.ended:
                break
        if err is None:
            if state.ended:
                proc.terminate()
            _, err = proc.communicate()
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
    session_dir, restarted = _session_lines(run_dir / "stdout.txt")
    input_log = _input_log(run_dir, session_dir)
    if state.error is not None:
        reason, detail = BOT_RAISED, f"{type(state.error).__name__}: {state.error}"
    elif state.bad_line is not None:
        reason, detail = BAD_LINK, f"the engine sent {state.bad_line!r}, not a frame or data line"
    elif state.ended == TIME_LIMIT and link.starts:
        reason, detail = TIME_LIMIT, f"the time limit, {seconds} s"
    elif state.ended == HANG:
        if state.unconnected:
            last = _last_line(run_dir / "stdout.txt")
            detail = f"no new connection for {hang:g} s after the link closed" + (
                f", and its last line is {last!r}" if last else "")
        else:
            after = "it connected" if state.last_frame is None else f"frame {state.last_frame}"
            detail = f"no frame for {hang:g} s after {after}"
        reason = HANG
    else:
        reason, detail = _game_verdict(run_dir, link.starts, err, input_log, settings, restarted,
                                       timed_out=state.ended == TIME_LIMIT)
    return Outcome(state.frames, state.last_frame, reason, detail, run_dir, input_log, state.error)


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
    ap.add_argument("--hang", type=float, default=30, metavar="SECONDS")
    ap.add_argument("--watch", type=_watch_arg, action="append", default=[], metavar="ADDR:LEN")
    ap.add_argument("--probe", help=argparse.SUPPRESS)
    ap.add_argument("name")
    ap.add_argument("seconds", type=int)
    args = ap.parse_args(argv)
    if args.hang < 0:
        ap.error("--hang is a number of seconds from 0")
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
        outcome = run(args.name, args.seconds, bot, pads=args.pads, script=args.script, every=args.every,
                      settings=settings, hang=args.hang or None, probe=args.probe)
    except (ValueError, LinkSetupError) as e:
        print(f"bot_link.py: {e}", file=sys.stderr)
        return 2
    if outcome.reason == NEVER_LINKED:
        print(f"bot_link.py: the game never connected: {outcome.detail}", file=sys.stderr)
        return 2
    last = "no frame" if outcome.last_frame is None else f"the last frame {outcome.last_frame}"
    print(f"{outcome.run_dir}: {outcome.reason}, {outcome.frames} frames answered, {last}")
    print(f"  {outcome.detail}")
    if outcome.input_log is not None:
        print(f"  input log {outcome.input_log}")
    return 0 if outcome.reason in CLEAN else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
