#!/usr/bin/env python3
"""Which guest words play differently in Dragoon than in Dolphin, and from which pass? Any words
of a race, read on both sides and compared one by one.

Usage: race_words.py dolphin ROUTE --movie DTM --fields N --out DIR [--iso ISO] WORD...
       race_words.py dragoon ROUTE --out DIR [--from FRAME] [--to FRAME] [-- SETTING ...]
       race_words.py diff DIR
       race_words.py show DIR WORD --passes A-B

race_trace.py gives the first pass where a race's compared values, dolphin_diff.FIELDS, differ.
A value they don't compare can differ first, such as a velocity behind a position, and this
finds it. A WORD is a watch as dolphin_ref.py boot takes it, a hex ADDR or ADDR+OFF+...+OFF for
the word a pointer path leads to, or either with :N after it for N words in a row from there,
its last offset (or ADDR) going up by 4 each.

dolphin plays ROUTE's converged movie DTM (dtm.py converge --disc console) for N fields, as
dolphin_diff.py does but with no frame dumps, watching dolphin_diff.watches()'s timeline words
and then the WORDs, into DIR/dolphin/ (dolphin_ref.py's ram.txt and run.json). Dolphin's memory
watcher sends each field's changed words as one datagram, and macOS refuses a local datagram
over net.local.dgram.maxdgram, 2048 bytes by default. A refused one would lose its field and
move every field after it, so dolphin refuses WORDs whose datagram could be longer than
DATAGRAM, with every word changing at once.

dragoon plays ROUTE in Dragoon as dolphin_diff.py does, both sides' seeds pinned (SEED) and the
disc at console speed, with no frame dumps and with each SETTING passed on to probe.sh, such as
GCN_INTERPRET=all. It reads the words DIR/dolphin/ram.txt's head names at every frame from FROM
to TO, by default from dolphin_diff.TRACE_EARLY frames before Dolphin's first race to the last
game frame Dolphin's run reaches, into DIR/dragoon/words.txt: the same
head, then a line a frame, the frame and each word in hex. A pointer path is followed the way
Dolphin's watcher follows one: when a pointer on the way leads outside main RAM, the word is
that pointer. A pointer into main RAM's uncached mirror at C0000000 leads into main RAM, as
the console's BATs map it.

diff and show refuse a Dolphin run that lost a field. The watcher's datagrams queue in the
receiving socket, which holds only a few of the largest, so a long enough stall loses one, and
every field after it moves. vi.renew_count (kar_ram.json), which the timeline watches, either
stays, goes up by one or goes back to 0 from one field to the next, so any other step means a
field was lost. A lost field with no new picture in it doesn't show.

diff compares the two at the first race in Dolphin's run (dolphin_diff.RACES), word by word.
Dragoon's frames at a pass past the last one Dolphin's run shows are left out.
Each Dragoon frame in the race whose pass Dolphin's run shows is compared with Dolphin's fields
at that pass and the one either side, as race_trace.py compares, since Dolphin reads RAM partway
into a pass. A word differs at the first frame whose value none of those fields holds, but for
a pass Dragoon read at another point of the same game steps. That's a pass whose rand.seed
(RAND, when it's watched) is at none of Dolphin's fields of the pass and the one either side,
and strictly between them: HSD_Rand's draws from one of the pass before's seeds come to
Dragoon's on the way to one of the pass after's, within DRAWS_MAX. A seed in step with
Dolphin's, or one Dolphin's fields hold still, as on Top Ride, makes no such pass. A word
that differs at such a pass alone, matching at the passes either side, isn't counted there.
Nor is the seed itself, in a run of such passes that ends with the seed matching again. A run
that lasts to the last pass compared counts from its first pass. Each side reads at its
own point of the game's steps, so where one side's pass holds two steps and the other's holds
them a pass apart, the two read states no field of the other shows. On air-ride-race that's
passes 1864 and 3863, with every word the same again a pass later (docs/dev/status.md,
"Air Ride's lone passes"). diff prints each word that differs, the earliest pass first, with
Dragoon's value and Dolphin's at the pass's first field, as f32 too with how many ulp apart.
Then it lists the passes it didn't count and says how many words match through which pass. A
word the game holds a value in for only part of a pass can show a difference that isn't one,
since each side reads at its own point of the pass, so `show` prints a word's values on both
sides pass by pass for a look. None of it goes in git.

Exits 0 when the command ran, whether a word differs or not, 1 when a run fell short, and 2 on
a bad argument, a missing or unreadable file or a refused run.
"""
from __future__ import annotations

import argparse
import dataclasses
import math
import struct
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import bot_link
import dolphin_diff
import dolphin_ref
import dtm
import kar_ram
import state_goldens
from dolphin_diff import PASSES, RACES, TABLE, Bad
from probe_dirs import remove_run
from routes import MANIFEST, Route, select_routes

DATAGRAM = 2048  # macOS's net.local.dgram.maxdgram, the most a local datagram may hold
HEX_MAX = 8  # a word's value in the datagram, in hex with no leading zeros
WORDS = "words.txt"
SPAN = ":"
UNCACHED = 0x40000000  # main RAM's uncached mirror, at C0000000, less its cached address
RENEW = f"{dtm.RENEW:08X}"  # vi.renew_count's watch
RAND = f"{dolphin_ref.word_of('rand.seed', TABLE):08X}"  # HSD_Rand's seed's watch
# The most HSD_Rand draws looked through from one pass to the pass after next. Dolphin's runs take
# up to 641 on Air Ride's race, 203 on City Trial's and 0 on Top Ride's.
DRAWS_MAX = 1000
Row = dict[str, int]  # a watch's text to its word


def expand(text: str) -> list[str]:
    """The watches TEXT names: TEXT itself, or N of them from TEXT:N."""
    head, sep, count = text.partition(SPAN)
    first = dolphin_ref.watch_address(head)
    if not sep:
        return [first]
    if not count.isdigit() or int(count) < 1:
        raise argparse.ArgumentTypeError(f"{text!r}: N in WORD:N is a whole number from 1")
    *path, last = first.split(dolphin_ref.CHAIN)
    out = []
    for k in range(int(count)):
        step = int(last, 16) + k * dolphin_ref.WORD
        if path:
            if step > 0xFFFF:
                raise argparse.ArgumentTypeError(f"{text!r} runs past offset FFFF")
            out.append(dolphin_ref.chain(int(path[0], 16), [*(int(o, 16) for o in path[1:]), step]))
        else:
            out.append(dolphin_ref.watch_address(f"{step:08X}"))
    return out


def datagram(watched: Sequence[str]) -> int:
    """The bytes the watcher's datagram takes when every one of WATCHED changes: each address as
    Locations.txt has it and its value, a line each, and the NUL after them."""
    return sum(len(w) + 1 + HEX_MAX + 1 for w in watched) + 1


def watch_list(words: Sequence[str]) -> list[str]:
    """dolphin_diff's timeline words, then WORDS' watches, each once, refused when their datagram
    could be over DATAGRAM."""
    out = list(dolphin_diff.watches(()))
    for text in words:
        out.extend(w for w in expand(text) if w not in out)
    size = datagram(out)
    if size > DATAGRAM:
        raise Bad(f"{len(out)} watches make a datagram of up to {size} bytes, over the "
                  f"{DATAGRAM} macOS lets through; watch fewer")
    return out


def parse(path: Path) -> tuple[list[str], list[tuple[int, Row]]]:
    """A ram.txt or words.txt: its watches and each line's number and words."""
    lines = dtm.read_lines(path)
    if not lines or not lines[0].startswith("frame "):
        raise Bad(f"{path}: no head line")
    head = lines[0].split()[1:]
    rows = []
    for line in lines[1:]:
        n, *values = line.split()
        if len(values) != len(head):
            raise Bad(f"{path}: line {n} has {len(values)} words for {len(head)} watches")
        rows.append((int(n), dict(zip(head, (int(v, 16) for v in values)))))
    return head, rows


def lost_field(rows: Sequence[tuple[int, Row]]) -> Optional[str]:
    """Where ROWS, a Dolphin run's, show a lost field: vi.renew_count stepping other than by
    staying, going up by one or going back to 0. None when they show none."""
    for (_, was), (n, now) in zip(rows, rows[1:]):
        if now[RENEW] not in (was[RENEW], was[RENEW] + 1, 0):
            return f"vi.renew_count goes from {was[RENEW]} to {now[RENEW]} at line {n}"
    return None


def read_dolphin(ram: Path) -> tuple[list[str], list[tuple[int, Row]]]:
    """RAM, a Dolphin run's ram.txt, as parse gives it, refused when it has no field or lost one."""
    head, rows = parse(ram)
    if not rows:
        raise Bad(f"{ram}: no field")
    lost = lost_field(rows)
    if lost:
        raise Bad(f"{ram}: {lost}, so a field was lost and every field after it moved; "
                  "run dolphin again, watching fewer words")
    return head, rows


# Dragoon's side.


def ram_address(pointer: int) -> Optional[int]:
    """Where POINTER leads in main RAM as the link reads it: itself, or the cached address of one
    into the uncached mirror. None outside both."""
    for address in (pointer, pointer - UNCACHED):
        if kar_ram.in_ram(address, 1):
            return address
    return None


def read_words(link, watched: Sequence[str]) -> list[int]:
    """Each of WATCHED now, read through LINK, a pointer path followed as Dolphin's watcher does,
    with the words each pointer leads to read together."""
    chased: dict[tuple[int, ...], tuple[bool, int]] = {}  # a path's pointer, or where it stopped

    def word(address: int) -> int:
        return struct.unpack(">I", link.read(address, dolphin_ref.WORD))[0]

    def chase(path: tuple[int, ...]) -> tuple[bool, int]:
        """(True, the pointer PATH leads to) or (False, the value it stopped at)."""
        if path not in chased:
            if len(path) == 1:
                value = word(path[0])
            else:
                ok, base = chase(path[:-1])
                if not ok:
                    chased[path] = (False, base)
                    return chased[path]
                value = word(base + path[-1])
            address = ram_address(value)
            chased[path] = (True, address) if address is not None else (False, value)
        return chased[path]

    where: list[tuple[bool, int]] = []
    for text in watched:
        head, *offsets = text.split(dolphin_ref.CHAIN)
        path = (int(head, 16), *(int(o, 16) for o in offsets))
        if len(path) == 1:
            where.append((True, path[0]))
            continue
        ok, base = chase(path[:-1])
        where.append((True, base + path[-1]) if ok else (False, base))
    values = {}
    wanted = sorted({a for ok, a in where if ok and kar_ram.in_ram(a, dolphin_ref.WORD)})
    i = 0
    while i < len(wanted):
        j = i
        while (j + 1 < len(wanted) and wanted[j + 1] - wanted[i] + dolphin_ref.WORD <= kar_ram.READ_MAX
               and wanted[j + 1] - wanted[j] <= 4 * dolphin_ref.WORD):
            j += 1
        data = link.read(wanted[i], wanted[j] - wanted[i] + dolphin_ref.WORD)
        for a in wanted[i:j + 1]:
            k = a - wanted[i]
            values[a] = struct.unpack(">I", data[k:k + dolphin_ref.WORD])[0]
        i = j + 1
    return [values.get(a, 0) if ok else a for ok, a in where]


class Reader(state_goldens.Checkpoints):
    """A bot that presses nothing and reads WATCHED at every frame from FIRST to LAST into
    `rows`, and stops the run there."""

    def __init__(self, watched: Sequence[str], first: int, last: int) -> None:
        super().__init__([last], 1, fields=(), table=TABLE)
        self.watched = list(watched)
        self.first, self.last = first, last
        self.rows: dict[int, list[int]] = {}

    def __call__(self, link):
        if self.first <= link.frame <= self.last:
            self.rows[link.frame] = read_words(link, self.watched)
        return super().__call__(link)


def play_dragoon(route: Route, out: Path, first: Optional[int], last: Optional[int],
                 probe: Optional[Path] = None, settings: Sequence[str] = ()) -> Optional[str]:
    """Play ROUTE in Dragoon reading OUT/dolphin/ram.txt's words from FIRST to LAST, into
    OUT/dragoon/words.txt. Returns why the run ended badly, None when it ended at its
    --exit-after."""
    ram = dolphin_diff.dolphin_dir(out) / "ram.txt"
    watched, _ = parse(ram)
    span = dolphin_diff.trace_span(dtm.read_lines(ram))
    if span is None and (first is None or last is None):
        raise Bad(f"{ram}: no race, so give --from and --to")
    first = first if first is not None else span[0]
    last = last if last is not None else span[1]
    if last < first:
        raise Bad(f"--to {last} is before --from {first}")
    name = f"race-words-{route.name}"
    bot = Reader(watched, first, last)
    seconds = math.ceil(route.seconds * dolphin_diff.SLOW * max(1.0, last / max(route.required)))
    played = dataclasses.replace(route, required=[last], dump_every=1, seconds=seconds)
    print(f"{route.name}: Dragoon, {len(watched)} words every frame from {first} to {last}",
          flush=True)
    outcome, _ = state_goldens.play(played, name, every=None, bot=bot, probe=probe,
                                    settings=[f"--disc={dolphin_diff.DISC}", dolphin_diff.SEED, *settings])
    try:
        if outcome.reason == bot_link.NEVER_LINKED:
            raise Bad(f"{route.name}: the game never connected: {outcome.detail}")
        folder = dolphin_diff.dragoon_dir(out)
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / WORDS, "w", encoding="utf-8") as f:
            f.write("frame " + " ".join(watched) + "\n")
            for n, values in sorted(bot.rows.items()):
                f.write(f"{n} " + " ".join(f"{v:08X}" for v in values) + "\n")
    finally:
        remove_run(outcome.run_dir)
    return state_goldens.ended_badly(outcome)


# The comparison.


def f32(word: int) -> float:
    return struct.unpack(">f", struct.pack(">I", word))[0]


def ordered(word: int) -> int:
    """WORD's place among f32s in order, -0 and +0 one place."""
    return 0x80000000 - (word & 0x7FFFFFFF) if word & 0x80000000 else word + 0x80000000


def ulps(a: int, b: int) -> int:
    return abs(ordered(a) - ordered(b))


def looks_float(word: int) -> bool:
    """Whether WORD reads as a finite f32 that isn't a pointer into main RAM."""
    return not kar_ram.in_ram(word, 1) and (word >> 23) & 0xFF != 0xFF


def values_text(ours: int, theirs: int) -> str:
    text = f"Dragoon {ours:08X}, Dolphin {theirs:08X}"
    if looks_float(ours) and looks_float(theirs):
        text += f" ({f32(ours):.9g} against {f32(theirs):.9g}, {ulps(ours, theirs)} ulp)"
    return text


def draw(seed: int) -> int:
    """HSD_Rand's next seed (kar_ram.json's rand.seed)."""
    return (seed * 214013 + 2531011) & 0xFFFFFFFF


def between(start: int, mid: int, end: int, most: int = DRAWS_MAX) -> bool:
    """Whether HSD_Rand's draws from seed START come to MID on the way to END, within MOST."""
    seen = False
    for _ in range(most + 1):
        seen = seen or start == mid
        if start == end:
            return seen
        start = draw(start)
    return False


@dataclass
class Word:
    watch: str
    frame: Optional[int] = None  # the first Dragoon frame it differs at, None when it doesn't
    at: Optional[int] = None  # and that frame's pass
    ours: int = 0
    theirs: int = 0  # Dolphin's at the pass's first field

    def text(self) -> str:
        return (f"{self.watch} first differs at frame {self.frame}, pass {self.at}: "
                + values_text(self.ours, self.theirs))


@dataclass
class Diff:
    race: str
    words: list[Word] = field(default_factory=list)
    frames: tuple[int, int] = (0, 0)  # the Dragoon frames compared, first and last
    through: Optional[int] = None  # the last pass compared
    elsewhere: dict[int, list[str]] = field(default_factory=dict)  # lone passes read elsewhere

    def differing(self) -> list[Word]:
        return sorted((w for w in self.words if w.frame is not None), key=lambda w: (w.at, w.frame))

    def elsewhere_text(self) -> str:
        passes = [f"pass {p} ({len(w)} words)" if len(w) > 1 else f"pass {p} ({w[0]})"
                  for p, w in sorted(self.elsewhere.items()) if w != [RAND]]
        alone = sum(w == [RAND] for w in self.elsewhere.values())
        if alone:
            passes.append(f"{alone} pass{'es' if alone > 1 else ''} where only {RAND}, rand.seed, differs")
        listed = ", ".join(passes[:-1]) + " and " + passes[-1] if len(passes) > 1 else passes[0]
        return (f"Not counted, since Dragoon read them at another point of the same draws: {listed}")

    def lines(self) -> list[str]:
        if self.through is None:
            return [f"{self.race}: no pass compared"]
        out = [f"{self.race}: {len(self.words)} words, Dragoon frames {self.frames[0]} to "
               f"{self.frames[1]}, through pass {self.through}"]
        out += [w.text() for w in self.differing()]
        if self.elsewhere:
            out.append(self.elsewhere_text())
        same = len(self.words) - len(self.differing())
        out.append(f"{same} words match through pass {self.through}")
        return out


def race_fields(lines: Sequence[str]) -> tuple[str, tuple[int, int], dict[int, list[int]]]:
    """Dolphin's first race in LINES: its name, its scene and its fields (from 0) by pass."""
    found = dolphin_diff.scenes(lines)
    counts = dolphin_diff.passes(lines)
    for i, (_, scene, since) in enumerate(found):
        if scene in RACES:
            until = found[i + 1][2] if i + 1 < len(found) else 0
            by_pass: dict[int, list[int]] = {}
            for n, k in enumerate(dolphin_diff.scene_passes(counts, since, until)):
                if k is not None:
                    by_pass.setdefault(k, []).append(n)
            return RACES[scene], scene, by_pass
    raise Bad("Dolphin's run has no race")


def scene_and_pass(row: Row) -> tuple[tuple[int, int], int]:
    link = dolphin_diff.Watched(row)
    return ((kar_ram.read(link, "scene.major", TABLE), kar_ram.read(link, "scene.minor", TABLE)),
            kar_ram.read(link, PASSES, TABLE))


def compare(ram: Path, words: Path) -> Diff:
    head, dolphin = read_dolphin(ram)
    ours_head, dragoon = parse(words)
    if ours_head != head:
        raise Bad(f"{words} doesn't watch what {ram} does")
    name, scene, by_pass = race_fields(dtm.read_lines(ram))
    timeline = set(dolphin_diff.watches(()))
    diff = Diff(name, [Word(w) for w in head if w not in timeline])
    rows = [r for _, r in dolphin]
    misses: dict[str, dict[int, tuple[int, int, int]]] = {w.watch: {} for w in diff.words}
    ours: dict[int, list[Row]] = {}
    for frame, row in dragoon:
        got_scene, at = scene_and_pass(row)
        if got_scene != scene or at not in by_pass:
            continue
        near = [rows[n] for p in (at - 1, at, at + 1) for n in by_pass.get(p, ())]
        first = rows[by_pass[at][0]]
        for watch, missed in misses.items():
            if at not in missed and all(r[watch] != row[watch] for r in near):
                missed[at] = (frame, row[watch], first[watch])
        ours.setdefault(at, []).append(row)
        diff.frames = (diff.frames[0] or frame, frame)
        diff.through = at

    def read_elsewhere(p: int) -> bool:
        """Whether Dragoon's seed at pass P is at none of Dolphin's fields of passes P-1 to P+1
        and on Dolphin's draws from pass P-1 to pass P+1, so strictly between them. A seed
        Dolphin's fields hold still across the passes has nothing between."""
        if p - 1 not in ours or p + 1 not in ours:
            return False
        starts = {rows[n][RAND] for n in by_pass.get(p - 1, ())}
        ends = {rows[n][RAND] for n in by_pass.get(p + 1, ())}
        near = {rows[n][RAND] for q in (p - 1, p, p + 1) for n in by_pass.get(q, ())}
        return all(row[RAND] not in near and any(between(a, row[RAND], b) for a in starts for b in ends)
                   for row in ours[p])

    # The passes Dragoon read at another point of the same draws: each run of passes running
    # where the seed differs, every one read_elsewhere, that ends with the seed matching again.
    seed_off: set[int] = set()
    if RAND in misses:
        run: list[int] = []
        for p in sorted(ours):
            if p in misses[RAND]:
                run.append(p)
                continue
            if all(read_elsewhere(q) for q in run):
                seed_off.update(run)
            run = []

    for w in diff.words:
        missed = misses[w.watch]
        for p in sorted(missed):
            alone = w.watch == RAND or (p - 1 not in missed and p + 1 not in missed)
            if alone and p in seed_off:
                diff.elsewhere.setdefault(p, []).append(w.watch)
                continue
            w.frame, w.ours, w.theirs = missed[p]
            w.at = p
            break
    return diff


def show(ram: Path, words: Path, watch: str, passes: range) -> list[str]:
    """WATCH's value on both sides at each pass of PASSES: Dragoon's at each of its frames there,
    then Dolphin's at each of its fields."""
    head, dolphin = read_dolphin(ram)
    _, dragoon = parse(words)
    if watch not in head:
        raise Bad(f"{ram} doesn't watch {watch}")
    _, scene, by_pass = race_fields(dtm.read_lines(ram))
    ours: dict[int, list[str]] = {}
    for frame, row in dragoon:
        got_scene, at = scene_and_pass(row)
        if got_scene == scene:
            ours.setdefault(at, []).append(f"{row[watch]:08X}")
    def theirs_at(p: int) -> list[str]:
        return [f"{dolphin[n][1][watch]:08X}" for n in by_pass.get(p, ())]

    out = [f"{watch}, pass: Dragoon at each frame | Dolphin at each field, * where Dragoon's "
           "value is at none of Dolphin's fields of the pass or one either side"]
    for p in passes:
        theirs = theirs_at(p)
        near = {*theirs_at(p - 1), *theirs, *theirs_at(p + 1)}
        mark = "" if set(ours.get(p, [])) <= near else "  *"
        out.append(f"{p}: {' '.join(ours.get(p, ['-']))} | {' '.join(theirs) or '-'}{mark}")
    return out


def parse_passes(text: str) -> range:
    first, sep, last = text.partition("-")
    if not (first.isdigit() and last.isdigit() and sep) or int(last) < int(first):
        raise argparse.ArgumentTypeError(f"{text!r} isn't A-B with B no less than A")
    return range(int(first), int(last) + 1)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    dp = sub.add_parser("dolphin")
    dp.add_argument("route", metavar="ROUTE")
    dp.add_argument("--movie", type=Path, required=True, metavar="DTM")
    dp.add_argument("--fields", type=int, required=True, metavar="N")
    dp.add_argument("--out", type=Path, required=True, metavar="DIR")
    dp.add_argument("--iso", type=Path, default=dolphin_diff.ISO)
    dp.add_argument("words", nargs="+", metavar="WORD")
    gp = sub.add_parser("dragoon")
    gp.add_argument("route", metavar="ROUTE")
    gp.add_argument("--out", type=Path, required=True, metavar="DIR")
    gp.add_argument("--from", dest="first", type=int, metavar="FRAME")
    gp.add_argument("--to", dest="last", type=int, metavar="FRAME")
    fp = sub.add_parser("diff")
    fp.add_argument("dir", type=Path, metavar="DIR")
    sp = sub.add_parser("show")
    sp.add_argument("dir", type=Path, metavar="DIR")
    sp.add_argument("watch", metavar="WORD")
    sp.add_argument("--passes", type=parse_passes, required=True, metavar="A-B")
    argv, settings = bot_link.split_settings(argv)
    args = ap.parse_args(argv)
    try:
        if args.command in ("diff", "show"):
            ram = dolphin_diff.dolphin_dir(args.dir) / "ram.txt"
            words = dolphin_diff.dragoon_dir(args.dir) / WORDS
            if args.command == "diff":
                print("\n".join(compare(ram, words).lines()))
            else:
                (watch,) = expand(args.watch)
                print("\n".join(show(ram, words, watch, args.passes)))
            return 0
        (route,) = select_routes([args.route], MANIFEST)
        if state_goldens.route_pads(route) != 1:
            raise Bad(f"{route.name}: plays more than one pad, and both sides here play port 1 only")
        if args.command == "dolphin":
            watched = watch_list(args.words)
            if args.fields < 1:
                raise Bad("--fields is 1 or more")
            cmd = dtm.boot_command(args.iso, args.movie, args.fields,
                                   dolphin_diff.dolphin_dir(args.out), dolphin_diff.DISC, watched)
            print(f"{route.name}: Dolphin, {args.fields} fields, {len(watched)} words", flush=True)
            return subprocess.run(cmd).returncode
        bad = play_dragoon(route, args.out, args.first, args.last, settings=settings)
        if bad:
            print(f"{route.name}: {bad}")
        return 1 if bad else 0
    except argparse.ArgumentTypeError as e:
        ap.error(str(e))
    except (Bad, OSError, ValueError, KeyError, bot_link.LinkSetupError) as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
