"""A stand-in for probe.sh and the game, for the soak's tests.

`make_tree` writes a probe.sh into a temp tree's tools/ that plays the engine's side of the bot
link over testgame.FakeGame's menus, as `bot_link.run(probe=...)` runs it. It works in the same
build/probe/NAME/ the real probe.sh does, keeps a session whose input log ends in `# end 0 FRAME`
on every way out, says its `[session]`, `[reset]` and `[shaders]` lines in stdout.txt and puts a
counter at PICTURE_ADDR that stands in for the picture's hash. On SIGTERM it saves and exits at
once. It records what it saw in record.json. As the engine does, it ends the game once a
process has shown the frames of an `--exit-after=N` setting, and stops it on a `done` that
leaves out a port the bot drives. What it does besides play is in plan.json, which `set_plan`
writes beside tools/:

  "race"     frames a race lasts before the game ends it, 3000 by default
  "events"    a list of {"frame": N or "race": N, "process": P, "do": [ACTION, ...]}. It happens
              at frame N of process P (1 before a reset), or at the Nth frame of the first race
              the process plays, once. An ACTION is one of
                ["say", TEXT]            a line in stdout.txt
                ["panic"]                panic.txt, and the game ends
                ["exit"]                 the game ends on its own
                ["shutdown"]             the console shuts down and the game ends
                ["hang", SECONDS]        no frame for that long, with the link open
                ["reset", {"kind": "restart", "shaders_ms": 100, "connect_after": 0}]
                                         a console reset: the game starts again as the next
                                         process, with the `[shaders]` line a restart prints
                ["screen", MINOR]        the game stops on that screen and ignores the pads
                ["freeze_picture"]       the picture counter stops
  "refuse"    text for stderr; the game exits 2 without a game
  "connect_fails"  the game's failed connect, without one
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from testutil import write_file

TOOLS = Path(__file__).resolve().parent
PICTURE_ADDR = 0x80001000
ENGINE_SHA = "0123456789abcdef0123456789abcdef01234567"


def built_sha(process: int) -> str:
    """The `engine_sha` the fake writes in the session.json of its PROCESSth process."""
    return f"{ENGINE_SHA}-dirty{process}"

FAKE_ENGINE = r'''#!@PYTHON@
import atexit, json, os, signal, socket, struct, sys, time

sys.path.insert(0, "@TOOLS@")
import bot_menus
from bot_link import Pad
from testgame import FakeGame
from testutil import FakeLink

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
name, seconds, script, every, *settings = sys.argv[1:]
out = os.path.join(root, "build", "probe", name)
os.makedirs(out, exist_ok=True)
os.chdir(out)
with open(os.path.join(root, "plan.json")) as f:
    plan = json.load(f)


def setting(prefix, default=""):
    return ([s[len(prefix):] for s in settings if s.startswith(prefix)] or [default])[-1]


path = setting("GCN_BOT=")
ports = int(setting("--pads=", "1"))
session = setting("GCN_SESSION=")
exit_after = int(setting("--exit-after=", "0"))  # frames before the game ends, as the engine's flag does
process, frame, picture, picture_frozen, game_frozen = 1, 0, 0, False, False
conn = lines = log = None
fired = set()
link = FakeLink()
game = FakeGame(link, players=ports, race=plan.get("race", 3000))
with open("pid.txt", "w") as f:
    f.write(str(os.getpid()))


def save():
    rec = {"argv": sys.argv[1:], "settings": settings, "visited": game.visited, "started": game.started,
           "processes": process, "frame": frame}
    with open("record.json", "w") as f:
        json.dump(rec, f)


atexit.register(save)


def say(text, file="stdout.txt"):
    with open(file, "a") as f:
        f.write(text)


def begin_log():
    global log
    where = session
    if os.path.exists(os.path.join(where, "session.json")):
        n = 2
        while os.path.exists(os.path.join(where, "run-%d" % n, "session.json")):
            n += 1
        where = os.path.join(where, "run-%d" % n)
    os.makedirs(os.path.join(where, "inputs"))
    with open(os.path.join(where, "session.json"), "w") as f:
        json.dump({"engine_sha": "@ENGINE_SHA@-dirty%d" % process}, f)
    say("[session] %s\n" % where)
    log = open(os.path.join(where, "inputs", "inputs.txt"), "w")
    log.write("# gcn-recomp input log v5\n")
    log.flush()


def end_log():
    global log
    if log is not None:
        log.write("# end 0 %d\n" % frame)
        log.flush()
    log = None


def on_term(signum, stack):
    end_log()
    save()
    os._exit(0)


signal.signal(signal.SIGTERM, on_term)


def connect():
    global conn, lines
    conn = socket.socket(socket.AF_UNIX)
    conn.connect(path)
    lines = conn.makefile("rb")


def stop_game(code):
    end_log()
    save()
    sys.exit(code)


def reset(spec):
    global conn, lines, process, link, game, frame, game_frozen
    say("[reset] the game reset the console (%s, code 0)\n" % spec.get("kind", "restart"))
    end_log()
    lines.close()
    conn.close()
    process += 1
    frame = 0
    begin_log()
    say("[shaders] 70 programs from cache (0 from binaries, 70 compiled, 0 of them from the game's key list) "
        "in %d ms\n" % spec.get("shaders_ms", 100))
    time.sleep(spec.get("connect_after", 0))
    connect()
    link = FakeLink()
    game = FakeGame(link, players=ports, race=plan.get("race", 3000))
    game_frozen = False
    fired.clear()


def act(do):
    """Does DO. True if the game started again, so the frame count is a new one."""
    global picture_frozen, game_frozen
    for action in do:
        kind = action[0]
        if kind == "say":
            say(action[1] + "\n")
        elif kind == "panic":
            say("guest panic: foo.c:12: boom\nguest backtrace (innermost first):\n", "panic.txt")
            stop_game(1)
        elif kind == "exit":
            stop_game(0)
        elif kind == "shutdown":
            say("[reset] the game reset the console (shutdown, code 0)\n")
            stop_game(0)
        elif kind == "hang":
            time.sleep(action[1])
        elif kind == "reset":
            reset(action[1])
            return True
        elif kind == "screen":
            game_frozen = True
            link.set("scene.minor", action[1])
        elif kind == "freeze_picture":
            picture_frozen = True
    return False


def events():
    """Does what the plan says for this frame. True if the game started again."""
    for i, ev in enumerate(plan.get("events", [])):
        if ev.get("process", 1) != process or i in fired:
            continue
        if "frame" in ev:
            due = frame == ev["frame"]
        else:
            due = game.minor in bot_menus.PLAYING and game.raced == ev["race"]
        if due:
            fired.add(i)
            if act(ev["do"]):
                return True
    return False


def step(pads):
    conn.sendall(("frame %d\n" % frame).encode())
    while True:
        line = lines.readline().decode()
        if not line:
            say("[bot] frame %d: the bot hung up\n" % frame)
            stop_game(1)
        words = line.split()
        if words[0] == "read":
            data = link.read(int(words[1], 16), int(words[2]))
            conn.sendall(b"data " + data.hex().encode() + b"\n")
        elif words[0] == "pad":
            b, sx, sy, cx, cy, l, r = int(words[2], 16), *map(int, words[3:9])
            pads[int(words[1])] = Pad(buttons=b, sx=sx, sy=sy, cx=cx, cy=cy, l=l, r=r)
        elif words[0] == "done":
            for port in range(1, ports + 1):
                if port not in pads:  # the engine stops the game on a port the bot drives and left out
                    say('[bot] frame %d: done without a pad line for port %d, which the bot drives: "%s"\n'
                        % (frame, port, line.strip()))
                    stop_game(1)
            return


if plan.get("refuse"):
    print(plan["refuse"], file=sys.stderr)
    sys.exit(2)
begin_log()
if plan.get("connect_fails"):
    say("--bot %s: can't connect: Connection refused\n" % path)
    stop_game(1)
connect()
while True:
    if exit_after and frame >= exit_after:
        stop_game(0)
    if events():
        continue
    link.frame = frame
    pads = {}
    step(pads)
    if not game_frozen:
        game.advance(pads)
    if not picture_frozen:
        picture += 1
    link.put(@PICTURE@, struct.pack(">I", picture))
    frame += 1
'''


def make_tree(root: Path) -> Path:
    """Writes the fake probe.sh into ROOT/tools/ and returns its path."""
    text = (FAKE_ENGINE.replace("@PYTHON@", sys.executable).replace("@TOOLS@", str(TOOLS))
            .replace("@PICTURE@", str(PICTURE_ADDR)).replace("@ENGINE_SHA@", ENGINE_SHA))
    (root / "tools").mkdir(parents=True, exist_ok=True)
    probe = write_file(root / "tools", "probe.sh", text)
    probe.chmod(0o755)
    return probe


def set_plan(root: Path, **plan: object) -> None:
    """Writes the plan the fake game follows (see the head of this file)."""
    write_file(root, "plan.json", json.dumps(plan))


def axv(n: int, kind: str, pb: str = "80579F88", loop: str = "01808A02", end: str = "018189FF") -> str:
    """An [axv] line for a voice with no loop flag, at a music stream's slot unless told otherwise."""
    return (f"[axv] list={n} pb={pb} {kind} run=1 looping=0 stream=0 fmt=00 src=0 loop={loop} end={end} "
            f"cur=00DD0195 ratio=00010000")
