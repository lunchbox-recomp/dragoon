from __future__ import annotations

import dataclasses
import json
import os
import shutil
import socket
import sys
import tempfile
import unittest
from pathlib import Path

import bot_link
from bot_link import BUTTONS, Link, LinkSetupError, Outcome, Pad, encode_pads, run, socket_path
from testutil import run_main, write_file

REAL_PROBE = Path(__file__).resolve().parent / "probe.sh"

# A stand-in for probe.sh and the game behind it. It takes probe.sh's arguments, works in the
# same build/probe/NAME/, and plays the engine's side of the bot link as plan.json beside tools/
# says, with the checks gcn-recomp's bot_link.cpp makes that a test here needs. It records what
# it saw in record.json. A plan is {"frames": [N, ...]} and any of these:
#   "after"          what it does once its frames are done: "exit" (the default), "linger" (waits
#                    out SECONDS, as a game does until probe.sh kills it), "panic", "fatal",
#                    "garbage" (sends a line that isn't a frame) or "reset" (hangs up and
#                    connects again to play "then", another plan)
#   "refuse"         the text of a refusal on stderr; it exits 2 without a game, as probe.sh does
#   "connect_fails"  the game's failed connect, without one
#   "refuse_reads"   stops the game at the first read, as a read outside RAM does
#   "bad_data"       answers a read with what isn't a data line
#   "ignore_hangup"  waits instead of exiting when the bot hangs up
#   "moving"         makes RAM change from frame to frame
FAKE_PROBE = r'''#!@PYTHON@
import atexit, json, os, socket, sys, time

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
name, seconds, script, every, *settings = sys.argv[1:]
out = os.path.join(root, "build", "probe", name)
os.makedirs(out, exist_ok=True)
os.chdir(out)
with open(os.path.join(root, "plan.json")) as f:
    plan = json.load(f)
path = [s[len("GCN_BOT="):] for s in settings if s.startswith("GCN_BOT=")][0]
ports = int(([s[len("--pads="):] for s in settings if s.startswith("--pads=")] or ["1"])[-1])
rec = {"argv": sys.argv[1:], "events": [], "starts": 0, "gcn_bot": path}
with open("pid.txt", "w") as f:
    f.write(str(os.getpid()))


def save():
    with open("record.json", "w") as f:
        json.dump(rec, f)


atexit.register(save)


def say(text, file="stdout.txt"):
    with open(file, "a") as f:
        f.write(text)


def stop(frame, why):
    say("[bot] frame %d: %s\n" % (frame, why))
    sys.exit(1)


def ram(addr, length, frame):
    shift = frame if plan.get("moving") else 0
    return bytes((addr + i + shift) & 255 for i in range(length))


def step(conn, lines, frame):
    conn.sendall(("frame %d\n" % frame).encode())
    rec["events"].append("frame %d" % frame)
    have = set()
    while True:
        line = lines.readline().decode()
        if not line:
            if plan.get("ignore_hangup"):
                time.sleep(20)
            stop(frame, "the bot hung up")
        line = line.rstrip("\n")
        rec["events"].append(line)
        words = line.split()
        if words[0] == "read":
            if plan.get("refuse_reads"):
                stop(frame, 'a read outside RAM, 80000000 to 817FFFFF: "%s"' % line)
            if plan.get("bad_data"):
                conn.sendall(b"nope\n")
                continue
            conn.sendall(b"data " + ram(int(words[1], 16), int(words[2]), frame).hex().encode() + b"\n")
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


def play(frames):
    conn = socket.socket(socket.AF_UNIX)
    conn.connect(path)
    rec["starts"] += 1
    lines = conn.makefile("rb")
    for frame in frames:
        step(conn, lines, frame)
    return conn, lines


if plan.get("refuse"):
    print(plan["refuse"], file=sys.stderr)
    sys.exit(2)
if plan.get("connect_fails"):
    say("--bot %s: can't connect: Connection refused\n" % path)
    sys.exit(1)
conn, lines = play(plan["frames"])
after = plan.get("after", "exit")
if after == "linger":
    time.sleep(int(seconds))
elif after == "panic":
    say("guest panic: foo.c:12: boom\nguest backtrace (innermost first):\n", "panic.txt")
elif after == "fatal":
    say("FATAL: call_indirect: no function at 00000000\n")
elif after == "garbage":
    conn.sendall(b"hello\n")
    lines.readline()
elif after == "reset":
    lines.close()
    conn.close()
    play(plan["then"]["frames"])
'''

# A stand-in for the game alone, for probe.sh itself to run in build/dragoon.
FAKE_GAME = r'''#!@PYTHON@
import json, os, socket, sys

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

    def record(self, name: str = "t") -> dict:
        return json.loads((self.root / "build" / "probe" / name / "record.json").read_text())


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
        self.assertEqual((outcome.reason, outcome.frames), (bot_link.GAME_ENDED, 2))
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


class OutcomeTest(FakeProbeCase):
    def test_a_stop_the_engine_reports_is_its_own_line(self):
        self.plan([3, 4], refuse_reads=True)
        calls: list[int] = []

        def bot(link: Link) -> dict[int, Pad]:
            calls.append(link.frame)
            link.read(0x817FFFFF, 2)
            return {1: Pad()}

        outcome = self.go(bot)
        self.assertEqual(calls, [3])  # the read ended the run, and the bot isn't called again
        self.assertEqual((outcome.reason, outcome.frames, outcome.last_frame), (bot_link.ENGINE_STOP, 0, 3))
        self.assertEqual(outcome.detail, '[bot] frame 3: a read outside RAM, 80000000 to 817FFFFF: '
                                         '"read 817FFFFF 2"')
        self.assertIsNone(outcome.error)
        self.assertEqual(outcome.run_dir, self.root / "build" / "probe" / "t")

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

    def test_a_bot_that_catches_exceptions_still_stops_when_the_engine_does(self):
        self.plan([3], refuse_reads=True)

        def bot(link: Link) -> dict[int, Pad]:
            try:
                link.read(0x80000000, 1)
            except Exception:
                pass
            return {1: Pad()}

        self.assertEqual(self.go(bot).reason, bot_link.ENGINE_STOP)

    def test_a_game_that_exits_after_its_frames_is_a_game_that_ended(self):
        self.plan([0, 1, 2])
        outcome = self.go(neutral, settings=["--exit-after=1500"])
        self.assertEqual((outcome.reason, outcome.frames, outcome.last_frame), (bot_link.GAME_ENDED, 3, 2))
        self.assertEqual(outcome.detail, "--exit-after=1500")

    def test_a_game_that_exits_by_itself_says_so(self):
        self.plan([0])
        outcome = self.go(neutral)
        self.assertEqual((outcome.reason, outcome.detail), (bot_link.GAME_ENDED, "the game exited"))

    def test_a_game_that_runs_to_the_time_limit_is_a_game_that_ended(self):
        self.plan([0, 1], after="linger")
        outcome = self.go(neutral, seconds=1, settings=["--exit-after=1500"])
        self.assertEqual((outcome.reason, outcome.frames), (bot_link.GAME_ENDED, 2))
        self.assertEqual(outcome.detail, "the time limit, 1 s")

    def test_a_game_that_never_connects_says_what_probe_said(self):
        self.plan([], refuse="no /x/build/dragoon; build the game first")
        outcome = self.go(neutral)
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

    def test_what_an_earlier_run_of_the_name_left_is_not_this_runs(self):
        run_dir = self.root / "build" / "probe" / "t"
        run_dir.mkdir(parents=True)
        write_file(run_dir, "panic.txt", "guest panic: old.c:1: old\n")
        write_file(run_dir, "stdout.txt", "[bot] frame 9: the bot hung up\nFATAL: old\n")
        self.plan([0])
        outcome = self.go(neutral)
        self.assertEqual(outcome.reason, bot_link.GAME_ENDED)
        self.assertFalse((run_dir / "panic.txt").exists())

    def test_a_game_that_resets_connects_again_and_the_bot_goes_on(self):
        self.plan([0, 1, 2], after="reset", then={"frames": [0, 1]})
        seen: list[tuple[int, int]] = []

        def bot(link: Link) -> dict[int, Pad]:
            seen.append((link.starts, link.frame))
            return {1: Pad()}

        outcome = self.go(bot)
        self.assertEqual(seen, [(1, 0), (1, 1), (1, 2), (2, 0), (2, 1)])
        self.assertEqual((outcome.reason, outcome.frames, outcome.last_frame), (bot_link.GAME_ENDED, 5, 1))

    def test_a_run_removes_its_socket_and_leaves_the_lock(self):
        self.plan([0])
        self.go(neutral)
        sock = socket_path(self.root / "build" / "probe" / "t")
        self.assertFalse(os.path.exists(sock))
        self.assertTrue(os.path.exists(sock + ".lock"))

    def test_ctrl_c_in_the_bot_ends_the_game_too(self):
        self.plan(list(range(10)), ignore_hangup=True)

        def bot(link: Link) -> dict[int, Pad]:
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.go(bot)
        pid = int((self.root / "build" / "probe" / "t" / "pid.txt").read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        self.assertFalse(os.path.exists(socket_path(self.root / "build" / "probe" / "t")))


class SetupTest(FakeProbeCase):
    def test_probe_gets_its_arguments_in_order_with_the_socket_last(self):
        self.plan([0])
        self.go(lambda link: {1: Pad(), 2: Pad()}, name="t", seconds=17, pads=2, script="120:A:5", every=30,
                settings=["--exit-after=900", "GCN_SESSION=s"])
        argv = self.record()["argv"]
        sock = socket_path(self.root / "build" / "probe" / "t")
        self.assertEqual(argv, ["t", "17", "120:A:5", "30", "--exit-after=900", "GCN_SESSION=s",
                                "--pads=2", f"GCN_BOT={sock}"])

    def test_arguments_the_run_sets_itself_are_refused(self):
        for settings in (["GCN_BOT=/x"], ["--pads=2"]):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                self.go(neutral, settings=settings)
        for kwargs in ({"name": "../x"}, {"name": ""}, {"name": ".hidden"}, {"pads": 0}, {"pads": 5},
                       {"seconds": 0}, {"every": 0}):
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
        self.assertEqual((outcome.reason, outcome.frames), (bot_link.GAME_ENDED, 2))
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
        run_dir = self.root / "build" / "probe" / "t"
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
        self.assertFalse(os.path.exists(socket_path(self.root / "build" / "probe" / "t")))


class RealProbeTest(unittest.TestCase):
    def test_gcn_bot_and_the_settings_pass_through_probe_sh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "tools").mkdir()
            (root / "build").mkdir()
            probe = root / "tools" / "probe.sh"
            shutil.copy(REAL_PROBE, probe)
            game = write_file(root / "build", "dragoon", FAKE_GAME.replace("@PYTHON@", sys.executable))
            game.chmod(0o755)
            outcome = run("t", 20, neutral, pads=2, script="120:A:5", every=30,
                          settings=["--exit-after=1500", "GCN_FRAMETIME=1"], probe=probe)
            record = json.loads((root / "build" / "probe" / "t" / "record.json").read_text())
        self.assertEqual((outcome.reason, outcome.frames, outcome.last_frame), (bot_link.GAME_ENDED, 3, 2))
        self.assertEqual(outcome.detail, "--exit-after=1500")
        self.assertEqual(record["env"]["GCN_BOT"], socket_path(root / "build" / "probe" / "t"))
        self.assertEqual(record["env"]["GCN_INPUT"], "120:A:5")
        self.assertEqual(record["env"]["GCN_FRAMETIME"], "1")
        self.assertIn("--pads=2", record["argv"])
        self.assertIn("--exit-after=1500", record["argv"])
        self.assertIn("--dump-every=30", record["argv"])
        self.assertNotIn("--bot", " ".join(record["argv"]))


class CommandTest(FakeProbeCase):
    def main(self, *args: str) -> tuple[int, str, str]:
        return run_main(bot_link.main, "--probe", str(self.probe), *args)

    def test_a_game_that_ended_exits_0_and_prints_where_and_how(self):
        self.plan([0, 1, 2])
        code, out, err = self.main("--pads", "1", "t", "30", "--", "--exit-after=1500")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, f"{self.root}/build/probe/t: game_ended, 3 frames answered, the last frame 2\n"
                              "  --exit-after=1500\n")
        self.assertIn("--exit-after=1500", self.record()["argv"])

    def test_a_stop_exits_1_with_the_engines_line(self):
        self.plan([4], refuse_reads=True)
        code, out, _ = self.main("--watch", "80000000:1", "t", "30")
        self.assertEqual(code, 1)
        self.assertIn(": engine_stop, 0 frames answered, the last frame 4\n", out)
        self.assertIn('  [bot] frame 4: a read outside RAM, 80000000 to 817FFFFF: "read 80000000 1"', out)

    def test_send_makes_the_bot_send_other_ports_than_the_game_drives(self):
        self.plan([4])
        code, out, _ = self.main("--send", "2", "t", "30")
        self.assertEqual(code, 1)
        self.assertIn("port 2 isn't one the bot drives (--pads=1)", out)
        code, out, _ = self.main("--pads", "2", "--send", "1", "t", "30")
        self.assertEqual(code, 1)
        self.assertIn("done without a pad line for port 2", out)

    def test_watch_prints_a_value_when_it_changes(self):
        self.plan([5, 6, 7])
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
        self.assertEqual(self.record()["argv"][:4], ["t", "9", "tests/routes/menu.txt", "20"])

    def test_a_run_that_could_not_start_exits_2_on_stderr(self):
        code, out, err = run_main(bot_link.main, "--probe", str(self.root / "nothing.sh"), "t", "30")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("bot_link.py: no ", err)
        self.assertEqual(self.main("--watch", "zz:2", "t", "30")[0], 2)
        code, _, err = self.main("t", "30", "--", "--pads=2")
        self.assertEqual(code, 2)
        self.assertIn("run sets GCN_BOT and --pads itself", err)


if __name__ == "__main__":
    unittest.main()
