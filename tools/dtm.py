#!/usr/bin/env python3
"""How does a route's input play in Dolphin? Turn a route into a Dolphin input movie (.dtm).

Usage: dtm.py make ROUTE --out FILE --fields N [--timeline RAM_TXT] [--count-polls]
       dtm.py converge ROUTE ISO --fields N --dir DIR [--max K] [--disc SPEED] [--count-polls]
       dtm.py read FILE
       dtm.py polls RAM_TXT
       dtm.py presses ROUTE RAM_TXT
       dtm.py steps RAM_TXT [--at FRAME]...

A route (tests/routes/, read by routes.parse_route) says which buttons are down at which of the
game's own frames. Dragoon's input_script_apply puts them on the pad when the game reads it, by
gx::g_frames_submitted, the frames the game had finished before that read. A .dtm says what the
pad reads at each of Dolphin's polls of it, one 8-byte ControllerState a poll, from power-on.
Dolphin polls on its video clock, not on the game's frames, so make maps one onto the other in
two steps.

Polls to fields: the game sets the serial interface to poll twice a field from field 48 on, and
it does in every scene top-ride-grass passes through, from the title to the race. From field
48 on, poll i is made in field poll_field(i), POLLS a field, with POLL_SHIFT for the slower
polling before. That was counted, not read from the source: with --count-polls, make puts each
poll's number in the analog triggers, too little for the game's PADClamp to let through, and
polls reads a run that watches WATCH, which holds the game's queue of raw pad reads, and prints
the polls between the game's reads in each run of fields. It shows 2 a field throughout, with
the game reading either the field's first poll or the last one of the field before
(read_field). A field that shows 1 or 3 is the read landing the other side of a poll, and one
that shows 4 or 0 next to it is the same thing evened out.

Fields to game frames: the game draws fewer frames than fields while it loads, so a field isn't
a game frame. --timeline takes the game frames each field reached in an earlier run of the
movie (game_frames, from kar_ram.json's vi.renew_count). Each poll gets the route's input at the
game frame the field before its read had reached, as the engine gives it. The first movie has no
timeline and maps field f to frame f. converge plays a movie with dolphin_ref.py, makes the next
from that run and stops when one comes out byte for byte the same as the one it played, or after
--max runs. How many it takes depends on where it starts. presses shows where the game read each
press, from the same queue, against the frame the route gives it.

The header (HEADER, from Movie.h at Dolphin 2609a) is GKYE01's, pad 1 only, from power-on with no
savestate, and the RTC at RTC, the dolphin-ref config's own CustomRTCValue. bSaveConfig is off,
so the run's config, not the movie, picks the CPU core, the DSP and the cards (dolphin_ref.py's
CONFIG) and its --disc the disc speed. The disc's MD5 is zeros, which skips Dolphin's check.
tickCount is twice the CPU ticks of the movie's fields, so playback ends when the input runs
out, not on ticks.

read prints a .dtm's header and the polls where the pad changes. steps prints a run's scene
word changes with the field and game frame each came at, and with --at the field a game frame
came at.

A movie holds presses and nothing read from the disc, but movies stay out of git all the same:
make writes them where --out says, a scratch or build folder.

Exits 0 when the command ran, when converge found its fixed point and when presses found every
press on its frame. Exits 1 when polls finds no counted polls, converge didn't settle and
presses found one off its frame, and 2 on a bad argument or file.
"""
from __future__ import annotations

import argparse
import struct
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import dolphin_ref
import kar_ram
from routes import Press, parse_route, route_script

GAME_ID = b"GKYE01"
SIGNATURE = b"DTM\x1a"
HEADER_SIZE = 256
PAD_SIZE = 8
RTC = 946684800  # 2000-01-01 00:00:00 UTC, the dolphin-ref config's CustomRTCValue
# The GameCube's CPU clock and NTSC's field rate, 60000/1001 a second.
TICKS_PER_SECOND = 486_000_000
TICKS_PER_FIELD = TICKS_PER_SECOND * 1001 // 60000
POLLS = 2  # polls a field, as dtm.py polls measured on top-ride-grass (docs/dev/status.md)
POLL_SHIFT = 46  # measured the same way: poll 50 is the first of field 48's two
STICK_CENTER = 0x80
TABLE = kar_ram.load()
SCENE_WORD = dolphin_ref.word_of("scene.major", TABLE)  # scene.minor is its bottom byte
# The game reads the pads once a field into the sysdolphin library's queue of raw reads.
# HSD_PadState's first word holds the queue's length, read place, write place and count, a byte
# each. Each entry starts with port 1's PADStatus, whose first word holds the buttons and the
# main stick and whose second the C stick and then the analog triggers, L then R.
PAD_STATE = dolphin_ref.word_of("pad.queue_length", TABLE)
(QUEUE_LENGTH,) = TABLE["pad.queue_length"].values
QUEUE = TABLE["pad.queue"].address
QUEUE_ENTRY = TABLE["pad.queue"].length
TRIGGERS = 4  # the offset of the second word in an entry
RENEW = dolphin_ref.word_of("vi.renew_count", TABLE)
BUTTON_WORDS = tuple(QUEUE + QUEUE_ENTRY * k for k in range(QUEUE_LENGTH))
TRIGGER_WORDS = tuple(a + TRIGGERS for a in BUTTON_WORDS)
WATCH = (SCENE_WORD, RENEW, PAD_STATE, *BUTTON_WORDS, *TRIGGER_WORDS)
# --count-polls puts poll i in the triggers as (i // COUNT_BASE % COUNT_BASE, i % COUNT_BASE).
# The SDK's PADClamp makes a trigger at 30 or less 0, so the game never sees them.
COUNT_BASE = 30
CONVERGE_MAX = 10

# Movie.h's DTMHeader, packed, in its order: (name, struct format).
HEADER = (
    ("filetype", "4s"), ("gameID", "6s"), ("bWii", "?"), ("controllers", "B"),
    ("bFromSaveState", "?"), ("frameCount", "Q"), ("inputCount", "Q"), ("lagCount", "Q"),
    ("uniqueID", "Q"), ("numRerecords", "I"), ("author", "32s"), ("videoBackend", "16s"),
    ("audioEmulator", "16s"), ("md5", "16s"), ("recordingStartTime", "Q"),
    ("bSaveConfig", "?"), ("bSkipIdle", "?"), ("bDualCore", "?"), ("bProgressive", "?"),
    ("bDSPHLE", "?"), ("bFastDiscSpeed", "?"), ("CPUCore", "B"), ("bEFBAccessEnable", "?"),
    ("bEFBCopyEnable", "?"), ("bSkipEFBCopyToRam", "?"), ("bEFBCopyCacheEnable", "?"),
    ("bEFBEmulateFormatChanges", "?"), ("bImmediateXFB", "?"), ("bSkipXFBCopyToRam", "?"),
    ("memcards", "B"), ("bClearSave", "?"), ("bongos", "B"), ("bSyncGPU", "?"),
    ("bNetPlay", "?"), ("bPAL60", "?"), ("language", "B"), ("reserved3", "B"),
    ("bFollowBranch", "?"), ("bUseFMA", "?"), ("GBAControllers", "B"), ("bWidescreen", "?"),
    ("countryCode", "B"), ("reserved", "5s"), ("discChange", "40s"), ("revision", "20s"),
    ("DSPiromHash", "I"), ("DSPcoefHash", "I"), ("tickCount", "Q"), ("reserved2", "11s"),
)
HEADER_FORMAT = "<" + "".join(fmt for _, fmt in HEADER)
assert struct.calcsize(HEADER_FORMAT) == HEADER_SIZE

# ControllerState's first two bytes, one bit each from the lowest, as Movie.h lists them, by
# the routes' names for the buttons.
BITS = ("START", "A", "B", "X", "Y", "Z", "UP", "DOWN", "LEFT", "RIGHT", "L", "R", "disc",
        "reset", "connected", "get_origin")
# The SDK's PADStatus button bits, which the game's queue holds, by the same names.
PAD_BITS = {"LEFT": 0x0001, "RIGHT": 0x0002, "DOWN": 0x0004, "UP": 0x0008, "Z": 0x0010,
            "R": 0x0020, "L": 0x0040, "A": 0x0100, "B": 0x0200, "X": 0x0400, "Y": 0x0800,
            "START": 0x1000}


class Bad(Exception):
    """A route, movie or run file the tool can't use."""


@dataclass
class Pad:
    """What one poll of the pad reads."""
    buttons: set[str] = field(default_factory=set)
    stick_x: int = STICK_CENTER
    stick_y: int = STICK_CENTER
    c_x: int = STICK_CENTER
    c_y: int = STICK_CENTER
    trigger_l: int = 0
    trigger_r: int = 0
    connected: bool = True

    def pack(self) -> bytes:
        bits = 0
        for i, name in enumerate(BITS):
            if name in self.buttons or (name == "connected" and self.connected):
                bits |= 1 << i
        return struct.pack("<HBBBBBB", bits, self.trigger_l, self.trigger_r, self.stick_x,
                           self.stick_y, self.c_x, self.c_y)


def pad_at(presses: Sequence[Press], port: int, frame: int) -> Pad:
    """What PORT reads at FRAME, every press active then laid over a pad at rest, as
    input_script_apply does: buttons add up, a stick push or a trigger is the last press's, and
    a push of 0 leaves its axis alone."""
    pad = Pad()
    for p in presses:
        if p.port != port or not p.at <= frame < p.at + p.duration:
            continue
        pad.buttons |= p.buttons
        if p.stick[0]:
            pad.stick_x = (STICK_CENTER + p.stick[0]) & 0xFF
        if p.stick[1]:
            pad.stick_y = (STICK_CENTER + p.stick[1]) & 0xFF
        if "L" in p.buttons:
            pad.trigger_l = 0xFF
        if "R" in p.buttons:
            pad.trigger_r = 0xFF
    return pad


def count(pad: Pad, poll: int) -> Pad:
    """PAD with POLL's number in the triggers, as --count-polls puts it."""
    pad.trigger_l = poll // COUNT_BASE % COUNT_BASE
    pad.trigger_r = poll % COUNT_BASE
    return pad


def frame_of(field_: int, timeline: Sequence[int]) -> int:
    """The game's frames by the end of FIELD (from 1, 0 before field 1): TIMELINE's, game_frames
    from an earlier run, and one a field past its end. With no timeline, the field itself."""
    if field_ < 1:
        return 0
    if not timeline:
        return field_
    if field_ <= len(timeline):
        return timeline[field_ - 1]
    return timeline[-1] + field_ - len(timeline)


def poll_field(poll: int) -> int:
    """The field Dolphin makes POLL in, POLLS a field, once the game has set its sampling rate at
    field 48 (poll 50). Before that Dolphin polls once a field, so this puts polls 0 to 49 in
    fields 23 to 47, later than they're made; no route presses anything that early."""
    return (poll + POLL_SHIFT) // POLLS


def read_field(poll: int) -> int:
    """The field the game reads POLL in, if it reads it: the field it's made in for that field's
    first poll and the next one for its last, as the queue showed with POLLS at 2."""
    return poll_field(poll) + (poll + POLL_SHIFT) % POLLS


def polls(presses: Sequence[Press], fields: int, timeline: Sequence[int] = (),
          count_polls: bool = False) -> list[bytes]:
    """Port 1's input for FIELDS fields: each poll reads what the route has down at the game
    frame TIMELINE says the field before its read had reached, which is the frame count the
    engine applies a route by."""
    out = []
    for poll in range((fields + 1) * POLLS - POLL_SHIFT):
        pad = pad_at(presses, 0, frame_of(read_field(poll) - 1, timeline))
        out.append((count(pad, poll) if count_polls else pad).pack())
    return out


def header(frames: int, inputs: int, controllers: int = 1) -> bytes:
    """A DTMHeader for a movie of FRAMES fields and INPUTS polls from power-on."""
    values = {name: (b"" if fmt.endswith("s") else 0) for name, fmt in HEADER}
    values.update(filetype=SIGNATURE, gameID=GAME_ID, controllers=controllers,
                  frameCount=frames, inputCount=inputs, recordingStartTime=RTC,
                  tickCount=2 * frames * TICKS_PER_FIELD)
    return struct.pack(HEADER_FORMAT, *(values[name] for name, _ in HEADER))


def ports_used(presses: Sequence[Press]) -> int:
    """The controllers byte: bit 0 for port 1 and one more bit for each port a press uses."""
    bits = 1
    for p in presses:
        bits |= 1 << p.port
    return bits


def make(script: str, fields: int, timeline: Sequence[int] = (),
         count_polls: bool = False) -> bytes:
    """A movie of FIELDS fields playing SCRIPT's presses on pad 1, by TIMELINE's game frames."""
    try:
        presses = parse_route(script)
    except ValueError as e:
        raise Bad(str(e)) from None
    if ports_used(presses) != 1:
        raise Bad("a press on another port than 1: a movie here plays pad 1 only")
    last = frame_of(fields - 1, timeline)
    late = [p for p in presses if p.at + p.duration > last]
    if late:
        raise Bad(f"{late[0].at}: a press that ends after game frame {last}, which the last "
                  f"read of field {fields}, the movie's last, comes at")
    inputs = polls(presses, fields, timeline, count_polls)
    return header(fields, len(inputs)) + b"".join(inputs)


def read_header(data: bytes) -> dict:
    if len(data) < HEADER_SIZE or data[:4] != SIGNATURE:
        raise Bad("not a .dtm: no DTM signature")
    if (len(data) - HEADER_SIZE) % PAD_SIZE:
        raise Bad("its input isn't whole 8-byte polls")
    names = [name for name, _ in HEADER]
    return dict(zip(names, struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])))


def unpack(chunk: bytes) -> Pad:
    bits, tl, tr, sx, sy, cx, cy = struct.unpack("<HBBBBBB", chunk)
    names = {name for i, name in enumerate(BITS) if bits >> i & 1}
    return Pad(names - {"connected"}, sx, sy, cx, cy, tl, tr, "connected" in names)


def changes(data: bytes) -> list[tuple[int, Pad]]:
    """Each poll where port 1's pad differs from the poll before, with what it reads."""
    out, last = [], None
    for i in range(HEADER_SIZE, len(data), PAD_SIZE):
        chunk = data[i:i + PAD_SIZE]
        if chunk != last:
            out.append(((i - HEADER_SIZE) // PAD_SIZE, unpack(chunk)))
        last = chunk
    return out


def counted(word: int) -> int:
    """The poll number --count-polls put in a PADStatus's second word, modulo COUNT_BASE**2."""
    return (word >> 8 & 0xFF) * COUNT_BASE + (word & 0xFF)


def latest(state: int, entries: Sequence[int]) -> Optional[int]:
    """The word of ENTRIES, one from each queue entry, in the entry the game wrote last, from
    HSD_PadState's first word STATE (length, read place, write place, entries not yet taken).
    None before the game has read a pad. The game takes entries as it goes, so the last byte
    says nothing about whether it read one."""
    length, write = state >> 24, state >> 8 & 0xFF
    if length != QUEUE_LENGTH or not any(entries):
        return None
    return entries[(write - 1) % length]


def column(head: Sequence[str], address: int) -> int:
    try:
        return list(head).index(f"{address:08X}")
    except ValueError:
        raise Bad(f"ram.txt doesn't watch {address:08X}") from None


def reads(lines: Sequence[str]) -> list[tuple[int, int, int]]:
    """From a ram.txt watching WATCH, each field the game read a counted poll at: (field, the
    poll's number, scene word). The count wraps every COUNT_BASE**2 polls, so each number is
    taken as the one nearest POLLS a field on from the last."""
    head = lines[0].split()
    scene, state = column(head, SCENE_WORD), column(head, PAD_STATE)
    cols = [column(head, a) for a in TRIGGER_WORDS]
    out: list[tuple[int, int, int]] = []
    wrap = COUNT_BASE ** 2
    for line in lines[1:]:
        words = line.split()
        word = latest(int(words[state], 16), [int(words[c], 16) for c in cols])
        if word is None:
            continue
        poll, n = counted(word), int(words[0])
        if out:
            expect = out[-1][1] + POLLS * (n - out[-1][0])
            poll += (expect - poll + wrap // 2) // wrap * wrap
        out.append((n, poll, int(words[scene], 16)))
    return out


def poll_steps(lines: Sequence[str]) -> list[tuple[int, int, int, int, int]]:
    """Runs of read fields with the same scene word, the same polls read since the last read
    field and the same lag: (first field, last field, scene word, polls, lag). Polls is the
    count since the read before, over however many fields that was, and lag is the read field
    less poll_field of the poll read, 1 when the game reads the last poll of the field before."""
    runs: list[list[int]] = []
    last = None
    for n, poll, word in reads(lines):
        lag = n - poll_field(poll)
        if last is not None:
            step = poll - last
            if runs and runs[-1][2:] == [word, step, lag]:
                runs[-1][1] = n
            else:
                runs.append([n, n, word, step, lag])
        last = poll
    return [tuple(r) for r in runs]  # type: ignore[misc]


def game_frames(lines: Sequence[str]) -> list[int]:
    """From a ram.txt watching RENEW, the game's frames by the end of each field: RENEW's low
    byte counts the frames the game has shown since the last reset to 0, so a field adds what
    it grew by, or all of it after a reset."""
    col = column(lines[0].split(), RENEW)
    out, total, last = [], 0, 0
    for line in lines[1:]:
        value = int(line.split()[col], 16) & 0xFF
        total += value - last if value >= last else value
        last = value
        out.append(total)
    return out


def scene_steps(lines: Sequence[str]) -> list[tuple[int, int, int, int]]:
    """From a ram.txt watching SCENE_WORD and RENEW, each field where the scene word changes:
    (field, the game's frames by then, scene.major, scene.minor)."""
    col = column(lines[0].split(), SCENE_WORD)
    frames = game_frames(lines)
    out, last = [], None
    for line, frame in zip(lines[1:], frames):
        cols = line.split()
        word = int(cols[col], 16)
        if word != last:
            out.append((int(cols[0]), frame, word >> 24, word & 0xFF))
        last = word
    return out


def button_reads(lines: Sequence[str]) -> list[tuple[int, int, set[str]]]:
    """From a ram.txt watching WATCH, each field the game read port 1 in: (field, the game's
    frames by the field before, which is the count the engine applies a route by, the buttons
    it read). A read is a field where the queue's write place moves."""
    head = lines[0].split()
    state = column(head, PAD_STATE)
    cols = [column(head, a) for a in BUTTON_WORDS]
    frames = game_frames(lines)
    out, place = [], None
    for i, line in enumerate(lines[1:]):
        words = line.split()
        value = int(words[state], 16)
        length, write = value >> 24, value >> 8 & 0xFF
        if length != QUEUE_LENGTH or write == place:
            continue
        place = write
        word = int(words[cols[(write - 1) % length]], 16)
        held = {name for name, bit in PAD_BITS.items() if word >> 16 & bit}
        out.append((int(words[0]), frames[i - 1] if i else 0, held))
    return out


def press_reads(presses: Sequence[Press], lines: Sequence[str]) -> list[tuple[Press, int, int]]:
    """Each port 1 press with the read it first showed in: (press, field, the game frame that
    read was given by). A press shows in the first read after the last one matched that has all
    its buttons down and didn't have them in the read before. -1, -1 when none does."""
    found = button_reads(lines)
    out, start = [], 0
    for p in sorted((p for p in presses if p.port == 0 and p.buttons), key=lambda p: p.at):
        hit = next((k for k in range(start, len(found)) if p.buttons <= found[k][2] and
                    not (k and p.buttons <= found[k - 1][2])), None)
        if hit is None:
            out.append((p, -1, -1))
            continue
        out.append((p, found[hit][0], found[hit][1]))
        start = hit + 1
    return out


def describe(pad: Pad) -> str:
    parts = sorted(pad.buttons, key=BITS.index)
    if (pad.stick_x, pad.stick_y) != (STICK_CENTER, STICK_CENTER):
        parts.append(f"stick {pad.stick_x},{pad.stick_y}")
    if pad.trigger_l or pad.trigger_r:
        parts.append(f"triggers {pad.trigger_l},{pad.trigger_r}")
    if not pad.connected:
        parts.append("disconnected")
    return " ".join(parts) or "nothing"


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def cmd_make(args: argparse.Namespace) -> int:
    timeline = game_frames(read_lines(args.timeline)) if args.timeline else []
    data = make(route_script(args.route.read_text(encoding="utf-8")), args.fields, timeline,
                args.count_polls)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(data)
    print(f"{args.out}: {args.fields} fields, {(len(data) - HEADER_SIZE) // PAD_SIZE} polls")
    return 0


def boot_command(iso: Path, movie: Path, fields: int, out: Path, disc: str,
                 watched: Optional[Sequence[str]] = None, dump: bool = False) -> list[str]:
    """dolphin_ref.py playing MOVIE for FIELDS fields into OUT, with WATCHED watched (WATCH's
    words by default) and with DUMP its frames dumped."""
    if watched is None:
        watched = [f"{a:08X}" for a in WATCH]
    watch = [w for a in watched for w in ("--watch", a)]
    return [sys.executable, "-B", str(Path(dolphin_ref.__file__).resolve()), "boot", str(iso),
            "--frames", str(fields), "--movie", str(movie), "--disc", disc, *watch,
            *(["--dump"] if dump else []), "--out", str(out)]


def converge(script: str, fields: int, folder: Path, play, most: int = CONVERGE_MAX,
             count_polls: bool = False) -> tuple[Optional[int], Path]:
    """Play movie 1 (no timeline), make movie N + 1 from run N's ram.txt and stop when it's the
    movie run N played: (N, its movie), or (None, the last movie) after MOST runs. PLAY(movie,
    out) plays a movie into OUT and returns its exit code."""
    movie = make(script, fields, (), count_polls)
    for n in range(1, most + 1):
        path = folder / f"movie-{n}.dtm"
        path.write_bytes(movie)
        out = folder / f"run-{n}"
        if play(path, out):
            raise Bad(f"{out}: the run didn't play all {fields} fields")
        following = make(script, fields, game_frames(read_lines(out / "ram.txt")), count_polls)
        if following == movie:
            return n, path
        movie = following
    return None, path


def cmd_converge(args: argparse.Namespace) -> int:
    args.dir.mkdir(parents=True, exist_ok=True)

    def play(movie: Path, out: Path) -> int:
        return subprocess.run(boot_command(args.iso, movie, args.fields, out, args.disc)).returncode

    n, path = converge(route_script(args.route.read_text(encoding="utf-8")), args.fields, args.dir,
                       play, args.max, args.count_polls)
    if n is None:
        print(f"{path}: no fixed point in {args.max} runs")
        return 1
    print(f"{path}: the fixed point, after {n} runs")
    return 0


def cmd_read(path: Path) -> int:
    data = path.read_bytes()
    h = read_header(data)
    game = h["gameID"].rstrip(b"\0").decode("ascii", "replace")
    print(f"game {game}, controllers "
          f"{h['controllers']:#04x}, from savestate {h['bFromSaveState']}, save config "
          f"{h['bSaveConfig']}, fields {h['frameCount']}, polls {h['inputCount']}, ticks "
          f"{h['tickCount']}, RTC {h['recordingStartTime']}, md5 {h['md5'].hex()}")
    for poll, pad in changes(data):
        print(f"poll {poll}: {describe(pad)}")
    return 0


def cmd_steps(path: Path, at: Sequence[int] = ()) -> int:
    lines = read_lines(path)
    for field_, frame, major, minor in scene_steps(lines):
        print(f"field {field_} game frame {frame}: scene.major {major} scene.minor {minor}")
    frames = game_frames(lines)
    for frame in at:
        field_ = next((n for n, f in enumerate(frames, 1) if f >= frame), None)
        print(f"game frame {frame}: " + (f"field {field_}" if field_ else
                                         f"not reached by field {len(frames)}"))
    return 0


def cmd_polls(path: Path) -> int:
    steps = poll_steps(read_lines(path))
    for first, last, word, step, lag in steps:
        print(f"fields {first}-{last}: scene.major {word >> 24} scene.minor {word & 0xFF}, "
              f"{step} polls since the last read, lag {lag}")
    return 0 if steps else 1


def cmd_presses(route: Path, ram: Path) -> int:
    presses = parse_route(route_script(route.read_text(encoding="utf-8")))
    off = 0
    for p, field_, frame in press_reads(presses, read_lines(ram)):
        names = "+".join(sorted(p.buttons))
        if field_ < 0:
            print(f"{p.at}:{names}: never read")
            off += 1
            continue
        said = "on its frame" if frame == p.at else f"{frame - p.at:+d} frames off"
        print(f"{p.at}:{names}: read at field {field_}, given at game frame {frame}, {said}")
        off += frame != p.at
    return 1 if off else 0


def frame_count(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} isn't a whole number") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"{text!r} isn't 1 or more")
    return value


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    mk = sub.add_parser("make", help="turn a route into a .dtm")
    mk.add_argument("route", type=Path, metavar="ROUTE")
    mk.add_argument("--out", type=Path, required=True, metavar="FILE")
    mk.add_argument("--fields", type=frame_count, required=True, metavar="N",
                    help="the fields the movie covers, past the route's last press")
    mk.add_argument("--timeline", type=Path, metavar="RAM_TXT",
                    help="an earlier run's ram.txt, for the game frame each field reaches")
    mk.add_argument("--count-polls", action="store_true",
                    help="put each poll's number in the triggers, for polls to count")
    cv = sub.add_parser("converge", help="remake a movie from its own runs until it settles")
    cv.add_argument("route", type=Path, metavar="ROUTE")
    cv.add_argument("iso", type=Path, metavar="ISO")
    cv.add_argument("--fields", type=frame_count, required=True, metavar="N")
    cv.add_argument("--dir", type=Path, required=True, metavar="DIR",
                    help="where the movies and runs go, a scratch or build folder")
    cv.add_argument("--max", type=frame_count, default=CONVERGE_MAX, metavar="K",
                    help=f"the most runs (default {CONVERGE_MAX})")
    cv.add_argument("--disc", choices=sorted(dolphin_ref.DISC), default=dolphin_ref.DEFAULT_DISC)
    cv.add_argument("--count-polls", action="store_true",
                    help="count the polls in every movie, for polls to read the last run")
    rd = sub.add_parser("read", help="print a .dtm's header and its presses")
    rd.add_argument("movie", type=Path, metavar="FILE")
    pl = sub.add_parser("polls", help="count the polls a field in a counted run's ram.txt")
    pl.add_argument("ram", type=Path, metavar="RAM_TXT")
    pr = sub.add_parser("presses", help="where the game read each of a route's presses")
    pr.add_argument("route", type=Path, metavar="ROUTE")
    pr.add_argument("ram", type=Path, metavar="RAM_TXT")
    st = sub.add_parser("steps", help="print a run's scene steps by field and game frame")
    st.add_argument("ram", type=Path, metavar="RAM_TXT")
    st.add_argument("--at", type=frame_count, action="append", default=[], metavar="FRAME",
                    help="also print the field the game reaches FRAME at, such as a checkpoint")
    args = ap.parse_args(argv)
    try:
        if args.command == "make":
            return cmd_make(args)
        if args.command == "converge":
            return cmd_converge(args)
        if args.command == "read":
            return cmd_read(args.movie)
        if args.command == "steps":
            return cmd_steps(args.ram, args.at)
        if args.command == "presses":
            return cmd_presses(args.route, args.ram)
        return cmd_polls(args.ram)
    except (Bad, OSError, IndexError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
