from __future__ import annotations

import argparse
import dataclasses
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import bot_link
from bot_link import BUTTONS, Link, LinkSetupError, Outcome, Pad, encode_pads, run, socket_path
from testutil import run_main, write_file

REAL_PROBE = Path(__file__).resolve().parent / "probe.sh"

# A stand-in for probe.sh and the game behind it. It takes probe.sh's arguments, works in the
# same build/probe/NAME/, and plays the engine's side of the bot link as plan.json beside tools/
# says, with the checks gcn-recomp's bot_link.cpp makes that a test here needs. Like the engine
# it begins a session for GCN_SESSION (a run-N of its own once session.json is taken), prints its
# [session] line, writes an input log that ends in `# end POLL FRAME` on the ways out the engine
# writes one on, and on SIGTERM ends the way probe.sh and the game do: the probe is gone at once
# and the game goes on for half a second, as on_interrupt does. It records what it saw in
# record.json, and whether the link was still open when the game looked. A plan is
# {"frames": [N, ...]} and any of these:
#   "after"          what it does once its frames are done: "exit" (the default), "linger" (waits
#                    out SECONDS with the link open and sends no frame), "shutdown" (the console
#                    shutdown the game asks for), "died" (no `# end`, as after an abort),
#                    "panic", "fatal", "garbage" (sends a line that isn't a frame) or "reset"
#                    (a console reset: it hangs up and starts again as a new process, to play
#                    "then", another plan, which may have a "connect_after" of its own and may
#                    have "session_first", which says its [session] line before the hang-up),
#                    "reset_fails" (the reset, and the restart never happens, as when execv
#                    fails) or "reset_dies" (the restarted process says its [session] line and
#                    dies before its input log)
#   "forever"        goes on sending frames after the listed ones, for as long as the bot answers
#   "refuse"         the text of a refusal on stderr; it exits 2 without a game, as probe.sh does
#   "connect_fails"  the game's failed connect, without one
#   "connect_after"  seconds to wait before it connects
#   "boot_says"      a line it prints after its [session] line and before it connects
#   "die_at"         exits just after sending that frame, without waiting for the answer
#   "partial_data"   answers the first read with half a line and exits
#   "bad_data"       answers a read with what isn't a data line
#   "ignore_hangup"  waits instead of exiting when the bot hangs up
#   "moving"         makes RAM change from frame to frame
#   "kind"           what a reset says it is: "restart" (the default), "hot reset" or "shutdown"
#   "exit_late"      seconds the probe lingers after a plain exit, with the link closed
# A read outside 80000000 to 817FFFFF, or of fewer than 1 or more than 256 bytes, stops the game.
FAKE_PROBE = r'''#!@PYTHON@
import atexit, json, os, signal, socket, sys, time

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
name, seconds, script, every, *settings = sys.argv[1:]
out = os.path.join(root, "build", "probe", name)
os.makedirs(out, exist_ok=True)
os.chdir(out)
with open(os.path.join(root, "plan.json")) as f:
    plan = json.load(f)
path = [s[len("GCN_BOT="):] for s in settings if s.startswith("GCN_BOT=")][0]
ports = int(([s[len("--pads="):] for s in settings if s.startswith("--pads=")] or ["1"])[-1])
session = ([s[len("GCN_SESSION="):] for s in settings if s.startswith("GCN_SESSION=")] or [""])[-1]
rec = {"argv": sys.argv[1:], "events": [], "starts": 0, "gcn_bot": path, "session": session}
conn = lines = log = last = None
with open("pid.txt", "w") as f:
    f.write(str(os.getpid()))


def save():
    with open("record.json", "w") as f:
        json.dump(rec, f)


atexit.register(save)


def say(text, file="stdout.txt"):
    with open(file, "a") as f:
        f.write(text)


def begin_log(open_log=True):
    global log
    if not session:
        return
    where = session
    if os.path.exists(os.path.join(where, "session.json")):
        n = 2
        while os.path.exists(os.path.join(where, "run-%d" % n, "session.json")):
            n += 1
        where = os.path.join(where, "run-%d" % n)
    os.makedirs(os.path.join(where, "inputs") if open_log else where)
    with open(os.path.join(where, "session.json"), "w") as f:
        f.write("{}")
    say("[session] %s\n" % where)
    if not open_log:
        return
    log = open(os.path.join(where, "inputs", "inputs.txt"), "w")
    log.write("# gcn-recomp input log v5\n")
    log.flush()


def end_log():
    global log
    if log is not None:
        log.write("# end 0 %d\n" % (last if last is not None else 0))
        log.flush()
    log = None


def on_term(signum, frame):
    # probe.sh exits at once on SIGTERM and leaves the game to shut down by itself, so the
    # probe is gone here and a child plays the game, which looks at the link a moment later.
    if os.fork():
        os._exit(1)
    devnull = os.open(os.devnull, os.O_RDWR)  # the game's output goes to a file, not probe.sh's pipes
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    time.sleep(0.5)
    state = "none"
    if conn is not None:
        conn.setblocking(False)
        try:
            state = "open" if conn.recv(1, socket.MSG_PEEK) else "closed"
        except BlockingIOError:
            state = "open"
        except OSError:
            state = "closed"
    rec["link_at_term"] = state
    end_log()
    save()
    os._exit(1)


signal.signal(signal.SIGTERM, on_term)


def stop(frame, why):
    say("[bot] frame %d: %s\n" % (frame, why))
    end_log()
    sys.exit(1)


def ram(addr, length, frame):
    shift = frame if plan.get("moving") else 0
    return bytes((addr + i + shift) & 255 for i in range(length))


def step(frame):
    conn.sendall(("frame %d\n" % frame).encode())
    if not plan.get("forever"):
        rec["events"].append("frame %d" % frame)
    if plan.get("die_at") == frame:
        end_log()
        sys.exit(0)
    have = set()
    while True:
        line = lines.readline().decode()
        if not line:
            if plan.get("ignore_hangup"):
                time.sleep(20)
            stop(frame, "the bot hung up")
        line = line.rstrip("\n")
        if not plan.get("forever"):
            rec["events"].append(line)
        words = line.split()
        if words[0] == "read":
            addr, length = int(words[1], 16), int(words[2])
            if not (0x80000000 <= addr and addr + length <= 0x81800000 and 1 <= length <= 256):
                stop(frame, 'a read outside RAM, 80000000 to 817FFFFF: "%s"' % line)
            if plan.get("partial_data"):
                conn.sendall(b"data 0102")
                end_log()
                sys.exit(0)
            if plan.get("bad_data"):
                conn.sendall(b"nope\n")
                continue
            conn.sendall(b"data " + ram(addr, length, frame).hex().encode() + b"\n")
        elif words[0] == "pad":
            port = int(words[1])
            if not 1 <= port <= ports:
                stop(frame, 'port %d isn\'t one the bot drives (--pads=%d): "%s"' % (port, ports, line))
            have.add(port)
        elif words[0] == "done":
            for port in range(1, ports + 1):
                if port not in have:
                    stop(frame, 'done without a pad line for port %d, which the bot drives: "%s"' % (port, line))
            return


def numbers(frames, forever):
    for frame in frames:
        yield frame
    n = frames[-1] + 1 if frames else 0
    while forever:
        yield n
        n += 1


def play(frames, forever=False, connect_after=0, begun=False):
    global conn, lines, last
    if not begun:
        begin_log()
    if plan.get("boot_says"):
        say(plan["boot_says"])
    if connect_after:
        time.sleep(connect_after)
    if plan.get("connect_fails"):
        say("--bot %s: can't connect: Connection refused\n" % path)
        end_log()
        sys.exit(1)
    conn = socket.socket(socket.AF_UNIX)
    conn.connect(path)
    rec["starts"] += 1
    lines = conn.makefile("rb")
    for frame in numbers(frames, forever):
        last = frame
        step(frame)


if plan.get("refuse"):
    print(plan["refuse"], file=sys.stderr)
    sys.exit(2)
play(plan["frames"], plan.get("forever", False), plan.get("connect_after", 0))
after = plan.get("after", "exit")
if after == "linger":
    time.sleep(int(seconds))
    end_log()
elif after == "panic":
    say("guest panic: foo.c:12: boom\nguest backtrace (innermost first):\n", "panic.txt")
elif after == "fatal":
    say("FATAL: call_indirect: no function at 00000000\n")
elif after == "died":
    say("abort: assertion failed\n")
elif after == "shutdown":
    say("[reset] the game reset the console (shutdown, code 0)\n")
    end_log()
elif after == "garbage":
    conn.sendall(b"hello\n")
    lines.readline()
    end_log()
elif after in ("reset", "reset_fails", "reset_dies"):
    say("[reset] the game reset the console (%s, code 0)\n" % plan.get("kind", "restart"))
    end_log()
    early = after == "reset" and plan["then"].get("session_first")
    if early:  # the new process is quick, and says its [session] line as the old one lets go
        begin_log()
    lines.close()
    conn.close()
    if after == "reset_dies":
        begin_log(open_log=False)
        sys.exit(1)
    if after == "reset":
        play(plan["then"]["frames"], connect_after=plan["then"].get("connect_after", 0), begun=bool(early))
        end_log()
else:
    end_log()
if plan.get("exit_late"):  # probe.sh sees its game gone only at its next one-second tick
    lines.close()
    conn.close()
    time.sleep(plan["exit_late"])
'''

# A stand-in for the game alone, for probe.sh itself to run in build/dragoon.
FAKE_GAME = r'''#!@PYTHON@
import json, os, socket, sys

print("[session] " + os.environ["GCN_SESSION"], file=sys.stderr, flush=True)
conn = socket.socket(socket.AF_UNIX)
conn.connect(os.environ["GCN_BOT"])
lines = conn.makefile("rb")
for frame in (0, 1, 2):
    conn.sendall(("frame %d\n" % frame).encode())
    while True:
        line = lines.readline().strip()
        if not line:
            sys.exit(1)
        if line == b"done":
            break
inputs = os.path.join(os.environ["GCN_SESSION"], "inputs")
os.makedirs(inputs)
with open(os.path.join(inputs, "inputs.txt"), "w") as f:
    f.write("# gcn-recomp input log v5\n# end 6 1500\n")
with open("record.json", "w") as f:
    json.dump({"argv": sys.argv[1:], "env": {k: v for k, v in os.environ.items() if k.startswith("GCN_")}}, f)
'''


def neutral(link: Link) -> dict[int, Pad]:
    return {1: Pad()}


class FakeProbeCase(unittest.TestCase):
    """A temp tree with a fake probe.sh in tools/, the way test_probe.py makes one."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.probe = self.tree(self.root)

    def tree(self, root: Path) -> Path:
        (root / "tools").mkdir(parents=True)
        probe = write_file(root / "tools", "probe.sh", FAKE_PROBE.replace("@PYTHON@", sys.executable))
        probe.chmod(0o755)
        return probe

    def plan(self, frames: list[int], **more: object) -> None:
        write_file(self.probe.parent.parent, "plan.json", json.dumps({"frames": frames, **more}))

    def go(self, bot, name: str = "t", seconds: int = 30, **kwargs) -> Outcome:
        return run(name, seconds, bot, probe=self.probe, **kwargs)

    def run_dir(self, name: str = "t") -> Path:
        return self.root / "build" / "probe" / name

    def record(self, name: str = "t") -> dict:
        return json.loads((self.run_dir(name) / "record.json").read_text())


class PadTest(unittest.TestCase):
    def test_a_default_pad_is_at_rest(self):
        self.assertEqual(Pad(), Pad(buttons=0, sx=128, sy=128, cx=128, cy=128, l=0, r=0))

    def test_a_pad_is_frozen(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            Pad().buttons = 1  # type: ignore[misc]

    def test_pad_lines_are_in_port_order_with_buttons_in_hex(self):
        pads = {2: Pad(buttons=BUTTONS["A"] | BUTTONS["START"], sx=0, l=255), 1: Pad()}
        self.assertEqual(encode_pads(pads), b"pad 1 0000 128 128 128 128 0 0\n"
                                            b"pad 2 1100 0 128 128 128 255 0\ndone\n")

    def test_a_port_left_out_is_left_out(self):
        self.assertEqual(encode_pads({}), b"done\n")
        self.assertEqual(encode_pads({3: Pad()}), b"pad 3 0000 128 128 128 128 0 0\ndone\n")

    def test_something_that_is_not_a_dict_of_pads_is_a_type_error(self):
        for bad in (None, [Pad()], {1: None}, {1: (0, 128, 128, 128, 128, 0, 0)}):
            with self.subTest(bad=bad), self.assertRaises(TypeError):
                encode_pads(bad)  # type: ignore[arg-type]

    def test_buttons_are_the_padstatus_bits(self):
        self.assertEqual(BUTTONS["A"], 0x0100)
        self.assertEqual(BUTTONS["START"], 0x1000)
        self.assertEqual(len(set(BUTTONS.values())), len(BUTTONS))
        for bits in BUTTONS.values():
            Pad(buttons=bits)

    def test_a_value_the_engine_would_refuse_is_a_value_error_here(self):
        for bad in ({"sx": 256}, {"sy": -1}, {"cx": 300}, {"cy": 128.0}, {"l": 256}, {"r": None},
                    {"buttons": 0x2000}, {"buttons": 0x0080}, {"buttons": -1}, {"buttons": 1.0}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Pad(**bad)
        Pad(buttons=0x1F7F, sx=0, sy=255, cx=0, cy=255, l=255, r=255)


class StepTest(FakeProbeCase):
    def test_the_bot_is_called_once_for_each_frame_with_its_number(self):
        self.plan([0, 1, 2])
        seen: list[int] = []

        def bot(link: Link) -> dict[int, Pad]:
            seen.append(link.frame)
            return {1: Pad(buttons=link.frame)}

        outcome = self.go(bot)
        self.assertEqual(seen, [0, 1, 2])
        self.assertEqual((outcome.frames, outcome.last_frame), (3, 2))
        self.assertEqual([e for e in self.record()["events"] if e.startswith("pad")],
                         ["pad 1 0000 128 128 128 128 0 0", "pad 1 0001 128 128 128 128 0 0",
                          "pad 1 0002 128 128 128 128 0 0"])

    def test_frame_numbers_can_jump(self):
        self.plan([0, 1, 5, 6000])
        seen: list[int] = []
        outcome = self.go(lambda link: seen.append(link.frame) or {1: Pad()})
        self.assertEqual(seen, [0, 1, 5, 6000])
        self.assertEqual((outcome.frames, outcome.last_frame), (4, 6000))

    def test_a_read_comes_back_with_the_bytes(self):
        self.plan([3])
        got: list[bytes] = []

        def bot(link: Link) -> dict[int, Pad]:
            got.append(link.read(0x80000010, 4))
            got.append(link.read(0x817FFF00, 256))
            return {1: Pad()}

        self.go(bot)
        self.assertEqual(got[0], bytes([0x10, 0x11, 0x12, 0x13]))
        self.assertEqual(got[1], bytes(range(256)))

    def test_reads_go_out_and_come_back_before_the_pads_are_sent(self):
        self.plan([3, 4], moving=True)
        got: list[bytes] = []

        def bot(link: Link) -> dict[int, Pad]:
            a = link.read(0x80000000, 2)
            b = link.read(0x80001000, 1)
            got.append(a + b)
            return {1: Pad(buttons=b[0])}

        self.go(bot)
        self.assertEqual(got, [bytes([3, 4, 3]), bytes([4, 5, 4])])
        self.assertEqual(self.record()["events"],
                         ["frame 3", "read 80000000 2", "read 80001000 1",
                          "pad 1 0003 128 128 128 128 0 0", "done",
                          "frame 4", "read 80000000 2", "read 80001000 1",
                          "pad 1 0004 128 128 128 128 0 0", "done"])

    def test_several_ports_arrive_together_in_one_answer(self):
        self.plan([0, 1])
        outcome = self.go(lambda link: {p: Pad(buttons=p, sx=p) for p in (3, 1, 2)}, pads=3)
        self.assertEqual((outcome.reason, outcome.frames), (bot_link.GAME_EXITED, 2))
        self.assertEqual(self.record()["events"][:5],
                         ["frame 0", "pad 1 0001 1 128 128 128 0 0", "pad 2 0002 2 128 128 128 0 0",
                          "pad 3 0003 3 128 128 128 0 0", "done"])
        self.assertIn("--pads=3", self.record()["argv"])

    def test_a_port_the_bot_leaves_out_is_named_by_the_engine_and_not_filled_in(self):
        self.plan([7])
        outcome = self.go(lambda link: {1: Pad()}, pads=2)
        self.assertEqual(outcome.reason, bot_link.ENGINE_STOP)
        self.assertIn("done without a pad line for port 2", outcome.detail)
        self.assertEqual([e for e in self.record()["events"] if e.startswith("pad")],
                         ["pad 1 0000 128 128 128 128 0 0"])

    def test_a_port_the_game_does_not_have_is_named_by_the_engine_with_its_line(self):
        self.plan([7])
        outcome = self.go(lambda link: {1: Pad(), 2: Pad(buttons=BUTTONS["A"])})
        self.assertEqual(outcome.reason, bot_link.ENGINE_STOP)
        self.assertEqual(outcome.detail, "[bot] frame 7: port 2 isn't one the bot drives (--pads=1): "
                                         '"pad 2 0100 128 128 128 128 0 0"')

    def test_a_value_out_of_range_is_the_bots_error_and_not_the_engines(self):
        self.plan([0, 1, 2])

        def bot(link: Link) -> dict[int, Pad]:
            return {1: Pad(sx=128 + 128 * link.frame)}  # 256 at frame 1

        outcome = self.go(bot)
        self.assertEqual((outcome.reason, outcome.frames), (bot_link.BOT_RAISED, 1))
        self.assertIn("Pad.sx", outcome.detail)


class OutcomeTest(FakeProbeCase):
    def test_a_stop_the_engine_reports_is_its_own_line(self):
        self.plan([3, 4])
        calls: list[int] = []

        def bot(link: Link) -> dict[int, Pad]:
            calls.append(link.frame)
            link.read(0x817FFFFF, 2)  # one byte past the end of RAM
            return {1: Pad()}

        outcome = self.go(bot)
        self.assertEqual(calls, [3])  # the read ended the run, and the bot isn't called again
        self.assertEqual((outcome.reason, outcome.frames, outcome.last_frame), (bot_link.ENGINE_STOP, 0, 3))
        self.assertEqual(outcome.detail, '[bot] frame 3: a read outside RAM, 80000000 to 817FFFFF: '
                                         '"read 817FFFFF 2"')
        self.assertIsNone(outcome.error)
        self.assertEqual(outcome.run_dir, self.run_dir())
        self.assertEqual(outcome.input_log, self.run_dir() / "session" / "inputs")

    def test_a_connect_the_engine_could_not_make_is_its_own_line(self):
        self.plan([], connect_fails=True)
        outcome = self.go(neutral)
        self.assertEqual((outcome.reason, outcome.frames, outcome.last_frame), (bot_link.CONNECT_FAILED, 0, None))
        self.assertEqual(outcome.detail, f"--bot {self.record()['gcn_bot']}: can't connect: Connection refused")

    def test_a_panic_txt_is_a_panic_with_its_first_line(self):
        self.plan([0, 1], after="panic")
        outcome = self.go(neutral)
        self.assertEqual((outcome.reason, outcome.frames), (bot_link.PANIC, 2))
        self.assertEqual(outcome.detail, "guest panic: foo.c:12: boom")

    def test_a_fatal_line_is_a_panic_without_a_panic_txt(self):
        self.plan([0], after="fatal")
        outcome = self.go(neutral)
        self.assertEqual(outcome.reason, bot_link.PANIC)
        self.assertEqual(outcome.detail, "FATAL: call_indirect: no function at 00000000")

    def test_a_bot_that_raises_ends_the_run_as_the_bots_and_not_as_the_engines_hang_up_line(self):
        self.plan(list(range(10)))

        def bot(link: Link) -> dict[int, Pad]:
            if link.frame == 2:
                raise ValueError("boom")
            return {1: Pad()}

        outcome = self.go(bot)
        self.assertEqual((outcome.reason, outcome.frames, outcome.last_frame), (bot_link.BOT_RAISED, 2, 2))
        self.assertEqual(outcome.detail, "ValueError: boom")
        self.assertIsInstance(outcome.error, ValueError)
        self.assertIn("[bot] frame 2: the bot hung up", (outcome.run_dir / "stdout.txt").read_text())

    def test_a_bot_that_returns_no_pads_is_a_bot_that_raised(self):
        self.plan([0, 1])
        outcome = self.go(lambda link: None)  # type: ignore[arg-type,return-value]
        self.assertEqual((outcome.reason, outcome.frames), (bot_link.BOT_RAISED, 0))
        self.assertIn("not a dict of port to Pad", outcome.detail)

    def test_the_end_of_the_link_is_not_an_exception_a_bot_can_catch(self):
        self.plan([3, 4])
        swallowed: list[BaseException] = []
        later: list[int] = []

        def bot(link: Link) -> dict[int, Pad]:
            try:
                link.read(0x817FFFFF, 2)
            except Exception as e:  # must not run: the engine's stop ends the bot's frame
                swallowed.append(e)
            later.append(link.frame)
            return {1: Pad()}

        self.assertFalse(issubclass(bot_link._Ended, Exception))
        self.assertEqual(self.go(bot).reason, bot_link.ENGINE_STOP)
        self.assertEqual((swallowed, later), ([], []))

    def test_a_game_that_exits_after_its_frames_is_exit_after(self):
        self.plan([0, 1, 2])
        outcome = self.go(neutral, settings=["--exit-after=2"])
        self.assertEqual((outcome.reason, outcome.frames, outcome.last_frame), (bot_link.EXIT_AFTER, 3, 2))
        self.assertEqual(outcome.detail, "--exit-after=2")
        self.assertEqual(outcome.input_log, self.run_dir() / "session" / "inputs")

    def test_a_game_that_ends_before_the_frames_exit_after_wants_is_not_exit_after(self):
        self.plan([0, 1, 2])
        outcome = self.go(neutral, settings=["--exit-after=1500"])
        self.assertEqual((outcome.reason, outcome.detail), (bot_link.GAME_EXITED, "the game ended at frame 2"))

    def test_a_game_that_exits_by_itself_is_game_exited(self):
        self.plan([0])
        outcome = self.go(neutral)
        self.assertEqual((outcome.reason, outcome.detail), (bot_link.GAME_EXITED, "the game ended at frame 0"))

    def test_a_game_that_shuts_the_console_down_is_shutdown_whatever_exit_after_says(self):
        self.plan([0, 1, 2], after="shutdown")
        for settings in ([], ["--exit-after=2"]):
            with self.subTest(settings=settings):
                outcome = self.go(neutral, settings=settings)
                self.assertEqual(outcome.reason, bot_link.SHUTDOWN)
                self.assertEqual(outcome.detail, "[reset] the game reset the console (shutdown, code 0)")

    def test_a_game_with_no_end_in_its_input_log_died_whatever_exit_after_says(self):
        self.plan([0, 1, 2], after="died")
        outcome = self.go(neutral, settings=["--exit-after=1500"])
        self.assertEqual((outcome.reason, outcome.frames), (bot_link.GAME_DIED, 3))
        self.assertEqual(outcome.detail, "abort: assertion failed")

    def test_a_game_with_no_input_log_at_all_died_and_its_last_line_is_the_detail(self):
        run_dir = self.root / "run"
        run_dir.mkdir()
        write_file(run_dir, "stdout.txt", "[session] can't write /x, so no session is recorded\nlast words\n\n")
        self.assertEqual(bot_link._game_verdict(run_dir, 1, "", None, []), (bot_link.GAME_DIED, "last words"))
        (run_dir / "stdout.txt").unlink()
        self.assertEqual(bot_link._game_verdict(run_dir, 1, "", None, []),
                         (bot_link.GAME_DIED, "the game wrote nothing"))

    def test_the_session_is_the_last_session_line_and_a_reset_after_it_is_a_restart_that_never_began_one(self):
        log = self.root / "stdout.txt"
        self.assertEqual(bot_link._session_lines(log), (None, None))  # no file
        write_file(self.root, "stdout.txt", "boot\n[session] /a/session\n")
        self.assertEqual(bot_link._session_lines(log), ("/a/session", None))
        write_file(self.root, "stdout.txt", "[session] /a/session\n"
                                            "[reset] the game reset the console (restart, code 0)\n")
        self.assertEqual(bot_link._session_lines(log),
                         ("/a/session", "[reset] the game reset the console (restart, code 0)"))
        write_file(self.root, "stdout.txt", "[session] /a/session\n"
                                            "[reset] the game reset the console (restart, code 0)\n"
                                            "[session] /a/session/run-2\n"
                                            "[session] can't write /x/run-3, so no session is recorded\n"
                                            "[reset] the game reset the console (hot reset, code 1)\n")
        self.assertEqual(bot_link._session_lines(log),
                         ("/a/session/run-2", "[reset] the game reset the console (hot reset, code 1)"))
        with open(log, "a") as f:
            f.write("[session] /a/session/run-3\n")
        self.assertEqual(bot_link._session_lines(log), ("/a/session/run-3", None))

    def test_a_shutdown_after_the_session_is_not_a_restart(self):
        write_file(self.root, "stdout.txt", "[session] /a/session\n"
                                            "[reset] the game reset the console (shutdown, code 0)\n")
        self.assertEqual(bot_link._session_lines(self.root / "stdout.txt"), ("/a/session", None))

    def test_the_session_line_is_found_however_much_the_game_says_after_it(self):
        write_file(self.root, "stdout.txt", "[session] /a/session\n" + "[frametime] 16.6\n" * (bot_link.TAIL // 8))
        self.assertGreater((self.root / "stdout.txt").stat().st_size, 2 * bot_link.TAIL)
        self.assertEqual(bot_link._session_lines(self.root / "stdout.txt"), ("/a/session", None))

    def test_the_input_log_is_the_inputs_of_the_named_session_when_it_holds_one(self):
        (self.root / "s" / "inputs").mkdir(parents=True)
        write_file(self.root / "s" / "inputs", "inputs.txt", "# end 0 0\n")
        (self.root / "t" / "inputs").mkdir(parents=True)  # a session whose game never opened its log
        self.assertEqual(bot_link._input_log(self.root, str(self.root / "s")), self.root / "s" / "inputs")
        self.assertEqual(bot_link._input_log(self.root, "s"), self.root / "s" / "inputs")  # relative: from the run
        self.assertIsNone(bot_link._input_log(self.root, "t"))
        self.assertIsNone(bot_link._input_log(self.root, "nowhere"))
        self.assertIsNone(bot_link._input_log(self.root, None))

    def test_a_restart_that_never_began_a_session_is_game_died_and_the_first_log_is_not_its_end(self):
        run_dir = self.root / "run"
        (run_dir / "session" / "inputs").mkdir(parents=True)
        write_file(run_dir / "session" / "inputs", "inputs.txt", "# end 9 1500\n")
        write_file(run_dir, "stdout.txt", f"[session] {run_dir / 'session'}\n"
                                          "[reset] the game reset the console (restart, code 0)\n")
        log = run_dir / "session" / "inputs"
        reset = "[reset] the game reset the console (restart, code 0)"
        self.assertEqual(bot_link._game_verdict(run_dir, 1, "", log, ["--exit-after=1500"], reset),
                         (bot_link.GAME_DIED, f"{reset}, and no session began after it"))
        self.assertEqual(bot_link._game_verdict(run_dir, 1, "", log, ["--exit-after=1500"])[0], bot_link.EXIT_AFTER)

    def test_a_game_that_restarts_and_never_relaunches_is_game_died(self):
        self.plan([0, 1], after="reset_fails")  # execv fails, and the game exits 0
        outcome = self.go(neutral)
        self.assertEqual((outcome.reason, outcome.frames, outcome.last_frame), (bot_link.GAME_DIED, 2, 1))
        self.assertEqual(outcome.detail, "[reset] the game reset the console (restart, code 0), "
                                         "and no session began after it")
        self.assertEqual(outcome.input_log, self.run_dir() / "session" / "inputs")  # the first process's

    def test_a_hot_reset_that_never_relaunches_is_game_died_too(self):
        self.plan([0], after="reset_fails", kind="hot reset")
        outcome = self.go(neutral)
        self.assertEqual(outcome.reason, bot_link.GAME_DIED)
        self.assertIn("(hot reset, code 0)", outcome.detail)

    def test_a_restart_that_dies_before_its_input_log_opens_is_game_died_with_no_input_log(self):
        self.plan([0, 1], after="reset_dies")
        outcome = self.go(neutral)
        self.assertEqual((outcome.reason, outcome.frames), (bot_link.GAME_DIED, 2))
        self.assertEqual(outcome.detail, f"[session] {self.run_dir() / 'session' / 'run-2'}")
        self.assertIsNone(outcome.input_log)  # not the first process's, which ended with the reset

    def test_a_shutdown_is_not_a_restart_that_died(self):
        self.plan([0], after="reset_fails", kind="shutdown")
        outcome = self.go(neutral)
        self.assertEqual(outcome.reason, bot_link.SHUTDOWN)

    def test_a_game_that_runs_to_the_time_limit_is_cut_off_there_with_the_link_open(self):
        self.plan([0, 1], after="linger")
        began = time.monotonic()
        outcome = self.go(neutral, seconds=1, settings=["--exit-after=1500"])
        self.assertLess(time.monotonic() - began, bot_link.DEADLINE_SLACK)  # run's deadline, not probe's
        self.assertEqual((outcome.reason, outcome.frames, outcome.detail),
                         (bot_link.TIME_LIMIT, 2, "the time limit, 1 s"))
        self.assertEqual(self.record()["link_at_term"], "open")
        self.assertNotIn("hung up", (outcome.run_dir / "stdout.txt").read_text())

    def test_the_time_limit_ends_a_game_that_is_sending_frames(self):
        self.plan([0], forever=True)
        outcome = self.go(neutral, seconds=1)
        self.assertEqual(outcome.reason, bot_link.TIME_LIMIT)
        self.assertGreater(outcome.frames, 1)
        self.assertEqual(self.record()["link_at_term"], "open")

    def test_a_game_that_has_not_connected_when_the_time_is_up_never_linked_and_says_where_it_got_to(self):
        self.plan([0], connect_after=20)
        began = time.monotonic()
        outcome = self.go(neutral, seconds=1)
        self.assertLess(time.monotonic() - began, bot_link.DEADLINE_SLACK)
        self.assertEqual((outcome.reason, outcome.frames, outcome.last_frame), (bot_link.NEVER_LINKED, 0, None))
        self.assertEqual(outcome.detail, "the game hadn't connected when the time limit came, and its last line "
                                         f"is '[session] {self.run_dir() / 'session'}'")

    def test_a_game_that_has_not_connected_at_the_time_limit_is_a_crash_when_it_said_so(self):
        self.plan([0], connect_after=20, boot_says="FATAL: boot: no window\n")
        outcome = self.go(neutral, seconds=1)
        self.assertEqual((outcome.reason, outcome.detail), (bot_link.PANIC, "FATAL: boot: no window"))

    def test_the_hang_clock_does_not_run_while_the_game_first_boots(self):
        self.plan([0], connect_after=1.5)
        outcome = self.go(neutral, hang=0.5)
        self.assertEqual((outcome.reason, outcome.frames), (bot_link.GAME_EXITED, 1))

    def test_a_game_that_resets_and_does_not_connect_again_is_a_hang_when_hang_is_set(self):
        self.plan([0, 1], after="reset", then={"frames": [0], "connect_after": 20})
        began = time.monotonic()
        outcome = self.go(neutral, hang=0.5)
        self.assertLess(time.monotonic() - began, bot_link.DEADLINE_SLACK)
        self.assertEqual((outcome.reason, outcome.frames, outcome.last_frame), (bot_link.HANG, 2, 1))
        self.assertEqual(outcome.detail, "no new connection for 0.5 s after the link closed, and its last line "
                                         f"is '[session] {self.run_dir() / 'session' / 'run-2'}'")
        self.assertEqual(outcome.input_log, self.run_dir() / "session" / "run-2" / "inputs")  # it began a session

    def test_the_hang_clock_is_armed_by_a_reset_even_when_the_new_process_has_already_said_its_session(self):
        self.plan([0, 1], after="reset", then={"frames": [0], "connect_after": 20, "session_first": True})
        began = time.monotonic()
        outcome = self.go(neutral, hang=0.5)
        self.assertLess(time.monotonic() - began, bot_link.DEADLINE_SLACK)
        self.assertEqual((outcome.reason, outcome.frames), (bot_link.HANG, 2))

    def test_resets_are_counted_whatever_follows_them_and_a_shutdown_is_not_one(self):
        log = self.root / "stdout.txt"
        self.assertEqual(bot_link._reset_count(log), 0)  # no file
        write_file(self.root, "stdout.txt", "[session] /a/session\n"
                                            "[reset] the game reset the console (restart, code 0)\n"
                                            "[session] /a/session/run-2\n"
                                            "[reset] the game reset the console (hot reset, code 1)\n"
                                            "[session] /a/session/run-3\n"
                                            "  [reset] indented, so not the engine's (restart, code 0)\n"
                                            "[reset] the game reset the console (shutdown, code 0)\n")
        self.assertEqual(bot_link._reset_count(log), 2)

    def test_a_game_that_exits_is_not_a_reconnect_the_hang_clock_runs_on_while_probe_notices(self):
        self.plan([0, 1], exit_late=1.5)
        outcome = self.go(neutral, hang=0.5)
        self.assertEqual((outcome.reason, outcome.frames), (bot_link.GAME_EXITED, 2))

    def test_a_shutdown_is_not_a_reconnect_the_hang_clock_runs_on_either(self):
        self.plan([0, 1], after="shutdown", exit_late=1.5)
        outcome = self.go(neutral, hang=0.5)
        self.assertEqual((outcome.reason, outcome.frames), (bot_link.SHUTDOWN, 2))

    def test_a_game_that_resets_and_does_not_connect_again_runs_into_the_time_limit_without_a_hang(self):
        self.plan([0, 1], after="reset", then={"frames": [0], "connect_after": 20})
        outcome = self.go(neutral, seconds=2)
        self.assertEqual((outcome.reason, outcome.frames, outcome.detail),
                         (bot_link.TIME_LIMIT, 2, "the time limit, 2 s"))

    def test_a_game_that_stops_sending_frames_is_a_hang_with_the_link_open(self):
        self.plan([0, 1, 2], after="linger")
        began = time.monotonic()
        outcome = self.go(neutral, hang=0.5)
        self.assertLess(time.monotonic() - began, 5)  # not the 30 s of the run
        self.assertEqual((outcome.reason, outcome.frames, outcome.last_frame), (bot_link.HANG, 3, 2))
        self.assertEqual(outcome.detail, "no frame for 0.5 s after frame 2")
        self.assertEqual(self.record()["link_at_term"], "open")
        self.assertNotIn("hung up", (outcome.run_dir / "stdout.txt").read_text())

    def test_the_hang_clock_starts_at_the_connect(self):
        self.plan([], after="linger")
        outcome = self.go(neutral, hang=0.5)
        self.assertEqual((outcome.reason, outcome.frames, outcome.last_frame), (bot_link.HANG, 0, None))
        self.assertEqual(outcome.detail, "no frame for 0.5 s after it connected")

    def test_the_time_the_bot_takes_is_not_the_games_hang(self):
        self.plan([0, 1, 2])

        def slow(link: Link) -> dict[int, Pad]:
            time.sleep(0.4)
            return {1: Pad()}

        outcome = self.go(slow, hang=0.3)
        self.assertEqual((outcome.reason, outcome.frames), (bot_link.GAME_EXITED, 3))

    def test_a_game_that_never_connects_says_what_probe_said_and_a_hang_is_not_asked_of_it(self):
        self.plan([], refuse="no /x/build/dragoon; build the game first")
        outcome = self.go(neutral, hang=0.5)
        self.assertEqual((outcome.reason, outcome.frames, outcome.last_frame), (bot_link.NEVER_LINKED, 0, None))
        self.assertEqual(outcome.detail, "no /x/build/dragoon; build the game first")

    def test_a_line_that_is_not_a_frame_is_a_bad_link(self):
        self.plan([0], after="garbage")
        outcome = self.go(neutral)
        self.assertEqual((outcome.reason, outcome.frames), (bot_link.BAD_LINK, 1))
        self.assertIn("b'hello\\n'", outcome.detail)

    def test_a_reply_that_is_not_data_is_a_bad_link(self):
        self.plan([0], bad_data=True)
        outcome = self.go(lambda link: link.read(0x80000000, 1) and {1: Pad()})  # type: ignore[arg-type]
        self.assertEqual(outcome.reason, bot_link.BAD_LINK)
        self.assertIn("nope", outcome.detail)

    def test_a_reply_cut_off_partway_through_a_line_is_the_game_ending_and_not_a_bad_link(self):
        self.plan([0, 1], partial_data=True)
        later: list[int] = []

        def bot(link: Link) -> dict[int, Pad]:
            link.read(0x80000000, 2)
            later.append(link.frame)
            return {1: Pad()}

        outcome = self.go(bot)
        self.assertEqual((outcome.reason, outcome.frames, later), (bot_link.GAME_EXITED, 0, []))

    def test_a_game_that_is_gone_when_the_pads_go_out_is_the_game_ending_and_not_an_error(self):
        self.plan([0, 1, 2], die_at=1)

        def bot(link: Link) -> dict[int, Pad]:
            if link.frame == 1:
                time.sleep(0.3)  # the game exits meanwhile, so the send finds nobody
            return {1: Pad()}

        outcome = self.go(bot)
        self.assertEqual((outcome.reason, outcome.frames, outcome.last_frame), (bot_link.GAME_EXITED, 1, 1))
        self.assertIsNone(outcome.error)

    def test_what_an_earlier_run_of_the_name_left_is_not_this_runs(self):
        run_dir = self.run_dir()
        (run_dir / "session" / "inputs").mkdir(parents=True)
        write_file(run_dir, "panic.txt", "guest panic: old.c:1: old\n")
        write_file(run_dir, "stdout.txt", "[bot] frame 9: the bot hung up\nFATAL: old\n")
        write_file(run_dir / "session", "session.json", "{}")
        write_file(run_dir / "session" / "inputs", "inputs.txt", "# end 9 9\n")
        self.plan([0])
        outcome = self.go(neutral)
        self.assertEqual(outcome.reason, bot_link.GAME_EXITED)
        self.assertFalse((run_dir / "panic.txt").exists())
        self.assertEqual(outcome.input_log, run_dir / "session" / "inputs")  # not a run-2 beside the old one
        self.assertFalse((run_dir / "session" / "run-2").exists())
        self.assertNotIn("# end 9 9", (outcome.input_log / "inputs.txt").read_text())

    def test_a_game_that_resets_connects_again_and_the_bot_goes_on_with_the_new_input_log(self):
        self.plan([0, 1, 2], after="reset", then={"frames": [0, 1]})
        seen: list[tuple[int, int]] = []

        def bot(link: Link) -> dict[int, Pad]:
            seen.append((link.starts, link.frame))
            return {1: Pad()}

        outcome = self.go(bot)
        self.assertEqual(seen, [(1, 0), (1, 1), (1, 2), (2, 0), (2, 1)])
        self.assertEqual((outcome.reason, outcome.frames, outcome.last_frame), (bot_link.GAME_EXITED, 5, 1))
        self.assertEqual(outcome.input_log, self.run_dir() / "session" / "run-2" / "inputs")

    def test_a_run_removes_its_socket_and_leaves_the_lock(self):
        self.plan([0])
        self.go(neutral)
        sock = socket_path(self.run_dir())
        self.assertFalse(os.path.exists(sock))
        self.assertTrue(os.path.exists(sock + ".lock"))

    def test_ctrl_c_in_the_bot_ends_the_game_too(self):
        self.plan(list(range(10)), ignore_hangup=True)

        def bot(link: Link) -> dict[int, Pad]:
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.go(bot)
        pid = int((self.run_dir() / "pid.txt").read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        self.assertFalse(os.path.exists(socket_path(self.run_dir())))


class WaitClosedTest(unittest.TestCase):
    def link(self) -> tuple[Link, socket.socket]:
        ours, theirs = socket.socketpair()
        link = Link()
        link._attach(ours)
        self.addCleanup(link._detach)
        self.addCleanup(theirs.close)
        return link, theirs

    def test_it_returns_when_the_game_closes_the_link_and_not_before(self):
        link, game = self.link()
        threading.Timer(0.3, game.close).start()
        began = time.monotonic()
        bot_link._wait_closed(link)
        self.assertGreaterEqual(time.monotonic() - began, 0.25)
        self.assertLess(time.monotonic() - began, bot_link.CLOSE_WAIT)

    def test_it_reads_past_what_the_game_still_sends(self):
        link, game = self.link()
        game.sendall(b"frame 9\nframe 10\n")
        threading.Timer(0.2, game.close).start()
        bot_link._wait_closed(link)

    def test_it_gives_up_on_a_game_that_never_closes_it(self):
        link, _ = self.link()
        began = time.monotonic()
        with mock.patch.object(bot_link, "CLOSE_WAIT", 0.3):
            bot_link._wait_closed(link)
        self.assertLess(time.monotonic() - began, 2)


class SetupTest(FakeProbeCase):
    def test_probe_gets_its_arguments_in_order_with_the_deadline_slack_and_the_socket_last(self):
        self.plan([0])
        self.go(lambda link: {1: Pad(), 2: Pad()}, name="t", seconds=17, pads=2, script="120:A:5", every=30,
                settings=["--exit-after=900", "GCN_FRAMETIME=1"])
        sock = socket_path(self.run_dir())
        self.assertEqual(self.record()["argv"],
                         ["t", str(17 + bot_link.DEADLINE_SLACK), "120:A:5", "30", "--exit-after=900",
                          "GCN_FRAMETIME=1", f"GCN_SESSION={self.run_dir() / 'session'}", "GCN_WAV=",
                          "GCN_AIDWAV=", "--pads=2", f"GCN_BOT={sock}"])

    def test_every_none_is_an_interval_no_run_reaches(self):
        self.plan([0])
        self.go(neutral, every=None)
        self.assertEqual(self.record()["argv"][3], str(bot_link.NO_DUMPS))
        self.assertGreaterEqual(bot_link.NO_DUMPS, 10 ** 9)

    def test_the_run_directory_is_beside_the_probe_as_probe_sh_finds_it(self):
        self.assertEqual(bot_link.run_directory("t", self.probe), self.run_dir())
        self.assertEqual(bot_link.run_directory("t"), bot_link.PROBE.parent.parent / "build" / "probe" / "t")
        self.plan([0])
        self.assertEqual(self.go(neutral).run_dir, self.run_dir())

    def test_a_session_the_run_makes_records_no_audio_unless_settings_say_where(self):
        self.plan([0])
        for settings, expected in ((["GCN_WAV=/x/out.wav"], ["GCN_WAV=/x/out.wav", "GCN_AIDWAV="]),
                                   (["GCN_AIDWAV=/x/aid.raw"], ["GCN_AIDWAV=/x/aid.raw", "GCN_WAV="]),
                                   (["GCN_WAV=/x/out.wav", "GCN_AIDWAV=/x/aid.raw"],
                                    ["GCN_WAV=/x/out.wav", "GCN_AIDWAV=/x/aid.raw"])):
            with self.subTest(settings=settings):
                self.go(neutral, settings=settings)
                argv = self.record()["argv"]
                self.assertEqual(sorted(a for a in argv if a.startswith(("GCN_WAV=", "GCN_AIDWAV="))),
                                 sorted(expected))
                self.assertEqual(len([a for a in argv if a.startswith("GCN_WAV=")]), 1)  # the caller's, not both
                self.assertEqual(len([a for a in argv if a.startswith("GCN_AIDWAV=")]), 1)

    def test_a_session_the_caller_names_is_left_to_the_engine_to_record_as_it_does(self):
        self.plan([0])
        self.go(neutral, settings=[f"GCN_SESSION={self.root / 'mine'}"])
        argv = self.record()["argv"]
        self.assertFalse([a for a in argv if a.startswith(("GCN_WAV", "GCN_AIDWAV"))])

    def test_a_session_in_settings_is_the_runs_and_a_relative_one_is_taken_from_the_run_directory(self):
        self.plan([0])
        mine = self.root / "mine"
        outcome = self.go(neutral, settings=[f"GCN_SESSION={mine}"])
        self.assertEqual(outcome.input_log, mine / "inputs")
        self.assertEqual(self.record()["argv"].count(f"GCN_SESSION={mine}"), 1)
        self.assertFalse((self.run_dir() / "session").exists())
        outcome = self.go(neutral, name="u", settings=["GCN_SESSION=rel"])
        self.assertEqual(outcome.input_log, self.run_dir("u") / "rel" / "inputs")

    def test_an_empty_session_in_settings_is_not_one(self):
        self.plan([0])
        outcome = self.go(neutral, settings=["GCN_SESSION="])
        self.assertEqual(outcome.input_log, self.run_dir() / "session" / "inputs")
        argv = self.record()["argv"]
        self.assertIn(f"GCN_SESSION={self.run_dir() / 'session'}", argv)
        self.assertIn("GCN_WAV=", argv)  # the run's own session, so it records no audio

    def test_arguments_the_run_sets_itself_are_refused(self):
        for settings in (["GCN_BOT=/x"], ["--pads=2"]):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                self.go(neutral, settings=settings)
        for kwargs in ({"name": "../x"}, {"name": ""}, {"name": ".hidden"}, {"pads": 0}, {"pads": 5},
                       {"seconds": 0}, {"every": 0}, {"hang": 0}, {"hang": -1.0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.go(neutral, **kwargs)
        self.assertFalse((self.root / "build").exists())

    def test_a_short_path_stays_in_the_run_directory(self):
        self.assertEqual(socket_path(Path("/a/build/probe/t")), "/a/build/probe/t/bot.sock")

    def test_a_path_past_the_socket_limit_moves_to_a_short_one_per_directory(self):
        long = Path("/" + "d" * 90) / "build" / "probe" / "t"
        path = socket_path(long)
        self.assertTrue(path.startswith("/tmp/dragoon-bot-") and path.endswith(".sock"), path)
        self.assertLessEqual(len(os.fsencode(path)), bot_link.SOCKET_PATH_MAX)
        self.assertEqual(path, socket_path(long))
        self.assertNotEqual(path, socket_path(Path("/" + "d" * 90) / "build" / "probe" / "u"))
        edge = Path("/" + "e" * (bot_link.SOCKET_PATH_MAX - len("/bot.sock") - 1))
        self.assertEqual(len(os.fsencode(str(edge / "bot.sock"))), bot_link.SOCKET_PATH_MAX)
        self.assertEqual(socket_path(edge), str(edge / "bot.sock"))
        self.assertTrue(socket_path(Path(str(edge) + "e")).startswith("/tmp/"))

    def test_a_run_in_a_long_directory_connects_over_the_short_path(self):
        long = self.root / ("x" * 60)
        self.probe = self.tree(long)
        self.plan([0, 1])
        sock = socket_path(long / "build" / "probe" / "t")
        self.addCleanup(lambda: Path(sock + ".lock").unlink(missing_ok=True))
        outcome = self.go(neutral)
        self.assertEqual((outcome.reason, outcome.frames), (bot_link.GAME_EXITED, 2))
        record = json.loads((long / "build" / "probe" / "t" / "record.json").read_text())
        self.assertEqual(record["gcn_bot"], sock)
        self.assertFalse(os.path.exists(sock))

    def test_a_second_listener_on_one_socket_is_refused_and_leaves_both_files(self):
        path = str(self.root / "bot.sock")
        first, lock = bot_link._listen(path)
        try:
            with self.assertRaises(OSError):
                bot_link._listen(path)
            self.assertTrue(os.path.exists(path))
            client = socket.socket(socket.AF_UNIX)
            client.connect(path)  # the first is still the one listening
            client.close()
        finally:
            first.close()
            os.close(lock)

    def test_a_socket_file_an_earlier_run_left_is_replaced_and_another_file_is_not(self):
        path = str(self.root / "bot.sock")
        old = socket.socket(socket.AF_UNIX)
        old.bind(path)
        old.close()  # the file stays
        listener, lock = bot_link._listen(path)
        listener.close()
        os.close(lock)
        os.unlink(path)
        write_file(self.root, "bot.sock", "not a socket")
        with self.assertRaises(OSError):
            bot_link._listen(path)
        self.assertEqual(Path(path).read_text(), "not a socket")

    def test_a_run_whose_socket_is_taken_is_refused_before_it_touches_the_directory(self):
        run_dir = self.run_dir()
        run_dir.mkdir(parents=True)
        write_file(run_dir, "stdout.txt", "the other run's")
        self.plan([0])
        listener, lock = bot_link._listen(socket_path(run_dir))
        try:
            with self.assertRaises(LinkSetupError):
                self.go(neutral)
        finally:
            listener.close()
            os.close(lock)
        self.assertEqual((run_dir / "stdout.txt").read_text(), "the other run's")

    def test_a_probe_that_is_missing_or_will_not_run_is_a_setup_error(self):
        with self.assertRaises(LinkSetupError):
            run("t", 5, neutral, probe=self.root / "tools" / "nothing.sh")
        self.probe.chmod(0o644)
        with self.assertRaises(LinkSetupError):
            self.go(neutral)
        self.assertFalse(os.path.exists(socket_path(self.run_dir())))


class RealProbeTest(unittest.TestCase):
    def tree(self, tmp: str) -> tuple[Path, Path]:
        """The real probe.sh over FAKE_GAME in a temp tree: the tree's root and its probe.sh."""
        root = Path(tmp).resolve()
        (root / "tools").mkdir()
        (root / "build").mkdir()
        probe = root / "tools" / "probe.sh"
        shutil.copy(REAL_PROBE, probe)
        game = write_file(root / "build", "dragoon", FAKE_GAME.replace("@PYTHON@", sys.executable))
        game.chmod(0o755)
        return root, probe

    def test_a_game_that_exited_is_not_a_hang_however_late_probe_sh_notices(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, probe = self.tree(tmp)
            began = time.monotonic()
            outcome = run("t", 20, neutral, settings=["--exit-after=1500"], hang=0.5, probe=probe)
            took = time.monotonic() - began
        self.assertEqual((outcome.reason, outcome.frames), (bot_link.EXIT_AFTER, 3))
        self.assertLess(took, 10)  # probe.sh's next one-second tick, not the run's 20 s

    def test_gcn_bot_the_session_and_the_settings_pass_through_probe_sh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, probe = self.tree(tmp)
            outcome = run("t", 20, neutral, pads=2, script="120:A:5", every=30,
                          settings=["--exit-after=1500", "GCN_FRAMETIME=1"], probe=probe)
            record = json.loads((root / "build" / "probe" / "t" / "record.json").read_text())
        self.assertEqual((outcome.reason, outcome.frames, outcome.last_frame), (bot_link.EXIT_AFTER, 3, 2))
        self.assertEqual(outcome.detail, "--exit-after=1500")
        self.assertEqual(outcome.input_log, root / "build" / "probe" / "t" / "session" / "inputs")
        self.assertEqual(record["env"]["GCN_BOT"], socket_path(root / "build" / "probe" / "t"))
        self.assertEqual(record["env"]["GCN_SESSION"], str(root / "build" / "probe" / "t" / "session"))
        self.assertEqual(record["env"]["GCN_INPUT"], "120:A:5")
        self.assertEqual(record["env"]["GCN_FRAMETIME"], "1")
        self.assertEqual((record["env"]["GCN_WAV"], record["env"]["GCN_AIDWAV"]), ("", ""))  # set, and empty
        self.assertIn("--pads=2", record["argv"])
        self.assertIn("--exit-after=1500", record["argv"])
        self.assertIn("--dump-every=30", record["argv"])
        self.assertNotIn("--no-input-log", record["argv"])  # a session keeps the log probe.sh otherwise drops
        self.assertNotIn("--bot", " ".join(record["argv"]))


class CommandTest(FakeProbeCase):
    def main(self, *args: str) -> tuple[int, str, str]:
        return run_main(bot_link.main, "--probe", str(self.probe), *args)

    def test_a_run_that_ended_by_itself_exits_0_and_prints_where_how_and_the_input_log(self):
        self.plan([0, 1, 2])
        code, out, err = self.main("--pads", "1", "t", "30", "--", "--exit-after=2")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, f"{self.run_dir()}: exit_after, 3 frames answered, the last frame 2\n"
                              "  --exit-after=2\n"
                              f"  input log {self.run_dir()}/session/inputs\n")
        self.assertIn("--exit-after=2", self.record()["argv"])

    def test_the_time_limit_and_a_shutdown_exit_0(self):
        self.plan([0], after="linger")
        self.assertEqual(self.main("--hang", "0", "t", "1")[0], 0)  # --hang 0 is never
        self.plan([0, 1], after="shutdown")
        code, out, _ = self.main("t", "30")
        self.assertEqual(code, 0)
        self.assertIn(": shutdown, 2 frames answered", out)

    def test_a_game_that_exited_exits_1_as_nothing_in_a_bot_run_asks_for_that(self):
        self.plan([0, 1])
        code, out, err = self.main("t", "30")
        self.assertEqual((code, err), (1, ""))
        self.assertIn(": game_exited, 2 frames answered", out)
        self.assertIn("  the game ended at frame 1\n", out)
        self.assertNotIn(bot_link.GAME_EXITED, bot_link.CLEAN)

    def test_a_game_that_died_or_hung_or_stopped_exits_1(self):
        self.plan([0], after="died")
        code, out, _ = self.main("t", "30")
        self.assertEqual(code, 1)
        self.assertIn(": game_died, 1 frames answered", out)
        self.plan([0], after="linger")
        code, out, _ = self.main("--hang", "0.5", "t", "30")
        self.assertEqual(code, 1)
        self.assertIn(": hang, 1 frames answered", out)
        self.plan([4])
        self.assertEqual(self.main("--send", "2", "t", "30")[0], 1)

    def test_a_game_that_never_connected_exits_2_on_stderr(self):
        self.plan([], refuse="no build/dragoon; build the game first")
        code, out, err = self.main("t", "30")
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err, "bot_link.py: the game never connected: no build/dragoon; build the game first\n")

    def test_a_game_that_had_not_connected_at_the_time_limit_exits_2_on_stderr(self):
        self.plan([0], connect_after=20)
        code, out, err = self.main("t", "1")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("bot_link.py: the game never connected: the game hadn't connected when the time limit came", err)

    def test_a_game_that_did_not_connect_again_after_a_reset_exits_1_as_a_hang(self):
        self.plan([0], after="reset", then={"frames": [0], "connect_after": 20})
        code, out, _ = self.main("--hang", "0.5", "t", "30")
        self.assertEqual(code, 1)
        self.assertIn(": hang, 1 frames answered", out)

    def test_a_stop_exits_1_with_the_engines_line(self):
        self.plan([4])
        code, out, _ = self.main("--watch", "817FFFFF:2", "t", "30")
        self.assertEqual(code, 1)
        self.assertIn(": engine_stop, 0 frames answered, the last frame 4\n", out)
        self.assertIn('  [bot] frame 4: a read outside RAM, 80000000 to 817FFFFF: "read 817FFFFF 2"', out)

    def test_send_makes_the_bot_send_other_ports_than_the_game_drives(self):
        self.plan([4])
        code, out, _ = self.main("--send", "2", "t", "30")
        self.assertEqual(code, 1)
        self.assertIn("port 2 isn't one the bot drives (--pads=1)", out)
        code, out, _ = self.main("--pads", "2", "--send", "1", "t", "30")
        self.assertEqual(code, 1)
        self.assertIn("done without a pad line for port 2", out)

    def test_watch_prints_a_value_when_it_changes(self):
        self.plan([5, 6, 7], after="shutdown")
        code, out, _ = self.main("--watch", "80000010:2", "t", "30")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[:1], ["frame 5 80000010 1011"])
        self.assertEqual(len([line for line in out.splitlines() if line.startswith("frame ")]), 1)
        self.plan([5, 6, 7], moving=True)
        _, out, _ = self.main("--watch", "80000010:2", "t", "30")
        self.assertEqual([line for line in out.splitlines() if line.startswith("frame ")],
                         ["frame 5 80000010 1516", "frame 6 80000010 1617", "frame 7 80000010 1718"])

    def test_the_script_and_every_reach_probe(self):
        self.plan([0])
        self.main("--script", "tests/routes/menu.txt", "--every", "20", "t", "9")
        self.assertEqual(self.record()["argv"][:4], ["t", str(9 + bot_link.DEADLINE_SLACK),
                                                      "tests/routes/menu.txt", "20"])

    def test_a_run_that_could_not_start_exits_2_on_stderr(self):
        code, out, err = run_main(bot_link.main, "--probe", str(self.root / "nothing.sh"), "t", "30")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("bot_link.py: no ", err)
        self.assertEqual(self.main("--watch", "zz:2", "t", "30")[0], 2)
        self.assertEqual(self.main("--hang", "-1", "t", "30")[0], 2)
        code, _, err = self.main("t", "30", "--", "--pads=2")
        self.assertEqual(code, 2)
        self.assertIn("run sets GCN_BOT and --pads itself", err)


class CommandHelperTest(unittest.TestCase):
    def parser(self, **kwargs) -> argparse.ArgumentParser:
        ap = argparse.ArgumentParser(prog="tool.py")
        bot_link.add_play_arguments(ap)
        bot_link.add_run_arguments(ap, **kwargs)
        return ap

    def test_settings_are_what_follows_the_first_double_dash(self):
        self.assertEqual(bot_link.split_settings(["a", "--", "--exit-after=5", "--", "x"]),
                         (["a"], ["--exit-after=5", "--", "x"]))
        self.assertEqual(bot_link.split_settings(("a", "b")), (["a", "b"], []))

    def test_the_run_arguments_become_runs_keywords(self):
        ap = self.parser()
        args = ap.parse_args(["--script", "r.txt", "--pads", "2", "--every", "9", "--hang", "4", "--probe", "p"])
        self.assertEqual(bot_link.run_options(ap, args),
                         {"pads": 2, "script": "r.txt", "every": 9, "hang": 4.0, "probe": "p"})
        args = ap.parse_args(["--hang", "0"])
        self.assertEqual(bot_link.run_options(ap, args),
                         {"pads": 1, "script": "", "every": 60, "hang": None, "probe": None})
        ap = self.parser(every=None)
        self.assertIsNone(bot_link.run_options(ap, ap.parse_args([]))["every"])

    def test_a_negative_hang_is_the_parsers_error(self):
        ap = self.parser()
        code, _, err = run_main(lambda argv: bot_link.run_options(ap, ap.parse_args(argv)), "--hang", "-1")
        self.assertEqual(code, 2)
        self.assertIn("tool.py: error: --hang is a number of seconds from 0", err)

    def test_the_outcome_prints_where_how_and_the_input_log(self):
        outcome = Outcome(3, 2, bot_link.EXIT_AFTER, "--exit-after=2", Path("/r"), Path("/r/session/inputs"))
        code, out, err = run_main(lambda argv: bot_link.print_outcome(outcome, "tool.py"))
        self.assertEqual((out, err), ("/r: exit_after, 3 frames answered, the last frame 2\n  --exit-after=2\n"
                                      "  input log /r/session/inputs\n", ""))
        outcome = Outcome(0, None, bot_link.GAME_DIED, "gone", Path("/r"))
        self.assertEqual(run_main(lambda argv: bot_link.print_outcome(outcome, "tool.py"))[1],
                         "/r: game_died, 0 frames answered, no frame\n  gone\n")

    def test_a_game_that_never_connected_is_the_tools_error(self):
        outcome = Outcome(0, None, bot_link.NEVER_LINKED, "no build/dragoon", Path("/r"))
        _, out, err = run_main(lambda argv: bot_link.print_outcome(outcome, "tool.py"))
        self.assertEqual((out, err), ("", "tool.py: the game never connected: no build/dragoon\n"))


if __name__ == "__main__":
    unittest.main()
